"""Tests for Web Push delivery of due reminders."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pywebpush import WebPushException

from src.backend.main import app
from src.backend.reminders.push import PushService
from src.backend.reminders.reminder_manager import ReminderManager

client = TestClient(app)
SUB = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "BPkey", "auth": "authsecret"}}


@pytest.fixture
def service(tmp_path):
    return PushService(db_path=str(tmp_path / "push.db"))


def past(minutes=1):
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def test_keys_are_generated_once_and_reused(tmp_path):
    first = PushService(db_path=str(tmp_path / "a.db")).keys
    second = PushService(db_path=str(tmp_path / "a.db")).keys
    assert first.public_key == second.public_key and len(first.public_key) == 87
    assert (tmp_path / "vapid.json").stat().st_mode & 0o777 == 0o600


@patch("src.backend.reminders.push.webpush")
def test_due_reminders_are_pushed_once_to_every_device(mock_push, service):
    service.subscribe("u1", SUB)
    service.subscribe("u1", {**SUB, "endpoint": "https://push.example/phone"})
    reminder = service.reminders.create_reminder("u1", "Stretch", past())
    service.reminders.create_reminder("u1", "Later", (datetime.now(UTC) + timedelta(days=1)).isoformat())

    assert service.deliver_due() == 1
    assert mock_push.call_count == 2
    payload = json.loads(mock_push.call_args.kwargs["data"])
    assert payload["body"] == "Stretch" and payload["tag"] == f"reminder-{reminder['id']}"
    assert service.deliver_due() == 0  # already notified


@patch("src.backend.reminders.push.webpush")
def test_gone_subscriptions_are_removed(mock_push, service):
    service.subscribe("u2", SUB)
    service.reminders.create_reminder("u2", "Ping", past())
    gone = MagicMock(status_code=410)
    mock_push.side_effect = WebPushException("gone", response=gone)

    assert service.deliver_due() == 0
    assert service.subscriptions("u2") == []
    # Not marked notified, so the in-app toast still shows it
    assert [r["reminder_text"] for r in service.reminders.get_due("u2")] == ["Ping"]


@patch("src.backend.reminders.push.webpush")
def test_users_without_push_keep_in_app_notifications(mock_push, service):
    service.reminders.create_reminder("nopush", "Call back", past())
    assert service.deliver_due() == 0
    mock_push.assert_not_called()
    assert len(service.reminders.get_due("nopush")) == 1


def test_invalid_subscriptions_are_rejected(service):
    with pytest.raises(ValueError):
        service.subscribe("u3", {"endpoint": "http://insecure", "keys": {"p256dh": "x", "auth": "y"}})


def test_push_api():
    key = client.get("/api/v1/push/public-key").json()["public_key"]
    assert len(key) == 87
    assert client.post("/api/v1/push/subscribe", params={"user_id": "api"}, json=SUB).status_code == 201
    insecure = {**SUB, "endpoint": "http://x.y/z"}
    assert client.post("/api/v1/push/subscribe", params={"user_id": "api"}, json=insecure).status_code == 400
    assert client.delete("/api/v1/push/subscribe", params={"endpoint": SUB["endpoint"]}).status_code == 200


def test_reminder_manager_lists_due_across_users(tmp_path):
    mgr = ReminderManager(db_path=str(tmp_path / "r.db"))
    mgr.create_reminder("a", "A", past())
    mgr.create_reminder("b", "B", past(2))
    assert [r["reminder_text"] for r in mgr.get_all_due()] == ["B", "A"]


def test_push_payload_is_decryptable_by_the_browser_and_signed(service):
    """Act as the browser: our keys in the subscription, decrypt what the server sends, verify the VAPID JWT."""
    import base64
    import os

    import http_ece
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    browser_key = ec.generate_private_key(ec.SECP256R1())
    auth_secret = os.urandom(16)
    public = browser_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    service.subscribe("crypto", {"endpoint": "https://fcm.googleapis.com/fcm/send/fake",
                                 "keys": {"p256dh": b64(public), "auth": b64(auth_secret)}})
    service.reminders.create_reminder("crypto", "Drink water", past())

    sent = MagicMock(status_code=201)
    with patch("pywebpush.requests.post", return_value=sent) as post:
        assert service.deliver_due() == 1

    request = post.call_args
    assert request.args[0] == "https://fcm.googleapis.com/fcm/send/fake"
    headers = request.kwargs["headers"]
    assert headers["content-encoding"] == "aes128gcm" and headers["ttl"] == "3600"

    plaintext = http_ece.decrypt(request.kwargs["data"], private_key=browser_key, auth_secret=auth_secret,
                                 version="aes128gcm")
    assert json.loads(plaintext)["body"] == "Drink water"

    scheme, params = headers["authorization"].split(" ", 1)
    fields = dict(p.strip().split("=", 1) for p in params.split(","))
    token = fields["t"]
    assert fields["k"] == service.keys.public_key  # the key browsers subscribed with
    signed, _, signature = token.rpartition(".")
    unb64 = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))  # noqa: E731
    raw = unb64(signature)
    server_key = serialization.load_pem_private_key(service.keys.private_pem.encode(), None).public_key()
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    server_key.verify(der, signed.encode(), ec.ECDSA(hashes.SHA256()))  # raises if the signature is wrong
    claims = json.loads(unb64(signed.split(".")[1]))
    assert scheme == "vapid" and claims["aud"] == "https://fcm.googleapis.com" and claims["sub"].startswith("mailto:")
