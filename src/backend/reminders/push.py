"""Web Push for due reminders: notifications arrive even when no ContextAI tab is open."""

import base64
import json
import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid, Vapid01
from pywebpush import WebPushException, webpush

from src.backend.core.config import settings
from src.backend.db import Database
from src.backend.reminders.reminder_manager import ReminderManager

logger = logging.getLogger(__name__)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class VapidKeys:
    """VAPID keys identify this server to browsers' push services.

    Taken from settings when provided (recommended in production, so subscriptions survive redeploys);
    otherwise generated once and kept next to the database.
    """

    def __init__(self, data_dir: str) -> None:
        if settings.vapid_private_key and settings.vapid_public_key:
            self.private_pem = settings.vapid_private_key.replace("\\n", "\n")
            self.public_key = settings.vapid_public_key
            return
        path = os.path.join(data_dir, "vapid.json")
        if os.path.exists(path):
            with open(path) as fh:
                stored = json.load(fh)
            self.private_pem, self.public_key = stored["private_pem"], stored["public_key"]
            return
        vapid = Vapid01()
        vapid.generate_keys()
        self.private_pem = vapid.private_pem().decode()
        self.public_key = _b64url(
            vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        )
        os.makedirs(data_dir, exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"private_pem": self.private_pem, "public_key": self.public_key}, fh)
        os.chmod(path, 0o600)


def _signer(keys: "VapidKeys") -> Vapid01:
    # pywebpush reads a *string* key as base64 DER, not PEM, so hand it a ready Vapid instance instead
    return Vapid.from_pem(keys.private_pem.encode())


class PushService:
    """Stores browser push subscriptions and delivers due reminders to them."""

    def __init__(self, db_path: str | None = None, reminders: ReminderManager | None = None) -> None:
        self.db_path = db_path or settings.database_url or settings.sqlite_db_path
        self.db = Database(self.db_path)
        self.reminders = reminders or ReminderManager(self.db_path)
        # Generated keys live beside the local data; in production set VAPID_* so they survive redeploys
        local_db = settings.sqlite_db_path if self.db.kind == "postgres" else self.db_path
        self.keys = VapidKeys(os.path.dirname(os.path.abspath(local_db)))
        self.signer = _signer(self.keys)
        if self.db.kind != "sqlite":
            return  # Postgres: table comes from db/schema.sql
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    endpoint TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _conn(self):
        return self.db.connect()

    def subscribe(self, user_id: str, subscription: dict[str, Any]) -> None:
        keys = subscription.get("keys") or {}
        valid_endpoint = subscription.get("endpoint", "").startswith("https://")
        if not valid_endpoint or not keys.get("p256dh") or not keys.get("auth"):
            raise ValueError("Invalid push subscription.")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO push_subscriptions (endpoint, user_id, p256dh, auth, created_at) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET user_id = excluded.user_id, p256dh = excluded.p256dh,
                    auth = excluded.auth
                """,
                (subscription["endpoint"], user_id, keys["p256dh"], keys["auth"], datetime.now(UTC).isoformat()),
            )

    def unsubscribe(self, endpoint: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))

    def reassign_user(self, old_user_id: str, new_user_id: str) -> int:
        with self._conn() as conn:
            return conn.execute(
                "UPDATE push_subscriptions SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id)
            ).rowcount

    def subscriptions(self, user_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM push_subscriptions WHERE user_id = ?", (user_id,)).fetchall()
        return rows

    def deliver_due(self, now: datetime | None = None) -> int:
        """Push every due, un-notified reminder to its owner's devices. Returns how many reminders were pushed.

        A reminder is marked notified only if at least one device accepted it; users without push keep
        getting the in-app toast instead. Subscriptions the push service reports as gone are removed.
        """
        delivered = 0
        for reminder in self.reminders.get_all_due(now):
            payload = json.dumps({
                "title": "ContextAI reminder",
                "body": reminder["reminder_text"],
                "tag": f"reminder-{reminder['id']}",
                "url": "/chat",
            })
            sent = False
            for sub in self.subscriptions(reminder["user_id"]):
                try:
                    webpush(
                        subscription_info={
                            "endpoint": sub["endpoint"],
                            "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                        },
                        data=payload,
                        vapid_private_key=self.signer,
                        vapid_claims={"sub": settings.vapid_contact},
                        ttl=3600,
                    )
                    sent = True
                except WebPushException as err:
                    status = getattr(err.response, "status_code", None)
                    if status in (404, 410):
                        self.unsubscribe(sub["endpoint"])
                    else:
                        logger.warning("Push to %s failed: %s", sub["endpoint"][:40], status or err)
            if sent:
                self.reminders.mark_notified(reminder["id"], reminder["user_id"])
                delivered += 1
        return delivered


def start_push_loop(service: PushService, interval: float = 30.0) -> threading.Event:
    """Deliver due reminders every `interval` seconds in a daemon thread. Set the returned event to stop."""
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(interval):
            try:
                service.deliver_due()
            except Exception:
                logger.exception("Reminder push loop failed")

    threading.Thread(target=loop, name="reminder-push", daemon=True).start()
    return stop
