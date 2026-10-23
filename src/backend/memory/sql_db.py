"""SQLite conversation memory manager for ContextAI."""

import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from src.backend.core.config import settings

DEFAULT_CONVERSATION_TITLE = "New conversation"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteManager:
    """Manages conversations and their message history stored in SQLite."""

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
        """Initialize schema and migrate older databases that predate conversations."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
                ON conversations(user_id, updated_at);
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    conversation_id TEXT,
                    metadata TEXT
                );
                """
            )
            # Databases created before conversations existed lack these columns
            existing = {row["name"] for row in cursor.execute("PRAGMA table_info(conversation_history)")}
            if "conversation_id" not in existing:
                cursor.execute("ALTER TABLE conversation_history ADD COLUMN conversation_id TEXT")
            if "metadata" not in existing:
                cursor.execute("ALTER TABLE conversation_history ADD COLUMN metadata TEXT")
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conv_user_timestamp
                ON conversation_history(user_id, timestamp);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conv_conversation
                ON conversation_history(conversation_id, id);
                """
            )
            conn.commit()

    # ------------------------------------------------------------------ conversations

    def create_conversation(self, user_id: str, title: str | None = None) -> dict[str, Any]:
        """Create a new conversation for a user."""
        now = _now()
        conversation = {
            "id": uuid.uuid4().hex,
            "user_id": user_id,
            "title": (title or "").strip() or DEFAULT_CONVERSATION_TITLE,
            "created_at": now,
            "updated_at": now,
        }
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, user_id, title, created_at, updated_at)
                VALUES (:id, :user_id, :title, :created_at, :updated_at)
                """,
                conversation,
            )
            conn.commit()
        return conversation

    def get_conversation(self, conversation_id: str, user_id: str) -> dict[str, Any] | None:
        """Return a conversation if it exists and belongs to the user."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT id, user_id, title, created_at, updated_at FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def list_conversations(self, user_id: str) -> list[dict[str, Any]]:
        """List a user's conversations, most recently active first."""
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, user_id, title, created_at, updated_at
                FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def rename_conversation(self, conversation_id: str, user_id: str, title: str) -> bool:
        """Rename a conversation. Returns False if it does not exist for this user."""
        clean = title.strip()
        if not clean:
            raise ValueError("Title cannot be empty.")
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?",
                (clean, conversation_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Delete a conversation and its messages. Returns False if not found for this user."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            if cursor.rowcount == 0:
                return False
            conn.execute(
                "DELETE FROM conversation_history WHERE conversation_id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            conn.commit()
            return True

    # ------------------------------------------------------------------ messages

    def save_message(
        self,
        user_id: str,
        role: str,
        message: str,
        timestamp: str | None = None,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Save a conversation message (user or assistant) for a user.

        Returns the inserted row id.
        """
        if timestamp is None:
            timestamp = _now()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversation_history (user_id, role, message, timestamp, conversation_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, role, message, timestamp, conversation_id, json.dumps(metadata) if metadata else None),
            )
            if conversation_id:
                cursor.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ? AND user_id = ?",
                    (timestamp, conversation_id, user_id),
                )
            conn.commit()
            return cursor.lastrowid

    def get_recent_messages(
        self,
        user_id: str,
        limit: int = 10,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve recent history for a user, sorted chronologically.

        When conversation_id is given, only that conversation's messages are returned.
        """
        query = "SELECT id, user_id, role, message, timestamp FROM conversation_history WHERE user_id = ?"
        params: list[Any] = [user_id]
        if conversation_id is not None:
            query += " AND conversation_id = ?"
            params.append(conversation_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            # Reverse so that oldest is first and newest is last (chronological)
            return [dict(row) for row in reversed(rows)]

    def get_conversation_messages(self, conversation_id: str, user_id: str) -> list[dict[str, Any]]:
        """Return every message in a conversation, oldest first, with decoded metadata."""
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, role, message, timestamp, metadata
                FROM conversation_history
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY id ASC
                """,
                (conversation_id, user_id),
            ).fetchall()
        messages = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"]) if item["metadata"] else None
            messages.append(item)
        return messages

    def clear_history(self, user_id: str | None = None) -> None:
        """Clear conversations and history for a specific user, or all users if None."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if user_id is not None:
                cursor.execute("DELETE FROM conversation_history WHERE user_id = ?", (user_id,))
                cursor.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("DELETE FROM conversation_history")
                cursor.execute("DELETE FROM conversations")
            conn.commit()
