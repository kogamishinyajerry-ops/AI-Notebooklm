from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


logger = logging.getLogger("comac.governance.quota")

DEFAULT_UPLOAD_DAILY_BYTES = 500 * 1024 * 1024
DEFAULT_NOTEBOOK_MAX = 50
DEFAULT_RETRY_AFTER_SECONDS = 60


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_positive_int_env(env_name: str, default: int) -> int:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r is invalid; falling back to %d", env_name, raw, default)
        return default

    if value <= 0:
        logger.warning(
            "%s=%r must be a positive integer; falling back to %d",
            env_name,
            raw,
            default,
        )
        return default
    return value


def _open_connection(db_path: Path):
    from core.storage.sqlite_db import get_connection, init_schema

    conn = get_connection(db_path)
    init_schema(conn)
    return conn


class QuotaExceededError(Exception):
    """Raised when a quota dimension exceeds its configured limit."""

    def __init__(self, dimension: str, retry_after: int = DEFAULT_RETRY_AFTER_SECONDS):
        self.dimension = dimension
        self.retry_after = retry_after
        self.detail = f"Rate limit exceeded: {dimension}"
        super().__init__(self.detail)


class DailyUploadQuota:
    """Persist and enforce per-principal daily upload usage in SQLite."""

    def __init__(
        self,
        db_path: str | Path = Path("data/notebooks.db"),
        daily_limit: int | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.daily_limit = (
            daily_limit
            if daily_limit is not None
            else _parse_positive_int_env(
                "NOTEBOOKLM_UPLOAD_DAILY_BYTES", DEFAULT_UPLOAD_DAILY_BYTES
            )
        )
        self._now_fn = now_fn or _utc_now

    def _usage_date(self) -> str:
        return self._now_fn().astimezone(timezone.utc).strftime("%Y-%m-%d")

    def _updated_at(self) -> str:
        return self._now_fn().astimezone(timezone.utc).isoformat()

    def get_usage(self, principal_id: str, usage_date: str | None = None) -> int:
        conn = _open_connection(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT bytes_used
                FROM daily_upload_usage
                WHERE principal_id = ? AND usage_date = ?
                """,
                (principal_id, usage_date or self._usage_date()),
            ).fetchone()
            return int(row["bytes_used"]) if row else 0
        finally:
            conn.close()

    def check_and_record(self, principal_id: str, bytes_to_add: int) -> int:
        if not principal_id:
            raise ValueError("principal_id is required")
        if bytes_to_add < 0:
            raise ValueError("bytes_to_add must be non-negative")
        if bytes_to_add == 0:
            return self.get_usage(principal_id)
        if bytes_to_add > self.daily_limit:
            raise QuotaExceededError("upload_bytes")

        usage_date = self._usage_date()
        conn = _open_connection(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO daily_upload_usage (
                    principal_id,
                    usage_date,
                    bytes_used,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT (principal_id, usage_date)
                DO UPDATE SET
                    bytes_used = daily_upload_usage.bytes_used + excluded.bytes_used,
                    updated_at = excluded.updated_at
                WHERE daily_upload_usage.bytes_used + excluded.bytes_used <= ?
                """,
                (
                    principal_id,
                    usage_date,
                    bytes_to_add,
                    self._updated_at(),
                    self.daily_limit,
                ),
            )
            changed = int(
                conn.execute("SELECT changes() AS rowcount").fetchone()["rowcount"]
            )
            if changed == 0:
                conn.rollback()
                raise QuotaExceededError("upload_bytes")

            row = conn.execute(
                """
                SELECT bytes_used
                FROM daily_upload_usage
                WHERE principal_id = ? AND usage_date = ?
                """,
                (principal_id, usage_date),
            ).fetchone()
            conn.commit()
            return int(row["bytes_used"]) if row else 0
        finally:
            conn.close()


class NotebookCountCap:
    """Enforce a hard cap on notebook ownership using real-time COUNT(*) queries."""

    def __init__(
        self,
        db_path: str | Path = Path("data/notebooks.db"),
        max_count: int | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.max_count = (
            max_count
            if max_count is not None
            else _parse_positive_int_env("NOTEBOOKLM_NOTEBOOK_MAX", DEFAULT_NOTEBOOK_MAX)
        )

    def count(self, owner_id: str) -> int:
        if not owner_id:
            raise ValueError("owner_id is required")

        conn = _open_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM notebooks WHERE owner_id = ?",
                (owner_id,),
            ).fetchone()
            return int(row["count"]) if row else 0
        finally:
            conn.close()

    def check(self, owner_id: str) -> int:
        current_count = self.count(owner_id)
        if current_count >= self.max_count:
            raise QuotaExceededError("notebook_count")
        return current_count

