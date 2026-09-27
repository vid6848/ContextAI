"""SQLite conversation memory manager for ContextAI."""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any
from src.backend.core.config import settings


class SQLiteManager:
    """Manages short-term conversation history stored in SQLite."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path if db_path is not None else settings.sqlite_db_path
        self._ensure_dir()
        self.init_db()

    def _ensure_dir(self) -> None:
        """Ensure parent directory for database exists if db_path is a filesystem path."""
        if self.db_path and self.db_path != ":memory:":
            dirname = os.path.dirname(os.path.abspath(self.db_path))
            if dirname:
                os.makedirs(dirname, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Get an SQLite connection with row factory enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Initialize database schema with conversation_history table."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conv_user_timestamp
                ON conversation_history(user_id, timestamp);
                """
            )
            conn.commit()

    def save_message(
        self,
        user_id: str,
        role: str,
        message: str,
        timestamp: str | None = None,
    ) -> int:
        """Save a conversation message (user or assistant) for a user.

        Returns the inserted row id.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversation_history (user_id, role, message, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, role, message, timestamp),
            )
            conn.commit()
            return cursor.lastrowid

    def get_recent_messages(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve recent conversation history for a user, sorted chronologically.

        Only messages for the specified user_id are returned to ensure isolation.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, user_id, role, message, timestamp
                FROM conversation_history
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = cursor.fetchall()
            # Reverse so that oldest is first and newest is last (chronological)
            messages = [dict(row) for row in reversed(rows)]
            return messages

    def clear_history(self, user_id: str | None = None) -> None:
        """Clear conversation history for a specific user, or all users if None."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if user_id is not None:
                cursor.execute(
                    "DELETE FROM conversation_history WHERE user_id = ?",
                    (user_id,),
                )
            else:
                cursor.execute("DELETE FROM conversation_history")
            conn.commit()
