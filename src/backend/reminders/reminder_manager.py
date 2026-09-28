"""Reminder manager using SQLite persistence."""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any
from src.backend.core.config import settings


class ReminderManager:
    """Manages user reminders stored in SQLite."""

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
        """Initialize reminders table schema."""
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
                    status TEXT NOT NULL DEFAULT 'pending'
                );
                """
            )
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
    ) -> dict[str, Any]:
        """Create a new reminder for a user."""
        text = reminder_text.strip()
        if not text:
            raise ValueError("Reminder text cannot be empty.")
        if not user_id.strip():
            raise ValueError("User ID cannot be empty.")
        if not scheduled_time.strip():
            raise ValueError("Scheduled time cannot be empty.")

        created_at = datetime.now(timezone.utc).isoformat()
        status = "pending"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO reminders (user_id, reminder_text, scheduled_time, created_at, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id.strip(), text, scheduled_time.strip(), created_at, status),
            )
            conn.commit()
            reminder_id = cursor.lastrowid

        return {
            "id": reminder_id,
            "user_id": user_id.strip(),
            "reminder_text": text,
            "scheduled_time": scheduled_time.strip(),
            "created_at": created_at,
            "status": status,
        }

    def get_reminders(
        self,
        user_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve reminders for a given user, optionally filtered by status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    """
                    SELECT id, user_id, reminder_text, scheduled_time, created_at, status
                    FROM reminders
                    WHERE user_id = ? AND status = ?
                    ORDER BY scheduled_time ASC, id ASC
                    """,
                    (user_id, status),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, user_id, reminder_text, scheduled_time, created_at, status
                    FROM reminders
                    WHERE user_id = ?
                    ORDER BY status DESC, scheduled_time ASC, id ASC
                    """,
                    (user_id,),
                )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

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
