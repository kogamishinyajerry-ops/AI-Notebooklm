import sys
import types

from fastapi.testclient import TestClient

llm_package = types.ModuleType("core.llm")
llm_client = types.ModuleType("core.llm.client")
llm_client.call_local_llm = lambda system_prompt, user_query: "[]"
llm_package.client = llm_client
sys.modules.setdefault("core.llm", llm_package)
sys.modules["core.llm.client"] = llm_client

import apps.api.main as main


class DummyIngestionService:
    def __init__(self):
        self.paths = []

    def process_file(self, file_path: str) -> int:
        self.paths.append(file_path)
        return 3


class DummyRetriever:
    def get_by_source(self, filename: str, limit: int = 10):
        return [
            {
                "text": f"{filename} preview chunk",
                "metadata": {
                    "source": filename,
                    "page": "1",
                    "bbox": [10, 20, 30, 40],
                },
            }
        ]


def test_notes_are_isolated_by_space(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = TestClient(main.app)

    note_a = {
        "id": "a-1",
        "content": "Space A note",
        "source_refs": [{"source_file": "a.pdf", "page_number": 1, "content": "A"}],
        "created_at": 1.0,
    }
    note_b = {
        "id": "b-1",
        "content": "Space B note",
        "source_refs": [{"source_file": "b.pdf", "page_number": 2, "content": "B"}],
        "created_at": 2.0,
    }

    assert client.post("/api/v1/notes?space_id=space-a", json=note_a).status_code == 200
    assert client.post("/api/v1/notes?space_id=space-b", json=note_b).status_code == 200

    notes_a = client.get("/api/v1/notes?space_id=space-a").json()
    notes_b = client.get("/api/v1/notes?space_id=space-b").json()

    assert [note["content"] for note in notes_a] == ["Space A note"]
    assert [note["content"] for note in notes_b] == ["Space B note"]
    assert (tmp_path / "data" / "spaces" / "space-a" / "notes.json").exists()
    assert (tmp_path / "data" / "spaces" / "space-b" / "notes.json").exists()


def test_documents_upload_list_and_preview_are_space_scoped(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    ingestion = DummyIngestionService()
    monkeypatch.setattr(main, "ingestion_service", ingestion)
    monkeypatch.setattr(main, "retriever_engine", DummyRetriever())
    client = TestClient(main.app)

    upload_a = client.post(
        "/api/v1/documents/upload?space_id=space-a",
        files={"file": ("alpha.pdf", b"%PDF-1.4 alpha", "application/pdf")},
    )
    upload_b = client.post(
        "/api/v1/documents/upload?space_id=space-b",
        files={"file": ("beta.pdf", b"%PDF-1.4 beta", "application/pdf")},
    )

    assert upload_a.status_code == 200
    assert upload_b.status_code == 200
    assert upload_a.json()["filename"] == "alpha.pdf"
    assert upload_b.json()["filename"] == "beta.pdf"

    docs_a = client.get("/api/v1/documents?space_id=space-a").json()
    docs_b = client.get("/api/v1/documents?space_id=space-b").json()
    assert docs_a == [{"filename": "alpha.pdf", "display_name": "alpha.pdf"}]
    assert docs_b == [{"filename": "beta.pdf", "display_name": "beta.pdf"}]

    preview_a = client.get("/api/v1/documents/alpha.pdf/preview?space_id=space-a")
    assert preview_a.status_code == 200
    assert preview_a.json()[0]["metadata"]["source"] == "alpha.pdf"

    preview_wrong_space = client.get("/api/v1/documents/beta.pdf/preview?space_id=space-a")
    assert preview_wrong_space.status_code == 404

    assert (tmp_path / "data" / "spaces" / "space-a" / "docs" / "alpha.pdf").exists()
    assert (tmp_path / "data" / "spaces" / "space-b" / "docs" / "beta.pdf").exists()
    assert ingestion.paths[0].endswith("data/spaces/space-a/docs/alpha.pdf")


def test_default_space_can_fallback_to_legacy_docs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    legacy_docs = tmp_path / "data" / "docs"
    legacy_docs.mkdir(parents=True)
    (legacy_docs / "legacy.pdf").write_bytes(b"%PDF-1.4 legacy")

    client = TestClient(main.app)
    docs = client.get("/api/v1/documents?space_id=default")

    assert docs.status_code == 200
    assert docs.json() == [{"filename": "legacy.pdf", "display_name": "legacy.pdf"}]
