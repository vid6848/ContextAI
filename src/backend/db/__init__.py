"""One relational-database interface over SQLite (local/dev) and Postgres (Supabase in production).

Stores write SQL once, with SQLite-style placeholders (`?` and `:name`); for Postgres they're rewritten
to psycopg's (`%s`, `%(name)s`). Rows always come back as plain dicts with timestamps as ISO strings, so
callers behave identically on both engines.
"""

import atexit
import json
import os
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
_POSITIONAL = re.compile(r"\?")
_NAMED = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")


def is_postgres_url(target: str) -> bool:
    return target.startswith(("postgres://", "postgresql://"))


def _to_psycopg(sql: str) -> str:
    sql = sql.replace("%", "%%")
    return _NAMED.sub(r"%(\1)s", _POSITIONAL.sub("%s", sql))


def _plain(row: dict[str, Any]) -> dict[str, Any]:
    """Postgres returns datetimes; SQLite stores ISO text. Normalise to ISO strings."""
    return {k: v.isoformat() if isinstance(v, datetime | date) else v for k, v in row.items()}


def decode_json(value: Any) -> Any:
    """JSON columns: text on SQLite, already-decoded jsonb on Postgres."""
    if value is None or not isinstance(value, str | bytes):
        return value
    return json.loads(value)


class Result:
    def __init__(self, rows: list[dict[str, Any]], rowcount: int, lastrowid: Any = None) -> None:
        self._rows = rows
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._rows)

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class Connection:
    def __init__(self, raw: Any, kind: str) -> None:
        self.raw = raw
        self.kind = kind

    def execute(self, sql: str, params: Any = (), returning_id: bool = False) -> Result:
        """Run one statement. With returning_id=True on an INSERT, lastrowid holds the new row's id."""
        if self.kind == "sqlite":
            cur = self.raw.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()] if cur.description else []
            return Result(rows, cur.rowcount, cur.lastrowid)
        if returning_id:
            sql = f"{sql.rstrip().rstrip(';')} RETURNING id"
        cur = self.raw.execute(_to_psycopg(sql), params or None)
        rows = [_plain(r) for r in cur.fetchall()] if cur.description else []
        return Result(rows, cur.rowcount, rows[0]["id"] if returning_id and rows else None)


class Database:
    """A SQLite file or a Postgres URL. Postgres connections come from a small pool and get the schema."""

    _pools: dict[str, Any] = {}
    _lock = threading.Lock()

    def __init__(self, target: str) -> None:
        self.target = target
        self.kind = "postgres" if is_postgres_url(target) else "sqlite"
        if self.kind == "sqlite" and target != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(target)) or ".", exist_ok=True)
        if self.kind == "postgres":
            self._pool()

    def _pool(self) -> Any:
        with Database._lock:
            pool = Database._pools.get(self.target)
            if pool is None:
                from psycopg.rows import dict_row
                from psycopg_pool import ConnectionPool

                def configure(conn: Any) -> None:
                    # pgvector lives in the "extensions" schema on Supabase; UTC keeps ISO strings sortable
                    conn.execute("SET search_path = public, extensions")
                    conn.execute("SET TIME ZONE 'UTC'")
                    conn.commit()

                pool = ConnectionPool(
                    self.target,
                    min_size=1,
                    max_size=int(os.environ.get("DB_POOL_SIZE", "8")),
                    # prepare_threshold=None keeps it compatible with Supabase's transaction pooler
                    kwargs={"row_factory": dict_row, "prepare_threshold": None},
                    configure=configure,
                    open=True,
                )
                with pool.connection() as conn:
                    conn.execute(SCHEMA_FILE.read_text())
                Database._pools[self.target] = pool
            return pool

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        """A connection inside a transaction: committed on success, rolled back on error."""
        if self.kind == "sqlite":
            raw = sqlite3.connect(self.target)
            raw.row_factory = sqlite3.Row
            try:
                with raw:
                    yield Connection(raw, "sqlite")
            finally:
                raw.close()
        else:
            with self._pool().connection() as raw:
                yield Connection(raw, "postgres")

    @classmethod
    def close_all(cls) -> None:
        with cls._lock:
            for pool in cls._pools.values():
                pool.close()
            cls._pools.clear()


atexit.register(Database.close_all)
