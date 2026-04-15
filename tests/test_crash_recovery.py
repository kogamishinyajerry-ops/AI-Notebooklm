import json

from core.ingestion.transaction import IngestTransaction, recover_incomplete_transactions


class FakeVectorStore:
    def __init__(self):
        self.deleted_ids = []

    def delete(self, ids):
        self.deleted_ids.append(ids)


class FakeRegistry:
    def __init__(self):
        self.restored_snapshots = []

    def restore(self, snapshot_path):
        self.restored_snapshots.append(snapshot_path)


def test_recover_after_file_written_crash(tmp_path):
    managed_file = tmp_path / "uploaded.pdf"
    managed_file.write_bytes(b"%PDF")
    tx = IngestTransaction("space-a", ingest_id="file-crash", base_dir=tmp_path)
    tx.record_file(managed_file)

    recovered = recover_incomplete_transactions("space-a", base_dir=tmp_path)

    assert recovered == 1
    assert not managed_file.exists()
    assert json.loads(tx.journal_path.read_text(encoding="utf-8"))["status"] == "rolled_back"


def test_recover_after_vector_written_crash(tmp_path):
    vector_store = FakeVectorStore()
    tx = IngestTransaction("space-a", ingest_id="vector-crash", base_dir=tmp_path)
    tx.record_vector_ids(["v1", "v2", "v3"])

    recovered = recover_incomplete_transactions(
        "space-a",
        vector_store=vector_store,
        base_dir=tmp_path,
    )

    assert recovered == 1
    assert vector_store.deleted_ids == [["v1", "v2", "v3"]]


def test_recover_after_params_registered_crash(tmp_path):
    registry = FakeRegistry()
    snapshot = tmp_path / "params.snapshot.json"
    snapshot.write_text('{"before": true}', encoding="utf-8")
    tx = IngestTransaction("space-a", ingest_id="params-crash", base_dir=tmp_path)
    tx.record_params_snapshot(snapshot)

    recovered = recover_incomplete_transactions(
        "space-a",
        registry=registry,
        base_dir=tmp_path,
    )

    assert recovered == 1
    assert registry.restored_snapshots == [str(snapshot)]
