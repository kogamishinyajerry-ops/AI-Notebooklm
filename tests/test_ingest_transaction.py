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


def read_journal(tx):
    return json.loads(tx.journal_path.read_text(encoding="utf-8"))


def test_transaction_commit(tmp_path):
    tx = IngestTransaction("space-a", ingest_id="ingest-a", base_dir=tmp_path)

    tx.commit()

    journal = read_journal(tx)
    assert journal["status"] == "committed"
    assert "committed_at" in journal


def test_transaction_rollback_cleans_files(tmp_path):
    managed_file = tmp_path / "doc.pdf"
    managed_file.write_bytes(b"%PDF")
    tx = IngestTransaction("space-a", ingest_id="ingest-a", base_dir=tmp_path)
    tx.record_file(managed_file)

    tx.rollback()

    assert not managed_file.exists()
    assert read_journal(tx)["status"] == "rolled_back"


def test_transaction_rollback_cleans_vectors(tmp_path):
    vector_store = FakeVectorStore()
    tx = IngestTransaction("space-a", ingest_id="ingest-a", base_dir=tmp_path)
    tx.record_vector_ids(["v1", "v2"])

    tx.rollback(vector_store=vector_store)

    assert vector_store.deleted_ids == [["v1", "v2"]]
    assert read_journal(tx)["status"] == "rolled_back"


def test_transaction_rollback_restores_params(tmp_path):
    registry = FakeRegistry()
    snapshot = tmp_path / "params.snapshot.json"
    snapshot.write_text("{}", encoding="utf-8")
    tx = IngestTransaction("space-a", ingest_id="ingest-a", base_dir=tmp_path)
    tx.record_params_snapshot(snapshot)

    tx.rollback(registry=registry)

    assert registry.restored_snapshots == [str(snapshot)]
    assert read_journal(tx)["status"] == "rolled_back"


def test_recover_incomplete(tmp_path):
    managed_file = tmp_path / "doc.pdf"
    managed_file.write_bytes(b"%PDF")
    vector_store = FakeVectorStore()
    tx = IngestTransaction("space-a", ingest_id="ingest-a", base_dir=tmp_path)
    tx.record_file(managed_file)
    tx.record_vector_ids(["v1"])

    recovered = recover_incomplete_transactions(
        "space-a",
        vector_store=vector_store,
        base_dir=tmp_path,
    )

    assert recovered == 1
    assert not managed_file.exists()
    assert vector_store.deleted_ids == [["v1"]]
    assert read_journal(tx)["status"] == "rolled_back"


def test_recover_skips_committed(tmp_path):
    managed_file = tmp_path / "doc.pdf"
    managed_file.write_bytes(b"%PDF")
    vector_store = FakeVectorStore()
    tx = IngestTransaction("space-a", ingest_id="ingest-a", base_dir=tmp_path)
    tx.record_file(managed_file)
    tx.record_vector_ids(["v1"])
    tx.commit()

    recovered = recover_incomplete_transactions(
        "space-a",
        vector_store=vector_store,
        base_dir=tmp_path,
    )

    assert recovered == 0
    assert managed_file.exists()
    assert vector_store.deleted_ids == []
    assert read_journal(tx)["status"] == "committed"
