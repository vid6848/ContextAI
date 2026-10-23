"""Tests for Supabase sign-in: token verification, account isolation and moving guest data on sign-in."""

import io
import time
from unittest.mock import patch

import jwt
import pymupdf
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from src.backend import auth
from src.backend.core.config import settings
from src.backend.main import app

client = TestClient(app)
SUPABASE = "https://demo.supabase.co"
KEY = ec.generate_private_key(ec.SECP256R1())


def token(sub="0b9f7c1e-1111-2222-3333-444455556666", *, exp_in=3600, key=KEY, iss=f"{SUPABASE}/auth/v1",
          aud="authenticated"):
    now = int(time.time())
    claims = {"sub": sub, "aud": aud, "iss": iss, "iat": now, "exp": now + exp_in, "role": "authenticated"}
    return jwt.encode(claims, key, algorithm="ES256")


def bearer(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(autouse=True)
def supabase(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", SUPABASE)
    monkeypatch.setattr(settings, "supabase_publishable_key", "sb_publishable_test")
    verifier = auth.TokenVerifier(SUPABASE, key_for=lambda _t: KEY.public_key())
    monkeypatch.setattr(auth, "get_verifier", lambda: verifier)


def test_signed_in_requests_act_as_the_account():
    created = client.post("/api/v1/conversations", json={"user_id": "spoofed"}, headers=bearer(token())).json()
    assert created["user_id"] == "acct_0b9f7c1e-1111-2222-3333-444455556666"

    mine = client.get("/api/v1/conversations", headers=bearer(token())).json()["conversations"]
    assert [c["id"] for c in mine] == [created["id"]]
    # The body/query user_id is ignored once signed in, and nobody else sees the chat
    assert client.get("/api/v1/conversations", params={"user_id": "spoofed"}).json()["conversations"] == []
    other = bearer(token(sub="99999999-0000-0000-0000-000000000000"))
    assert client.get("/api/v1/conversations", headers=other).json()["conversations"] == []


def test_guests_cannot_pose_as_an_account():
    resp = client.get("/api/v1/conversations", params={"user_id": "acct_0b9f7c1e-1111-2222-3333-444455556666"})
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "bad",
    [
        token(exp_in=-10),
        token(key=ec.generate_private_key(ec.SECP256R1())),
        token(iss="https://evil.example/auth/v1"),
        token(aud="anon"),
        "not-a-jwt",
    ],
    ids=["expired", "wrong-key", "wrong-issuer", "wrong-audience", "garbage"],
)
def test_invalid_tokens_are_rejected(bad):
    resp = client.get("/api/v1/conversations", headers=bearer(bad))
    assert resp.status_code == 401
    assert "sign in again" in resp.json()["detail"]


def test_tokens_rejected_when_sign_in_is_not_configured(monkeypatch):
    monkeypatch.setattr(auth, "get_verifier", lambda: None)
    assert client.get("/api/v1/conversations", headers=bearer(token())).status_code == 401


def test_auth_required_mode_blocks_guests(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    assert client.get("/api/v1/conversations", params={"user_id": "guest1"}).status_code == 401
    assert client.get("/api/v1/conversations", headers=bearer(token())).status_code == 200


def test_public_config_exposes_only_public_values(monkeypatch):
    assert client.get("/api/v1/config").json() == {
        "auth": {"supabase_url": SUPABASE, "publishable_key": "sb_publishable_test", "required": False}
    }
    monkeypatch.setattr(settings, "supabase_url", "")
    assert client.get("/api/v1/config").json() == {"auth": None}


@patch("src.backend.llm.client.LLMClient.generate_response", return_value="Noted!")
def test_signing_in_moves_guest_data_into_the_account(_llm):
    guest = "guest-7f3a"
    chat = client.post("/api/v1/chat", json={"message": "hello there", "user_id": guest}).json()
    client.post("/api/v1/memories", params={"user_id": guest}, json={"fact": "Prefers dark mode"})
    client.post("/api/v1/reminders", json={"reminder_text": "Stretch", "scheduled_time": "2030-01-01T09:00",
                                           "user_id": guest})
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "Guest notes about the launch plan.")
    client.post("/api/v1/documents/upload", params={"user_id": guest},
                files={"file": ("notes.pdf", io.BytesIO(doc.write()), "application/pdf")})

    assert client.post("/api/v1/auth/claim", json={"guest_id": guest}).status_code == 401  # must be signed in
    claimed = client.post("/api/v1/auth/claim", json={"guest_id": guest}, headers=bearer(token())).json()
    assert claimed["moved"]["conversations"] == 1 and claimed["moved"]["memories"] == 1
    assert claimed["moved"]["reminders"] == 1 and claimed["moved"]["document_passages"] >= 1

    me = bearer(token())
    assert [c["id"] for c in client.get("/api/v1/conversations", headers=me).json()["conversations"]] == [
        chat["conversation_id"]
    ]
    assert [m["fact"] for m in client.get("/api/v1/memories", headers=me).json()["memories"]] == ["Prefers dark mode"]
    assert [r["reminder_text"] for r in client.get("/api/v1/reminders", headers=me).json()["reminders"]] == ["Stretch"]
    assert client.get("/api/v1/documents", headers=me).json()["documents"][0]["document_name"] == "notes.pdf"
    # Nothing is left behind under the guest id
    assert client.get("/api/v1/conversations", params={"user_id": guest}).json()["conversations"] == []

    bad = client.post("/api/v1/auth/claim", json={"guest_id": "acct_someone"}, headers=me)
    assert bad.status_code == 400
