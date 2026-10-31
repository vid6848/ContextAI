"""Conversations and message history, stored in SQLite locally or Postgres (Supabase) in production."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from src.backend.core.config import settings
from src.backend.db import Database, decode_json

DEFAULT_CONVERSATION_TITLE = "New conversation"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteManager:
    """Manages conversations and their message history.

    `db_path` is a SQLite file or a Postgres URL; by default DATABASE_URL when set, else the local file.
    (The name predates Postgres support.)
    """

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path if db_path is not None else (settings.database_url or settings.sqlite_db_path)
        self.db = Database(self.db_path)
        self.init_db()

    def get_connection(self):
        """A connection in a transaction (committed when the `with` block exits)."""
        return self.db.connect()

    def init_db(self) -> None:
        """Create the SQLite schema and migrate older files. Postgres uses db/schema.sql instead."""
        if self.db.kind != "sqlite":
            return
        with self.get_connection() as cursor:
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
        return conversation

    def get_conversation(self, conversation_id: str, user_id: str) -> dict[str, Any] | None:
        """Return a conversation if it exists and belongs to the user."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT id, user_id, title, created_at, updated_at FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
        return row

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
        return rows

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
            cursor = conn.execute(
                """
                INSERT INTO conversation_history (user_id, role, message, timestamp, conversation_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, role, message, timestamp, conversation_id, json.dumps(metadata) if metadata else None),
                returning_id=True,
            )
            if conversation_id:
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ? AND user_id = ?",
                    (timestamp, conversation_id, user_id),
                )
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
            return list(reversed(rows))

    def latest_attachments(self, conversation_id: str, user_id: str) -> list[str]:
        """The files attached to the most recent user message that had any, so follow-ups stay on them."""
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT metadata FROM conversation_history
                WHERE conversation_id = ? AND user_id = ? AND role = 'user' AND metadata IS NOT NULL
                ORDER BY id DESC LIMIT 10
                """,
                (conversation_id, user_id),
            ).fetchall()
        for row in rows:
            if attachments := (decode_json(row["metadata"]) or {}).get("attachments"):
                return list(attachments)
        return []

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
            item = row
            item["metadata"] = decode_json(item["metadata"]) or None
            messages.append(item)
        return messages

    def get_message(self, message_id: int, conversation_id: str, user_id: str) -> dict[str, Any] | None:
        """Return one message of a conversation, or None if it doesn't belong to it."""
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, role, message, timestamp, metadata
                FROM conversation_history
                WHERE id = ? AND conversation_id = ? AND user_id = ?
                """,
                (message_id, conversation_id, user_id),
            ).fetchone()
        if row is not None:
            row["metadata"] = decode_json(row["metadata"]) or None
        return row

    def update_message_metadata(
        self, message_id: int, conversation_id: str, user_id: str, changes: dict[str, Any]
    ) -> bool:
        """Merge keys into a message's metadata (a None value removes the key). False if not found."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT metadata FROM conversation_history WHERE id = ? AND conversation_id = ? AND user_id = ?",
                (message_id, conversation_id, user_id),
            ).fetchone()
            if row is None:
                return False
            metadata = decode_json(row["metadata"]) or {}
            for key, value in changes.items():
                if value is None:
                    metadata.pop(key, None)
                else:
                    metadata[key] = value
            conn.execute(
                "UPDATE conversation_history SET metadata = ? WHERE id = ?",
                (json.dumps(metadata) if metadata else None, message_id),
            )
            return True

    def delete_messages_from(self, message_id: int, conversation_id: str, user_id: str) -> int:
        """Delete a message and everything after it in a conversation (used by edit and regenerate)."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM conversation_history WHERE conversation_id = ? AND user_id = ? AND id >= ?",
                (conversation_id, user_id, message_id),
            )
            return cursor.rowcount

    def reassign_user(self, old_user_id: str, new_user_id: str) -> int:
        """Move a guest's conversations to their account. Returns how many conversations moved."""
        with self.get_connection() as conn:
            moved = conn.execute("UPDATE conversations SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
            conn.execute("UPDATE conversation_history SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id))
            return moved.rowcount

    def clear_history(self, user_id: str | None = None) -> None:
        """Clear conversations and history for a specific user, or all users if None."""
        with self.get_connection() as conn:
            if user_id is not None:
                conn.execute("DELETE FROM conversation_history WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
            else:
                conn.execute("DELETE FROM conversation_history")
                conn.execute("DELETE FROM conversations")
