from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3


VERSION = 1


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[str, ...]
    create_sql: str


_TABLE_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        name="notebooks",
        columns=("id", "name", "created_at", "updated_at", "source_count", "owner_id"),
        create_sql="""
            CREATE TABLE {table} (
                id           TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL,
                source_count INTEGER NOT NULL DEFAULT 0,
                owner_id     TEXT
            )
        """,
    ),
    TableSpec(
        name="notes",
        columns=("id", "notebook_id", "title", "content", "citations", "created_at", "updated_at"),
        create_sql="""
            CREATE TABLE {table} (
                id           TEXT PRIMARY KEY,
                notebook_id  TEXT NOT NULL,
                title        TEXT NOT NULL,
                content      TEXT NOT NULL,
                citations    TEXT NOT NULL DEFAULT '[]',
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL,
                FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
            )
        """,
    ),
    TableSpec(
        name="sources",
        columns=(
            "id",
            "notebook_id",
            "filename",
            "file_path",
            "status",
            "page_count",
            "chunk_count",
            "created_at",
            "updated_at",
            "error_message",
        ),
        create_sql="""
            CREATE TABLE {table} (
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
            )
        """,
    ),
    TableSpec(
        name="chat_messages",
        columns=(
            "id",
            "notebook_id",
            "role",
            "content",
            "citations",
            "is_fully_verified",
            "created_at",
        ),
        create_sql="""
            CREATE TABLE {table} (
                id                TEXT PRIMARY KEY,
                notebook_id       TEXT NOT NULL,
                role              TEXT NOT NULL,
                content           TEXT NOT NULL,
                citations         TEXT NOT NULL DEFAULT '[]',
                is_fully_verified INTEGER NOT NULL DEFAULT 0,
                created_at        TEXT NOT NULL,
                FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
            )
        """,
    ),
    TableSpec(
        name="studio_outputs",
        columns=("id", "notebook_id", "output_type", "title", "content", "citations", "created_at"),
        create_sql="""
            CREATE TABLE {table} (
                id           TEXT PRIMARY KEY,
                notebook_id  TEXT NOT NULL,
                output_type  TEXT NOT NULL,
                title        TEXT NOT NULL,
                content      TEXT NOT NULL,
                citations    TEXT NOT NULL DEFAULT '[]',
                created_at   TEXT NOT NULL,
                FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
            )
        """,
    ),
    TableSpec(
        name="knowledge_graphs",
        columns=("notebook_id", "nodes", "edges", "mindmap", "generated_at", "updated_at"),
        create_sql="""
            CREATE TABLE {table} (
                notebook_id  TEXT PRIMARY KEY,
                nodes        TEXT NOT NULL DEFAULT '[]',
                edges        TEXT NOT NULL DEFAULT '[]',
                mindmap      TEXT,
                generated_at TEXT NOT NULL DEFAULT '',
                updated_at   TEXT NOT NULL,
                FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
            )
        """,
    ),
)


def _database_path(conn: sqlite3.Connection) -> Path | None:
    rows = conn.execute("PRAGMA database_list").fetchall()
    for row in rows:
        name = row[1] if not isinstance(row, sqlite3.Row) else row["name"]
        path = row[2] if not isinstance(row, sqlite3.Row) else row["file"]
        if name == "main" and path:
            return Path(path)
    return None


def _index_sql(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'index'
          AND tbl_name = ?
          AND sql IS NOT NULL
        ORDER BY name
        """,
        (table,),
    ).fetchall()
    return [str(row["sql"] if isinstance(row, sqlite3.Row) else row[0]) for row in rows]


def _rebuild_table(conn: sqlite3.Connection, spec: TableSpec) -> None:
    temp_table = f"__t5_{spec.name}"
    indexes = _index_sql(conn, spec.name)
    columns = ", ".join(spec.columns)

    conn.execute(f"DROP TABLE IF EXISTS {temp_table}")
    conn.execute(spec.create_sql.format(table=temp_table))
    conn.execute(
        f"""
        INSERT INTO {temp_table} ({columns})
        SELECT {columns}
        FROM {spec.name}
        """
    )
    conn.execute(f"DROP TABLE {spec.name}")
    conn.execute(f"ALTER TABLE {temp_table} RENAME TO {spec.name}")
    for statement in indexes:
        conn.execute(statement)


def _foreign_key_violations(conn: sqlite3.Connection) -> list[tuple]:
    return [tuple(row) for row in conn.execute("PRAGMA foreign_key_check").fetchall()]


def _raise_if_fk_violations(conn: sqlite3.Connection) -> None:
    violations = _foreign_key_violations(conn)
    if violations:
        raise sqlite3.IntegrityError(f"foreign_key_check failed: {violations}")


def _repair_orphans(conn: sqlite3.Connection) -> None:
    db_path = _database_path(conn)
    if db_path is None:
        _raise_if_fk_violations(conn)
        return

    # Ensure schema DDL from init_schema is visible to the repair connection.
    conn.commit()
    from scripts.audit_integrity import repair_orphans

    repair_orphans(db_path, confirm=True)


def apply(conn: sqlite3.Connection, *, repair: bool = True) -> None:
    """Rebuild notebook-scoped tables so FK enforcement is guaranteed."""
    if repair:
        _repair_orphans(conn)

    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        for spec in _TABLE_SPECS:
            _rebuild_table(conn, spec)
        _raise_if_fk_violations(conn)
        conn.execute(f"PRAGMA user_version={VERSION}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
