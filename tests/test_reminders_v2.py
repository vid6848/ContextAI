"""Tests for natural-language reminder times, due notifications and reminders created from chat."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src.backend.core.config import settings
from src.backend.main import app
from src.backend.reminders.reminder_manager import ReminderManager
from src.backend.reminders.timeparse import parse_when

client = TestClient(app)
TZ = "Asia/Kolkata"  # UTC+5:30
NOW = datetime(2026, 10, 23, 10, 0, tzinfo=UTC)  # 15:30 in Kolkata, a Friday


def local(dt):
    return dt.astimezone(ZoneInfo(TZ))


@pytest.mark.parametrize(
    ("phrase", "expected_local"),
    [
        ("tomorrow at 5pm", "2026-10-24 17:00"),
        ("in 2 hours", "2026-10-23 17:30"),
        ("tonight", "2026-10-23 20:00"),
        ("at 6pm", "2026-10-23 18:00"),       # today's 6pm is still ahead
        ("at 6", "2026-10-23 18:00"),          # a bare 1-7 means pm
        ("next friday 9am", "2026-10-30 09:00"),
        ("Monday morning", "2026-10-26 09:00"),
        ("2026-12-01T10:00", "2026-12-01 10:00"),
    ],
)
def test_natural_language_times_resolve_in_the_users_timezone(phrase, expected_local):
    due = parse_when(phrase, TZ, now=NOW)
    assert local(due).strftime("%Y-%m-%d %H:%M") == expected_local
    assert due.tzinfo is not None


def test_unparseable_times_and_unknown_timezones():
    assert parse_when("gibberish xyz", TZ, now=NOW) is None
    assert parse_when("2026-12-01 10:00", "Not/AZone", now=NOW) == datetime(2026, 12, 1, 10, 0, tzinfo=UTC)


def test_due_reminders_are_returned_once(tmp_path):
    mgr = ReminderManager(db_path=str(tmp_path / "r.db"))
    past = mgr.create_reminder("u", "Stretch", (datetime.now(UTC) - timedelta(minutes=1)).isoformat())
    mgr.create_reminder("u", "Later", (datetime.now(UTC) + timedelta(days=1)).isoformat())

    assert [r["id"] for r in mgr.get_due("u")] == [past["id"]]
    assert mgr.mark_notified(past["id"], "u")
    assert mgr.get_due("u") == []
    assert not mgr.mark_notified(past["id"], "someone-else")


def test_bad_time_is_a_clear_error(tmp_path):
    mgr = ReminderManager(db_path=str(tmp_path / "r.db"))
    with pytest.raises(ValueError, match="Couldn't understand when"):
        mgr.create_reminder("u", "Call mom", "whenever-ish")


def test_legacy_reminders_table_is_migrated(tmp_path):
    db = tmp_path / "legacy.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, "
            "reminder_text TEXT NOT NULL, scheduled_time TEXT NOT NULL, created_at TEXT NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'pending')"
        )
        conn.execute(
            "INSERT INTO reminders (user_id, reminder_text, scheduled_time, created_at) VALUES ('u','Old','5pm','t')"
        )
    mgr = ReminderManager(db_path=str(db))
    mgr.create_reminder("u", "New", "2030-01-01T09:00")
    assert [r["reminder_text"] for r in mgr.get_reminders("u")] == ["New", "Old"]


def test_api_natural_language_creation_due_and_notified():
    created = client.post("/api/v1/reminders", json={
        "reminder_text": "Water plants", "scheduled_time": "in 1 hour", "timezone": TZ, "user_id": "api1"
    }).json()["reminder"]
    assert created["due_at"] and created["timezone"] == TZ

    bad = client.post("/api/v1/reminders", json={"reminder_text": "x", "scheduled_time": "soonish", "user_id": "api1"})
    assert bad.status_code == 400 and "Couldn't understand" in bad.json()["detail"]

    overdue = client.post("/api/v1/reminders", json={
        "reminder_text": "Stand up", "scheduled_time": "2020-01-01T09:00", "user_id": "api1"
    }).json()["reminder"]
    due = client.get("/api/v1/reminders/due", params={"user_id": "api1"}).json()["reminders"]
    assert [r["id"] for r in due] == [overdue["id"]]
    assert client.patch(f"/api/v1/reminders/{overdue['id']}/notified", params={"user_id": "api1"}).status_code == 200
    assert client.get("/api/v1/reminders/due", params={"user_id": "api1"}).json()["reminders"] == []


def test_model_can_create_and_list_reminders_from_chat(monkeypatch):
    monkeypatch.setattr(settings, "router_mode", "llm")
    rounds = iter([
        [{"id": "r1", "type": "function", "function": {
            "name": "create_reminder", "arguments": json.dumps({"text": "Call mom", "when": "2030-05-01T18:00"})}}],
        "Done, I'll remind you.",
    ])
    seen = []

    def fake_round(messages, tools=None, cancel_event=None):
        seen.append(messages)
        reply = next(rounds)
        if isinstance(reply, str):
            yield ("token", reply)
            yield ("message", {"role": "assistant", "content": reply})
        else:
            yield ("message", {"role": "assistant", "content": None, "tool_calls": reply})

    with patch("src.backend.llm.client.LLMClient.chat_round", side_effect=fake_round):
        events = []
        with client.stream("POST", "/api/v1/chat/stream", json={
            "message": "Remind me to call mom on May 1 2030 at 6pm", "user_id": "chat1", "timezone": TZ
        }) as r:
            name = None
            for line in r.iter_lines():
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: "):
                    events.append((name, json.loads(line[6:])))

    assert "Asia/Kolkata" in seen[0][0]["content"]  # the model is told the user's local time and zone
    done = next(d for n, d in events if n == "done")
    [card] = done["cards"]
    assert card["tool"] == "reminder" and card["output"]["text"] == "Call mom"
    assert card["output"]["due_at"].startswith("2030-05-01T12:30")  # 18:00 IST in UTC
    assert card["output"]["due_local"] == "Wednesday 01 May 2030, 18:00"  # what the model is told

    reminders = client.get("/api/v1/reminders", params={"user_id": "chat1"}).json()["reminders"]
    assert [(r["reminder_text"], r["timezone"]) for r in reminders] == [("Call mom", TZ)]
