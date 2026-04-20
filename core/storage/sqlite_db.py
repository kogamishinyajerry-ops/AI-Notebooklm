"""
core/storage/sqlite_db.py
=========================
V4.1-T2: SQLite Storage Migration — Foundation Module

Provides:
  - get_connection(path): opens SQLite DB with WAL mode + FK enforcement
  - init_schema(conn): runs all CREATE TABLE IF NOT EXISTS DDL
  - get_schema_version(conn): reads migration version
  - migrate_from_json(base_dir): orchestrates JSON → SQLite migration
  - run_migration_if_needed(base_dir): called at FastAPI startup

C1 compliant: local file only, no network calls, no telemetry.
"""

from __future__ import annotations

import json
import os
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.ingestion.transaction import DEFAULT_SPACES_DIR, iter_space_ids
from core.storage.migrations import apply_pending


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

SQLITE_POOL_SIZE_ENV = "NOTEBOOKLM_SQLITE_POOL_SIZE"


def _configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def _parse_pool_size() -> int:
    raw = os.getenv(SQLITE_POOL_SIZE_ENV, "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return max(value, 0)


class _PooledSQLiteConnection(sqlite3.Connection):
    """sqlite3 connection whose close() returns it to the owning pool."""

    _pool: "_SQLiteConnectionPool | None" = None
    _leased: bool = False

    def close(self) -> None:  # type: ignore[override]
        pool = self._pool
        if pool is None:
            super().close()
            return
        pool.release(self)

    def _really_close(self) -> None:
        self._pool = None
        self._leased = False
        super().close()


class _SQLiteConnectionPool:
    def __init__(self, db_path: Path, max_size: int) -> None:
        self.db_path = db_path
        self.max_size = max_size
        self._idle: queue.LifoQueue[_PooledSQLiteConnection] = queue.LifoQueue(
            maxsize=max_size
        )
        self._lock = threading.Lock()
        self._created = 0

    def acquire(self) -> _PooledSQLiteConnection:
        try:
            conn = self._idle.get_nowait()
        except queue.Empty:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=5.0,
                check_same_thread=False,
                factory=_PooledSQLiteConnection,
            )
            conn._pool = self
            with self._lock:
                self._created += 1
        conn._leased = True
        return _configure_connection(conn)  # type: ignore[return-value]

    def release(self, conn: _PooledSQLiteConnection) -> None:
        if not conn._leased:
            return
        conn._leased = False
        try:
            if conn.in_transaction:
                conn.rollback()
            _configure_connection(conn)
        except sqlite3.Error:
            conn._really_close()
            return

        try:
            self._idle.put_nowait(conn)
        except queue.Full:
            conn._really_close()

    def close_all(self) -> None:
        while True:
            try:
                conn = self._idle.get_nowait()
            except queue.Empty:
                return
            conn._really_close()

    @property
    def created(self) -> int:
        with self._lock:
            return self._created


_POOLS: dict[Path, _SQLiteConnectionPool] = {}
_POOLS_LOCK = threading.Lock()


def _pool_for(db_path: Path, max_size: int) -> _SQLiteConnectionPool:
    resolved = db_path.resolve()
    with _POOLS_LOCK:
        pool = _POOLS.get(resolved)
        if pool is None or pool.max_size != max_size:
            if pool is not None:
                pool.close_all()
            pool = _SQLiteConnectionPool(resolved, max_size=max_size)
            _POOLS[resolved] = pool
        return pool


def close_connection_pools() -> None:
    """Close all idle pooled SQLite connections.

    Primarily used by tests and process shutdown hooks. Leased connections still
    belong to their callers and will close or return when the caller calls
    ``close()``.
    """
    with _POOLS_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        pool.close_all()


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """
    Open a SQLite connection to *db_path* with:
      - WAL journal mode (better concurrent read performance)
      - PRAGMA foreign_keys = ON (enforce FK constraints)
      - PRAGMA busy_timeout = 5000 (wait up to 5s for locks)
      - PRAGMA synchronous = NORMAL (balanced durability/speed)
    """
    db_path = Path(db_path)
    pool_size = _parse_pool_size()
    if pool_size > 0:
        return _pool_for(db_path, pool_size).acquire()
    conn = sqlite3.connect(str(db_path), timeout=5.0, check_same_thread=False)
    return _configure_connection(conn)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version  INTEGER PRIMARY KEY,
    migrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notebooks (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    source_count INTEGER NOT NULL DEFAULT 0,
    owner_id     TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id           TEXT PRIMARY KEY,
    notebook_id  TEXT NOT NULL,
    title        TEXT NOT NULL,
    content      TEXT NOT NULL,
    citations    TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_notes_notebook ON notes(notebook_id);

CREATE TABLE IF NOT EXISTS sources (
    id              TEXT PRIMARY KEY,
    notebook_id     TEXT NOT NULL,
    filename        TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    status          TEXT NOT NULL,
    page_count      INTEGER,
    chunk_count     INTEGER,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    error_message   TEXT,
    FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sources_notebook ON sources(notebook_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id                TEXT PRIMARY KEY,
    notebook_id       TEXT NOT NULL,
    role              TEXT NOT NULL,
    content           TEXT NOT NULL,
    citations         TEXT NOT NULL DEFAULT '[]',
    is_fully_verified INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chat_notebook_created
    ON chat_messages(notebook_id, created_at);

CREATE TABLE IF NOT EXISTS studio_outputs (
    id           TEXT PRIMARY KEY,
    notebook_id  TEXT NOT NULL,
    output_type  TEXT NOT NULL,
    title        TEXT NOT NULL,
    content      TEXT NOT NULL,
    citations    TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL,
    FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_studio_notebook ON studio_outputs(notebook_id);

CREATE TABLE IF NOT EXISTS knowledge_graphs (
    notebook_id  TEXT PRIMARY KEY,
    nodes        TEXT NOT NULL DEFAULT '[]',
    edges        TEXT NOT NULL DEFAULT '[]',
    mindmap      TEXT,
    generated_at TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL,
    FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS daily_upload_usage (
    principal_id TEXT NOT NULL,
    usage_date   TEXT NOT NULL,   -- YYYY-MM-DD UTC
    bytes_used   INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (principal_id, usage_date)
);
CREATE INDEX IF NOT EXISTS idx_daily_upload_date ON daily_upload_usage(usage_date);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id            TEXT PRIMARY KEY,
    ts_utc              TEXT NOT NULL,
    event               TEXT NOT NULL,
    outcome             TEXT NOT NULL CHECK (outcome IN ('success', 'failure')),
    actor_type          TEXT NOT NULL CHECK (actor_type IN ('user', 'system', 'anonymous')),
    principal_id        TEXT NOT NULL,
    request_id          TEXT NOT NULL,
    remote_addr         TEXT NOT NULL,
    resource_type       TEXT NOT NULL,
    resource_id         TEXT NOT NULL,
    parent_resource_id  TEXT NOT NULL,
    http_status         INTEGER NOT NULL,
    error_code          TEXT NOT NULL,
    payload_json        TEXT NOT NULL,
    schema_version      INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts_utc);
CREATE INDEX IF NOT EXISTS idx_audit_principal_ts ON audit_events(principal_id, ts_utc);
CREATE INDEX IF NOT EXISTS idx_audit_event_ts ON audit_events(event, ts_utc);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_events(resource_type, resource_id);

CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Run all CREATE TABLE IF NOT EXISTS DDL."""
    conn.executescript(_SCHEMA_SQL)
    apply_pending(conn)
    conn.commit()


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

def get_schema_version(conn: sqlite3.Connection) -> int | None:
    """Return the recorded schema version, or None if not yet migrated."""
    cur = conn.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    )
    row = cur.fetchone()
    return int(row["version"]) if row else None


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Record the schema version (called after successful migration)."""
    from core.ingestion.transaction import utc_now_iso
    conn.execute(
        "INSERT INTO schema_version (version, migrated_at) VALUES (?, ?)",
        (version, utc_now_iso()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

@dataclass
class MigrationResult:
    success: bool
    version: int
    counts: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


def _utc_now() -> str:
    from core.ingestion.transaction import utc_now_iso
    return utc_now_iso()


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _rename_to_backup(path: Path) -> None:
    if path.exists():
        path.rename(path.with_suffix(path.suffix + ".v4_1_migrated"))


def _delete_backup(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".v4_1_migrated")
    if backup.exists():
        backup.unlink()


def _insert_notebooks(conn: sqlite3.Connection, data: List[Dict]) -> int:
    count = 0
    for item in data:
        conn.execute(
            """INSERT OR REPLACE INTO notebooks
               (id, name, created_at, updated_at, source_count, owner_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                item["id"], item["name"], item["created_at"], item["updated_at"],
                item.get("source_count", 0), item.get("owner_id"),
            ),
        )
        count += 1
    return count


def _insert_notes(conn: sqlite3.Connection, notebook_id: str, items: List[Dict]) -> int:
    count = 0
    for item in items:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO notes
               (id, notebook_id, title, content, citations, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                item["id"], notebook_id, item["title"], item["content"],
                json.dumps(item.get("citations", []), ensure_ascii=False),
                item["created_at"], item["updated_at"],
            ),
        )
        # rowcount == 1 means the row was actually inserted;
        # rowcount == 0 (or -1) means INSERT OR IGNORE skipped it (duplicate PK)
        if cursor.rowcount == 1:
            count += 1
    return count


def _insert_sources(conn: sqlite3.Connection, notebook_id: str, items: List[Dict]) -> int:
    count = 0
    for item in items:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO sources
               (id, notebook_id, filename, file_path, status, page_count,
                chunk_count, created_at, updated_at, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item["id"], notebook_id, item["filename"], item["file_path"],
                item.get("status", "uploading"), item.get("page_count"),
                item.get("chunk_count"),
                item["created_at"], item["updated_at"],
                item.get("error_message"),
            ),
        )
        if cursor.rowcount == 1:
            count += 1
    return count


def _insert_chat_messages(
    conn: sqlite3.Connection, notebook_id: str, items: List[Dict]
) -> int:
    count = 0
    for item in items:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO chat_messages
               (id, notebook_id, role, content, citations,
                is_fully_verified, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                item["id"], notebook_id, item["role"], item["content"],
                json.dumps(item.get("citations", []), ensure_ascii=False),
                int(item.get("is_fully_verified", False)),
                item["created_at"],
            ),
        )
        if cursor.rowcount == 1:
            count += 1
    return count


def _insert_studio_outputs(
    conn: sqlite3.Connection, notebook_id: str, items: List[Dict]
) -> int:
    count = 0
    for item in items:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO studio_outputs
               (id, notebook_id, output_type, title, content, citations, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                item["id"], notebook_id, item["output_type"], item["title"],
                item["content"],
                json.dumps(item.get("citations", []), ensure_ascii=False),
                item["created_at"],
            ),
        )
        if cursor.rowcount == 1:
            count += 1
    return count


def _insert_graph(conn: sqlite3.Connection, notebook_id: str, data: Dict) -> int:
    if not data:
        return 0
    conn.execute(
        """INSERT OR REPLACE INTO knowledge_graphs
           (notebook_id, nodes, edges, mindmap, generated_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            notebook_id,
            json.dumps(data.get("nodes", []), ensure_ascii=False),
            json.dumps(data.get("edges", []), ensure_ascii=False),
            json.dumps(data.get("mindmap")) if data.get("mindmap") else None,
            data.get("generated_at", ""),
            data.get("updated_at", _utc_now()),
        ),
    )
    return 1


def migrate_from_json(
    db_path: str | Path,
    base_dir: str | Path,
    spaces_dir: str | Path = DEFAULT_SPACES_DIR,
) -> MigrationResult:
    """
    Migrate all JSON stores to SQLite.

    Reads existing JSON files, inserts into SQLite within a single transaction,
    then renames JSON files to .v4_1_migrated backups.

    On any error, ROLLBACK is issued and no files are renamed.
    """
    t0 = time.monotonic()
    db_path = Path(db_path)
    base_dir = Path(base_dir)
    spaces_dir = Path(spaces_dir)

    counts: Dict[str, int] = {}
    errors: List[str] = []
    conn: Optional[sqlite3.Connection] = None

    try:
        # Set up DB
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = get_connection(db_path)
        init_schema(conn)

        # Check already-migrated
        version = get_schema_version(conn)
        if version is not None:
            return MigrationResult(success=True, version=version, counts={}, errors=[])

        # Begin transaction
        conn.execute("BEGIN TRANSACTION")

        # 1. notebooks.json
        notebooks_path = base_dir / "notebooks.json"
        notebooks_data = _read_json(notebooks_path) or []
        if not isinstance(notebooks_data, list):
            notebooks_data = []
        counts["notebooks"] = _insert_notebooks(conn, notebooks_data)

        # Collect notebook IDs for per-notebook migration
        notebook_ids = {nb["id"] for nb in notebooks_data if "id" in nb}

        # 2. Per-notebook files
        for nb_id in notebook_ids:
            nb_dir = spaces_dir / nb_id
            if not nb_dir.is_dir():
                continue

            # notes
            notes_path = nb_dir / "notes.json"
            notes_data = _read_json(notes_path) or []
            if isinstance(notes_data, list):
                counts["notes"] = counts.get("notes", 0) + _insert_notes(conn, nb_id, notes_data)

            # sources
            sources_path = nb_dir / "sources.json"
            sources_data = _read_json(sources_path) or []
            if isinstance(sources_data, list):
                counts["sources"] = counts.get("sources", 0) + _insert_sources(conn, nb_id, sources_data)

            # chat_history
            chat_path = nb_dir / "chat_history.json"
            chat_data = _read_json(chat_path) or []
            if isinstance(chat_data, list):
                counts["chat_messages"] = counts.get("chat_messages", 0) + _insert_chat_messages(conn, nb_id, chat_data)

            # studio
            studio_path = nb_dir / "studio.json"
            studio_data = _read_json(studio_path) or []
            if isinstance(studio_data, list):
                counts["studio_outputs"] = counts.get("studio_outputs", 0) + _insert_studio_outputs(conn, nb_id, studio_data)

            # graph
            graph_path = nb_dir / "graph.json"
            graph_data = _read_json(graph_path)
            if graph_data and isinstance(graph_data, dict):
                counts["knowledge_graphs"] = counts.get("knowledge_graphs", 0) + _insert_graph(conn, nb_id, graph_data)

        conn.execute("COMMIT")

        # Phase 3: Rename JSON files to backups (after successful commit)
        _rename_to_backup(notebooks_path)
        for nb_id in notebook_ids:
            nb_dir = spaces_dir / nb_id
            for fname in ("notes.json", "sources.json", "chat_history.json", "studio.json", "graph.json"):
                _rename_to_backup(nb_dir / fname)

        # Phase 4: Record version and verify reads work
        set_schema_version(conn, version=1)
        conn.execute("SELECT COUNT(*) FROM notebooks").fetchone()  # verify
        _delete_backup(notebooks_path)
        for nb_id in notebook_ids:
            nb_dir = spaces_dir / nb_id
            for fname in ("notes.json", "sources.json", "chat_history.json", "studio.json", "graph.json"):
                _delete_backup(nb_dir / fname)

        duration_ms = (time.monotonic() - t0) * 1000
        return MigrationResult(
            success=True, version=1, counts=counts, errors=[], duration_ms=duration_ms
        )

    except Exception as exc:  # pragma: no cover — defensive
        if conn:
            conn.execute("ROLLBACK")
        errors.append(str(exc))
        duration_ms = (time.monotonic() - t0) * 1000
        return MigrationResult(
            success=False, version=0, counts=counts, errors=errors, duration_ms=duration_ms
        )
    finally:
        if conn:
            conn.close()


def run_migration_if_needed(
    base_dir: str | Path = Path("data"),
    db_path: str | Path | None = None,
    spaces_dir: str | Path = DEFAULT_SPACES_DIR,
) -> MigrationResult:
    """
    Called at FastAPI startup: run migration once if the DB has not been
    initialized yet.

    Returns a MigrationResult (success=True even if already migrated).
    """
    if db_path is None:
        db_path = Path(base_dir) / "notebooks.db"
    db_path = Path(db_path)

    # If DB already exists and has a schema version, skip
    if db_path.exists():
        try:
            conn = get_connection(db_path)
            try:
                v = get_schema_version(conn)
                if v is not None:
                    return MigrationResult(success=True, version=v, counts={}, errors=[])
            finally:
                conn.close()
        except sqlite3.Error:
            pass  # DB exists but is not valid; re-run migration

    return migrate_from_json(db_path, base_dir, spaces_dir)
