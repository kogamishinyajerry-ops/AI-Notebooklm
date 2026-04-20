from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from limits.storage.base import Storage

from core.storage.sqlite_db import get_connection


_TABLE_NAME = "rate_limit_counters"
_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
    key TEXT PRIMARY KEY,
    value INTEGER NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{_TABLE_NAME}_expires_at
    ON {_TABLE_NAME}(expires_at);
"""
_CLEANUP_INTERVAL_SECONDS = 60.0


class SQLiteFixedWindowStorage(Storage):
    """Local SQLite storage for fixed-window chat rate limits.

    Only the fixed-window methods required by slowapi/limits are implemented.
    The table is created lazily inside the shared notebooks database so the
    change stays local-only and does not require a migration step.
    """

    STORAGE_SCHEME = ["sqlite+comac"]

    def __init__(
        self,
        db_path: str | Path,
        wrap_exceptions: bool = False,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._table_ready = False
        self._table_lock = threading.Lock()
        self._next_cleanup_at = 0.0
        super().__init__(str(self.db_path), wrap_exceptions=wrap_exceptions)

    @property
    def base_exceptions(self) -> type[Exception] | tuple[type[Exception], ...]:
        return sqlite3.Error

    def incr(
        self,
        key: str,
        expiry: int,
        elastic_expiry: bool = False,
        amount: int = 1,
    ) -> int:
        now = time.time()
        conn = get_connection(self.db_path)
        try:
            self._ensure_table(conn)
            self._maybe_cleanup(conn, now)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                f"SELECT value, expires_at FROM {_TABLE_NAME} WHERE key = ?",
                (key,),
            ).fetchone()
            expires_at = now + float(expiry)

            if row is None or float(row["expires_at"]) <= now:
                value = amount
                conn.execute(
                    f"""
                    INSERT INTO {_TABLE_NAME} (key, value, expires_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        expires_at = excluded.expires_at
                    """,
                    (key, value, expires_at),
                )
            else:
                value = int(row["value"]) + amount
                if not elastic_expiry:
                    expires_at = float(row["expires_at"])
                conn.execute(
                    f"""
                    UPDATE {_TABLE_NAME}
                    SET value = ?, expires_at = ?
                    WHERE key = ?
                    """,
                    (value, expires_at, key),
                )

            conn.commit()
            return value
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    def get(self, key: str) -> int:
        now = time.time()
        conn = get_connection(self.db_path)
        try:
            self._ensure_table(conn)
            self._maybe_cleanup(conn, now)
            row = conn.execute(
                f"SELECT value, expires_at FROM {_TABLE_NAME} WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return 0
            if float(row["expires_at"]) <= now:
                conn.execute(
                    f"DELETE FROM {_TABLE_NAME} WHERE key = ? AND expires_at <= ?",
                    (key, now),
                )
                conn.commit()
                return 0
            return int(row["value"])
        finally:
            conn.close()

    def get_expiry(self, key: str) -> float:
        now = time.time()
        conn = get_connection(self.db_path)
        try:
            self._ensure_table(conn)
            row = conn.execute(
                f"SELECT expires_at FROM {_TABLE_NAME} WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return now
            expires_at = float(row["expires_at"])
            if expires_at <= now:
                conn.execute(
                    f"DELETE FROM {_TABLE_NAME} WHERE key = ? AND expires_at <= ?",
                    (key, now),
                )
                conn.commit()
                return now
            return expires_at
        finally:
            conn.close()

    def check(self) -> bool:
        conn = get_connection(self.db_path)
        try:
            self._ensure_table(conn)
            conn.execute("SELECT 1").fetchone()
            return True
        finally:
            conn.close()

    def reset(self) -> Optional[int]:
        conn = get_connection(self.db_path)
        try:
            self._ensure_table(conn)
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {_TABLE_NAME}").fetchone()
            conn.execute(f"DELETE FROM {_TABLE_NAME}")
            conn.commit()
            return int(row["count"]) if row is not None else 0
        finally:
            conn.close()

    def clear(self, key: str) -> None:
        conn = get_connection(self.db_path)
        try:
            self._ensure_table(conn)
            conn.execute(f"DELETE FROM {_TABLE_NAME} WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()

    def _ensure_table(self, conn: sqlite3.Connection) -> None:
        if self._table_ready:
            return
        with self._table_lock:
            if self._table_ready:
                return
            conn.executescript(_TABLE_SQL)
            conn.commit()
            self._table_ready = True

    def _maybe_cleanup(self, conn: sqlite3.Connection, now: float) -> None:
        if now < self._next_cleanup_at:
            return
        with self.lock:
            if now < self._next_cleanup_at:
                return
            conn.execute(
                f"DELETE FROM {_TABLE_NAME} WHERE expires_at <= ?",
                (now,),
            )
            conn.commit()
            self._next_cleanup_at = now + _CLEANUP_INTERVAL_SECONDS
