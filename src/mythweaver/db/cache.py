from __future__ import annotations

from contextlib import closing
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class SQLiteCache:
    """Small JSON cache used for Modrinth metadata and deterministic tool runs."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_schema(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cache_entries (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        expires_at REAL NOT NULL,
                        created_at REAL NOT NULL
                    )
                    """
                )

    def get_json(self, key: str) -> dict[str, Any] | list[Any] | str | int | float | bool | None:
        now = time.time()
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT value, expires_at FROM cache_entries WHERE key = ?",
                    (key,),
                ).fetchone()
                if not row:
                    return None
                value, expires_at = row
                if expires_at < now:
                    connection.execute("DELETE FROM cache_entries WHERE key = ?", (key,))
                    return None
                return json.loads(value)

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        now = time.time()
        expires_at = now + ttl_seconds
        payload = json.dumps(value, sort_keys=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO cache_entries(key, value, expires_at, created_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        expires_at = excluded.expires_at,
                        created_at = excluded.created_at
                    """,
                    (key, payload, expires_at, now),
                )

    def purge_expired(self) -> int:
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM cache_entries WHERE expires_at < ?",
                    (time.time(),),
                )
                return cursor.rowcount
