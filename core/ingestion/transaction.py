"""Lightweight ingestion transaction journal.

The journal records resources created during ingestion so a failed or
interrupted run can be compensated later.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SPACES_DIR = Path("data/spaces")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    ):
        self.space_id = space_id
        self.ingest_id = ingest_id or str(uuid.uuid4())
        self.base_dir = Path(base_dir)

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

    def flush(self) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.journal_path.with_suffix(f"{self.journal_path.suffix}.tmp")
        tmp_path.write_text(json.dumps(self._journal, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.journal_path)

    def commit(self) -> None:
        self._journal["status"] = "committed"
        self._journal["committed_at"] = utc_now_iso()
        self.flush()

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
