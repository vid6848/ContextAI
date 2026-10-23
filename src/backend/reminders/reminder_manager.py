"""Reminder manager, stored in SQLite locally or Postgres (Supabase) in production."""

from datetime import UTC, datetime
from typing import Any

from src.backend.core.config import settings
from src.backend.db import Database
from src.backend.reminders.timeparse import parse_when

COLUMNS = "id, user_id, reminder_text, scheduled_time, created_at, status, due_at, timezone, notified_at"


class ReminderManager:
    """Manages user reminders stored in SQLite.

    `scheduled_time` keeps what the user (or the model) asked for; `due_at` is the resolved moment in UTC,
    which drives ordering and notifications.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path if db_path is not None else (settings.database_url or settings.sqlite_db_path)
        self.db = Database(self.db_path)
        self.init_db()

    def get_connection(self):
        """A connection in a transaction (committed when the `with` block exits)."""
        return self.db.connect()

    def init_db(self) -> None:
        """Create the SQLite table, adding newer columns to older files. Postgres uses db/schema.sql."""
        if self.db.kind != "sqlite":
            return
        with self.get_connection() as cursor:
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
                returning_id=True,
            )
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
        query += " ORDER BY status DESC, due_at IS NULL, due_at ASC, id ASC"
        with self.get_connection() as conn:
            return conn.execute(query, params).fetchall()

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
        return rows

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
        return rows

    def mark_notified(self, reminder_id: int, user_id: str) -> bool:
        """Record that the user was notified, so each reminder alerts once."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE reminders SET notified_at = ? WHERE id = ? AND user_id = ?",
                (datetime.now(UTC).isoformat(), reminder_id, user_id),
            )
            return cursor.rowcount > 0

    def reassign_user(self, old_user_id: str, new_user_id: str) -> int:
        with self.get_connection() as conn:
            return conn.execute(
                "UPDATE reminders SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id)
            ).rowcount

    def complete_reminder(self, reminder_id: int, user_id: str | None = None) -> bool:
        """Mark a reminder as completed."""
        with self.get_connection() as conn:
            if user_id:
                cursor = conn.execute(
                    "UPDATE reminders SET status = 'completed' WHERE id = ? AND user_id = ?",
                    (reminder_id, user_id),
                )
            else:
                cursor = conn.execute(
                    "UPDATE reminders SET status = 'completed' WHERE id = ?",
                    (reminder_id,),
                )
            return cursor.rowcount > 0

    def delete_reminder(self, reminder_id: int, user_id: str | None = None) -> bool:
        """Delete a reminder by ID."""
        with self.get_connection() as conn:
            if user_id:
                cursor = conn.execute(
                    "DELETE FROM reminders WHERE id = ? AND user_id = ?",
                    (reminder_id, user_id),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM reminders WHERE id = ?",
                    (reminder_id,),
                )
            return cursor.rowcount > 0
