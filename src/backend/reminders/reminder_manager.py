"""Reminder manager using SQLite persistence."""

import os
import sqlite3
from datetime import UTC, datetime
from typing import Any

from src.backend.core.config import settings
from src.backend.reminders.timeparse import parse_when

COLUMNS = "id, user_id, reminder_text, scheduled_time, created_at, status, due_at, timezone, notified_at"


class ReminderManager:
    """Manages user reminders stored in SQLite.

    `scheduled_time` keeps what the user (or the model) asked for; `due_at` is the resolved moment in UTC,
    which drives ordering and notifications.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path if db_path is not None else settings.sqlite_db_path
        self._ensure_dir()
        self.init_db()

    def _ensure_dir(self) -> None:
        """Ensure database parent directory exists."""
        if self.db_path and self.db_path != ":memory:":
            dirname = os.path.dirname(os.path.abspath(self.db_path))
            if dirname:
                os.makedirs(dirname, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Return an SQLite connection with row factory enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Initialize the reminders table, adding newer columns to databases that predate them."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    reminder_text TEXT NOT NULL,
                    scheduled_time TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    due_at TEXT,
                    timezone TEXT,
                    notified_at TEXT
                );
                """
            )
            existing = {row["name"] for row in cursor.execute("PRAGMA table_info(reminders)")}
            for column in ("due_at", "timezone", "notified_at"):
                if column not in existing:
                    cursor.execute(f"ALTER TABLE reminders ADD COLUMN {column} TEXT")
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reminders_user_status
                ON reminders(user_id, status);
                """
            )
            conn.commit()

    def create_reminder(
        self,
        user_id: str,
        reminder_text: str,
        scheduled_time: str,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """Create a reminder. `scheduled_time` may be ISO or natural language ("tomorrow at 5pm")."""
        text = reminder_text.strip()
        if not text:
            raise ValueError("Reminder text cannot be empty.")
        if not user_id.strip():
            raise ValueError("User ID cannot be empty.")
        if not scheduled_time.strip():
            raise ValueError("Scheduled time cannot be empty.")

        due = parse_when(scheduled_time, timezone)
        if due is None:
            raise ValueError(f'Couldn\'t understand when "{scheduled_time.strip()}" is. Try "tomorrow at 5pm".')

        created_at = datetime.now(UTC).isoformat()
        row = {
            "user_id": user_id.strip(),
            "reminder_text": text,
            "scheduled_time": scheduled_time.strip(),
            "created_at": created_at,
            "status": "pending",
            "due_at": due.isoformat(),
            "timezone": timezone,
            "notified_at": None,
        }
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reminders (user_id, reminder_text, scheduled_time, created_at, status, due_at, timezone)
                VALUES (:user_id, :reminder_text, :scheduled_time, :created_at, :status, :due_at, :timezone)
                """,
                row,
            )
            conn.commit()
            return {"id": cursor.lastrowid, **row}

    def get_reminders(
        self,
        user_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve reminders for a user, soonest first (pending before completed), optionally by status."""
        query = f"SELECT {COLUMNS} FROM reminders WHERE user_id = ?"
        params: list[Any] = [user_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY status DESC, COALESCE(due_at, scheduled_time) ASC, id ASC"
        with self.get_connection() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def get_due(self, user_id: str, now: datetime | None = None) -> list[dict[str, Any]]:
        """Pending reminders whose time has come and that haven't been notified yet."""
        moment = (now or datetime.now(UTC)).isoformat()
        with self.get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {COLUMNS} FROM reminders
                WHERE user_id = ? AND status = 'pending' AND notified_at IS NULL AND due_at IS NOT NULL AND due_at <= ?
                ORDER BY due_at ASC
                """,
                (user_id, moment),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_all_due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        """Due, un-notified pending reminders across all users (for the push scheduler)."""
        moment = (now or datetime.now(UTC)).isoformat()
        with self.get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT {COLUMNS} FROM reminders
                WHERE status = 'pending' AND notified_at IS NULL AND due_at IS NOT NULL AND due_at <= ?
                ORDER BY due_at ASC LIMIT 500
                """,
                (moment,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_notified(self, reminder_id: int, user_id: str) -> bool:
        """Record that the user was notified, so each reminder alerts once."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE reminders SET notified_at = ? WHERE id = ? AND user_id = ?",
                (datetime.now(UTC).isoformat(), reminder_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def complete_reminder(self, reminder_id: int, user_id: str | None = None) -> bool:
        """Mark a reminder as completed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute(
                    "UPDATE reminders SET status = 'completed' WHERE id = ? AND user_id = ?",
                    (reminder_id, user_id),
                )
            else:
                cursor.execute(
                    "UPDATE reminders SET status = 'completed' WHERE id = ?",
                    (reminder_id,),
                )
            conn.commit()
            return cursor.rowcount > 0

    def delete_reminder(self, reminder_id: int, user_id: str | None = None) -> bool:
        """Delete a reminder by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute(
                    "DELETE FROM reminders WHERE id = ? AND user_id = ?",
                    (reminder_id, user_id),
                )
            else:
                cursor.execute(
                    "DELETE FROM reminders WHERE id = ?",
                    (reminder_id,),
                )
            conn.commit()
            return cursor.rowcount > 0
