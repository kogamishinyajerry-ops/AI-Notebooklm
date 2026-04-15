import json

import pytest
from fastapi.testclient import TestClient

import apps.api.main as main
import services.knowledge.parameter_registry as parameter_registry
from core.retrieval.vector_store import VectorStoreAdapter
from services.ingestion import service as ingestion_service
from services.ingestion.parser import DocumentChunk
from services.knowledge.parameter_registry import ParameterRegistry


class DummyParser:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.closed = False

    def extract_chunks(self):
        return [
            DocumentChunk(
                text="MTOW 72500 kg",
                metadata={"source": "rollback.pdf", "page": 1, "bbox": [1, 2, 3, 4]},
            )
        ]

    def close(self):
        self.closed = True


class IdentityChunker:
    def chunk(self, blocks):
        return blocks


class FailingEmbeddingManager:
    def encode(self, texts):
        raise RuntimeError("embedding failed")


class NoopVectorStore:
    def add_documents(self, chunks, metadatas, embeddings):
        raise AssertionError("vector store should not be reached")


def test_ingestion_failure_restores_parameter_registry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ingestion_service, "PDFParser", DummyParser)
    monkeypatch.setattr(
        parameter_registry,
        "call_local_llm",
        lambda system_prompt, user_query: '[{"value":"72500","type":"MTOW","unit":"kg","context":"test"}]',
    )

    registry = ParameterRegistry(space_id="space-a")
    registry.registry = {
        "existing": {
            "123": [
                {
                    "type": "MLW",
                    "unit": "kg",
                    "source": "old.pdf",
                    "page": 1,
                    "context": "existing",
                }
            ]
        }
    }
    registry._save()

    service = ingestion_service.IngestionService.__new__(ingestion_service.IngestionService)
    service.space_id = "space-a"
    service.vector_store = NoopVectorStore()
    service.embedding_manager = FailingEmbeddingManager()
    service.chunker = IdentityChunker()
    service.parameter_registry = registry

    with pytest.raises(RuntimeError, match="embedding failed"):
        service.process_file("rollback.pdf")

    params = json.loads((tmp_path / "data" / "spaces" / "space-a" / "params.json").read_text())
    assert params == registry.registry
    assert "existing" in params
    assert "72500" not in json.dumps(params)


def test_vector_add_failure_deletes_known_ids():
    added_ids = []
    deleted_ids = []

    class FailingCollection:
        def add(self, ids, embeddings, metadatas, documents):
            added_ids.extend(ids)
            raise RuntimeError("chroma add failed")

        def delete(self, ids):
            deleted_ids.extend(ids)

    adapter = VectorStoreAdapter.__new__(VectorStoreAdapter)
    adapter.collection = FailingCollection()

    with pytest.raises(RuntimeError, match="chroma add failed"):
        adapter.add_documents(
            chunks=["text"],
            metadatas=[{"source": "a.pdf"}],
            embeddings=[[0.1, 0.2]],
        )

    assert added_ids
    assert deleted_ids == added_ids


def test_upload_failure_removes_written_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    class FailingIngestionService:
        def process_file(self, file_path: str) -> int:
            raise RuntimeError("ingestion failed")

    monkeypatch.setattr(main, "get_ingestion_service", lambda space_id: FailingIngestionService())
    client = TestClient(main.app)

    response = client.post(
        "/api/v1/documents/upload?space_id=space-a",
        files={"file": ("rollback.pdf", b"%PDF-1.4 rollback", "application/pdf")},
    )

    assert response.status_code == 500
    assert not (tmp_path / "data" / "spaces" / "space-a" / "docs" / "rollback.pdf").exists()
