"""Lightweight ingestion transaction journal.

The journal records resources created during ingestion so a failed or
interrupted run can be compensated later.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_SPACES_DIR = Path("data/spaces")
DEFAULT_COMMITTED_JOURNAL_RETENTION_DAYS = 7


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_journal_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def resolve_space_path(space_id: str, *parts: str, base_dir: str | Path = DEFAULT_SPACES_DIR) -> Path:
    return Path(base_dir) / space_id / Path(*parts)


def iter_space_ids(base_dir: str | Path = DEFAULT_SPACES_DIR) -> list[str]:
    spaces_dir = Path(base_dir)
    if not spaces_dir.exists():
        return []
    return sorted(path.name for path in spaces_dir.iterdir() if path.is_dir())


class IngestTransaction:
    """Record ingestion resources and roll them back on failure."""

    def __init__(
        self,
        space_id: str,
        ingest_id: str | None = None,
        base_dir: str | Path = DEFAULT_SPACES_DIR,
        committed_retention_days: int | None = DEFAULT_COMMITTED_JOURNAL_RETENTION_DAYS,
    ):
        self.space_id = space_id
        self.ingest_id = ingest_id or str(uuid.uuid4())
        self.base_dir = Path(base_dir)
        self.committed_retention_days = committed_retention_days

        tx_dir = resolve_space_path(space_id, ".transactions", base_dir=self.base_dir)
        tx_dir.mkdir(parents=True, exist_ok=True)
        self.journal_path = tx_dir / f"{self.ingest_id}.json"

        self._journal: dict[str, Any] = {
            "ingest_id": self.ingest_id,
            "space_id": space_id,
            "status": "in_progress",
            "started_at": utc_now_iso(),
            "resources": {
                "files": [],
                "vector_ids": [],
                "params_snapshot": None,
                "source": None,
                "graph_node_ids": [],
                "community_ids": [],
            },
        }
        self.flush()

    @property
    def status(self) -> str:
        return str(self._journal.get("status", "unknown"))

    @property
    def resources(self) -> dict[str, Any]:
        resources = self._journal.setdefault("resources", {})
        resources.setdefault("files", [])
        resources.setdefault("vector_ids", [])
        resources.setdefault("params_snapshot", None)
        resources.setdefault("source", None)
        resources.setdefault("graph_node_ids", [])
        resources.setdefault("community_ids", [])
        return resources

    def record_file(self, path: str | Path) -> None:
        value = str(path)
        if value not in self.resources["files"]:
            self.resources["files"].append(value)
            self.flush()

    def record_vector_ids(self, ids: list[str]) -> None:
        if not ids:
            return
        existing = set(self.resources["vector_ids"])
        new_ids = [item for item in ids if item not in existing]
        if new_ids:
            self.resources["vector_ids"].extend(new_ids)
            self.flush()

    def record_params_snapshot(self, snapshot_path: str | Path) -> None:
        self.resources["params_snapshot"] = str(snapshot_path)
        self.flush()

    def record_source(self, notebook_id: str, source_id: str) -> None:
        self.resources["source"] = {
            "notebook_id": notebook_id,
            "source_id": source_id,
        }
        self.flush()

    def flush(self) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.journal_path.with_suffix(f"{self.journal_path.suffix}.tmp")
        tmp_path.write_text(json.dumps(self._journal, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.journal_path)

    def commit(self) -> None:
        self._journal["status"] = "committed"
        self._journal["committed_at"] = utc_now_iso()
        self.flush()
        cleanup_committed_transactions(
            self.space_id,
            retention_days=self.committed_retention_days,
            base_dir=self.base_dir,
            exclude_paths={self.journal_path},
        )

    def rollback(self, vector_store: Any = None, registry: Any = None) -> None:
        """Best-effort rollback of all resources recorded in the journal."""
        resources = self.resources

        for file_path in resources["files"]:
            try:
                Path(file_path).unlink(missing_ok=True)
            except Exception:
                pass

        vector_ids = resources["vector_ids"]
        if vector_store is not None and vector_ids:
            try:
                vector_store.delete(ids=vector_ids)
            except Exception:
                pass

        snapshot_path = resources["params_snapshot"]
        if registry is not None and snapshot_path and Path(snapshot_path).exists():
            try:
                registry.restore(snapshot_path)
            except Exception:
                pass

        source = resources["source"]
        if registry is not None and source and hasattr(registry, "delete"):
            try:
                registry.delete(source["notebook_id"], source["source_id"])
            except Exception:
                pass

        # Reserved for the graph/community pipeline when those modules exist.
        if resources.get("graph_node_ids"):
            pass
        if resources.get("community_ids"):
            pass

        self._journal["status"] = "rolled_back"
        self._journal["rolled_back_at"] = utc_now_iso()
        self.flush()

    @classmethod
    def from_journal_file(cls, journal_path: str | Path) -> "IngestTransaction":
        path = Path(journal_path)
        data = json.loads(path.read_text(encoding="utf-8"))

        tx = cls.__new__(cls)
        tx.space_id = data["space_id"]
        tx.ingest_id = data["ingest_id"]
        tx.base_dir = path.parents[1].parent
        tx.committed_retention_days = DEFAULT_COMMITTED_JOURNAL_RETENTION_DAYS
        tx.journal_path = path
        tx._journal = data
        tx.resources
        return tx


def recover_incomplete_transactions(
    space_id: str,
    vector_store: Any = None,
    registry: Any = None,
    base_dir: str | Path = DEFAULT_SPACES_DIR,
) -> int:
    """Rollback all in-progress journals for a space and return the count."""
    tx_dir = resolve_space_path(space_id, ".transactions", base_dir=base_dir)
    if not tx_dir.exists():
        return 0

    recovered = 0
    for journal_file in sorted(tx_dir.glob("*.json")):
        try:
            data = json.loads(journal_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        if data.get("status") != "in_progress":
            continue

        try:
            tx = IngestTransaction.from_journal_file(journal_file)
            tx.rollback(vector_store=vector_store, registry=registry)
            recovered += 1
        except Exception:
            continue

    return recovered


def cleanup_committed_transactions(
    space_id: str,
    retention_days: int | None = DEFAULT_COMMITTED_JOURNAL_RETENTION_DAYS,
    base_dir: str | Path = DEFAULT_SPACES_DIR,
    now: datetime | None = None,
    exclude_paths: set[Path] | None = None,
) -> int:
    """Delete committed journals older than the retention window."""
    if retention_days is None or retention_days < 0:
        return 0

    tx_dir = resolve_space_path(space_id, ".transactions", base_dir=base_dir)
    if not tx_dir.exists():
        return 0

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    cutoff = current_time - timedelta(days=retention_days)
    excluded = {path.resolve() for path in exclude_paths or set()}

    removed = 0
    for journal_file in sorted(tx_dir.glob("*.json")):
        if journal_file.resolve() in excluded:
            continue
        try:
            data = json.loads(journal_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        if data.get("status") != "committed":
            continue

        committed_at = parse_journal_datetime(data.get("committed_at"))
        if committed_at is None or committed_at >= cutoff:
            continue

        try:
            journal_file.unlink()
            removed += 1
        except Exception:
            continue

    return removed


def count_incomplete_transactions(
    space_id: str,
    base_dir: str | Path = DEFAULT_SPACES_DIR,
) -> int:
    tx_dir = resolve_space_path(space_id, ".transactions", base_dir=base_dir)
    if not tx_dir.exists():
        return 0

    count = 0
    for journal_file in sorted(tx_dir.glob("*.json")):
        try:
            data = json.loads(journal_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("status") == "in_progress":
            count += 1
    return count


def oldest_incomplete_transaction_started_at(
    space_id: str,
    base_dir: str | Path = DEFAULT_SPACES_DIR,
) -> datetime | None:
    tx_dir = resolve_space_path(space_id, ".transactions", base_dir=base_dir)
    if not tx_dir.exists():
        return None

    oldest: datetime | None = None
    for journal_file in sorted(tx_dir.glob("*.json")):
        try:
            data = json.loads(journal_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        if data.get("status") != "in_progress":
            continue

        started_at = parse_journal_datetime(data.get("started_at"))
        if started_at is not None and (oldest is None or started_at < oldest):
            oldest = started_at

    return oldest


def summarize_transaction_health(
    base_dir: str | Path = DEFAULT_SPACES_DIR,
    now: datetime | None = None,
) -> dict[str, Any]:
    spaces: dict[str, int] = {}
    oldest_started_at: datetime | None = None
    for space_id in iter_space_ids(base_dir=base_dir):
        spaces[space_id] = count_incomplete_transactions(space_id, base_dir=base_dir)
        space_oldest = oldest_incomplete_transaction_started_at(space_id, base_dir=base_dir)
        if space_oldest is not None and (oldest_started_at is None or space_oldest < oldest_started_at):
            oldest_started_at = space_oldest

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    oldest_age_seconds = None
    if oldest_started_at is not None:
        oldest_age_seconds = max(0, int((current_time - oldest_started_at).total_seconds()))

    return {
        "in_progress": sum(spaces.values()),
        "oldest_pending_transaction_age_seconds": oldest_age_seconds,
        "spaces": spaces,
    }
