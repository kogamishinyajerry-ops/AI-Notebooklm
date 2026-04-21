from __future__ import annotations

from core.retrieval import vector_store as vector_store_module


def _matches_where(metadata, where):
    if not where:
        return True
    for key, condition in where.items():
        value = metadata.get(key)
        if isinstance(condition, dict):
            if "$eq" in condition and value != condition["$eq"]:
                return False
            if "$in" in condition and value not in condition["$in"]:
                return False
        elif value != condition:
            return False
    return True


class FakeCollection:
    def __init__(self):
        self.rows = {}
        self.last_add_metadatas = []

    def add(self, *, ids, embeddings, metadatas, documents):
        self.last_add_metadatas = metadatas
        for doc_id, embedding, metadata, document in zip(ids, embeddings, metadatas, documents):
            self.rows[doc_id] = {
                "embedding": embedding,
                "metadata": metadata,
                "document": document,
            }

    def delete(self, **kwargs):
        return None

    def query(self, *, n_results, where=None, **kwargs):
        rows = [
            row for row in self.rows.values()
            if _matches_where(row["metadata"], where)
        ][:n_results]
        return {
            "documents": [[row["document"] for row in rows]],
            "metadatas": [[row["metadata"] for row in rows]],
        }

    def get(self, *, ids=None, include=None, where=None):
        if ids is None:
            selected = [
                (doc_id, row)
                for doc_id, row in self.rows.items()
                if _matches_where(row["metadata"], where)
            ]
        else:
            selected = [
                (doc_id, self.rows[doc_id])
                for doc_id in ids
                if doc_id in self.rows
            ]
        return {
            "ids": [doc_id for doc_id, _row in selected],
            "documents": [row["document"] for _doc_id, row in selected],
            "metadatas": [row["metadata"] for _doc_id, row in selected],
        }


class FakePersistentClient:
    def __init__(self, path, settings):
        self.collection = FakeCollection()

    def get_or_create_collection(self, name):
        return self.collection


def test_vector_store_round_trips_bbox_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(
        vector_store_module.chromadb,
        "PersistentClient",
        FakePersistentClient,
    )

    adapter = vector_store_module.VectorStoreAdapter(
        persist_directory=str(tmp_path / "vector-db")
    )
    ids = adapter.add_documents(
        chunks=["Alpha", "Bravo"],
        metadatas=[
            {"source_id": "src-a", "page": 1, "bbox": [1.0, 2.0, 3.0, 4.0]},
            {"source_id": "src-b", "page": 2, "bbox": [10.0, 20.0, 30.0, 40.0]},
        ],
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
        ids=["doc-a", "doc-b"],
    )

    assert ids == ["doc-a", "doc-b"]
    assert adapter.collection.last_add_metadatas[0]["bbox"] == "[1.0, 2.0, 3.0, 4.0]"
    assert adapter.collection.last_add_metadatas[1]["bbox"] == "[10.0, 20.0, 30.0, 40.0]"

    queried = adapter.query(query_embeddings=[0.1, 0.2], top_k=2)
    assert queried["metadatas"][0][0]["bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert queried["metadatas"][0][1]["bbox"] == [10.0, 20.0, 30.0, 40.0]

    by_ids = adapter.get_by_ids(["doc-a", "doc-b"])
    assert by_ids["metadatas"][0]["bbox"] == [1.0, 2.0, 3.0, 4.0]
    assert by_ids["metadatas"][1]["bbox"] == [10.0, 20.0, 30.0, 40.0]

    fetched = adapter.get_all(where={"source_id": {"$eq": "src-a"}})
    assert fetched["ids"] == ["doc-a"]
    assert fetched["metadatas"][0]["bbox"] == [1.0, 2.0, 3.0, 4.0]
