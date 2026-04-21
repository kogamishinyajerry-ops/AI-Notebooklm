from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient

_REAL_MODEL_MODULES = (
    "core.models.chat_message",
    "core.models.graph",
    "core.models.note",
    "core.models.notebook",
    "core.models.source",
    "core.models.studio_output",
)


def _load_real_module(name: str):
    if name.startswith("services.ingestion"):
        sys.modules.pop("services", None)
        sys.modules.pop("services.ingestion", None)
    if name == "services.ingestion.parser":
        sys.modules.pop("fitz", None)
        importlib.import_module("fitz")
    if name.startswith("core.storage."):
        sys.modules.pop("core.storage", None)
    if name.startswith("core.models."):
        sys.modules.pop("core.models", None)
    if name.startswith("core.storage."):
        for module_name in _REAL_MODEL_MODULES:
            sys.modules.pop(module_name, None)
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def _load_real_fitz():
    sys.modules.pop("fitz", None)
    return importlib.import_module("fitz")


class RejectListCollection:
    def __init__(self):
        self.rows = {}

    def add(self, *, ids, embeddings, metadatas, documents):
        for metadata in metadatas:
            if isinstance(metadata.get("bbox"), list):
                raise TypeError("Expected scalar metadata value, got list")
        for doc_id, metadata, document in zip(ids, metadatas, documents):
            self.rows[doc_id] = {"metadata": metadata, "document": document}

    def delete(self, **kwargs):
        return None


class RejectListPersistentClient:
    def __init__(self, path, settings):
        self.collection = RejectListCollection()

    def get_or_create_collection(self, name):
        return self.collection


class MinimalIngestionService:
    def __init__(self, persist_directory):
        vector_store_module = _load_real_module("core.retrieval.vector_store")
        self.vector_store = vector_store_module.VectorStoreAdapter(
            persist_directory=str(persist_directory)
        )

    def process_file(
        self,
        file_path,
        space_id="default",
        source_id=None,
        transaction=None,
    ):
        PDFParser = _load_real_module("services.ingestion.parser").PDFParser

        parser = PDFParser(file_path)
        try:
            page_count = parser.page_count
            blocks = parser.extract_chunks()
        finally:
            parser.close()

        texts = []
        metadatas = []
        for block in blocks:
            metadata = dict(block.metadata)
            if source_id is not None:
                metadata["source_id"] = source_id
                metadata["space_id"] = space_id
            texts.append(block.text)
            metadatas.append(metadata)

        embeddings = [[0.0, 0.0, 0.0] for _ in texts]
        ids = self.vector_store.new_document_ids(len(texts))
        self.vector_store.add_documents(
            chunks=texts,
            metadatas=metadatas,
            embeddings=embeddings,
            ids=ids,
        )
        return len(texts), page_count


class EmptyIngestionService:
    def __init__(self):
        self.vector_store = types.SimpleNamespace(delete=lambda **kwargs: None)

    def process_file(
        self,
        file_path,
        space_id="default",
        source_id=None,
        transaction=None,
    ):
        return 0, 1


def _import_api_main(monkeypatch):
    bootstrap_ingestion = types.ModuleType("services.ingestion.service")

    class _BootstrapIngestionService:
        def __init__(self):
            self.vector_store = types.SimpleNamespace(delete=lambda **kwargs: None)

    bootstrap_ingestion.IngestionService = _BootstrapIngestionService
    monkeypatch.setitem(sys.modules, "services.ingestion.service", bootstrap_ingestion)

    bootstrap_retriever = types.ModuleType("core.retrieval.retriever")

    class _BootstrapRetrieverEngine:
        def retrieve(self, *args, **kwargs):
            return []

    bootstrap_retriever.RetrieverEngine = _BootstrapRetrieverEngine
    monkeypatch.setitem(sys.modules, "core.retrieval.retriever", bootstrap_retriever)

    for module_name in (
        "apps.api.main",
        "services",
        "services.ingestion",
        "core.knowledge",
        "core.knowledge.graph_extractor",
        "core.storage",
        "core.governance.gateway",
        "core.governance.prompts",
        "core.models",
        *_REAL_MODEL_MODULES,
        "fitz",
    ):
        sys.modules.pop(module_name, None)
    monkeypatch.setitem(sys.modules, "fitz", _load_real_fitz())
    sys.modules.pop("apps.api.main", None)
    return importlib.import_module("apps.api.main")


def _build_pdf_bytes(text):
    pymupdf = _load_real_fitz()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_upload_route_accepts_bbox_metadata_and_serves_page_preview(monkeypatch, tmp_path):
    vector_store_module = _load_real_module("core.retrieval.vector_store")
    monkeypatch.setattr(
        vector_store_module.chromadb,
        "PersistentClient",
        RejectListPersistentClient,
    )
    api_main = _import_api_main(monkeypatch)

    db_path = tmp_path / "notebooks.db"
    spaces_dir = tmp_path / "spaces"
    NotebookStore = _load_real_module("core.storage.notebook_store").NotebookStore
    SourceRegistry = _load_real_module("core.storage.source_registry").SourceRegistry
    NoteStore = _load_real_module("core.storage.note_store").NoteStore
    ChatHistoryStore = _load_real_module("core.storage.chat_history_store").ChatHistoryStore
    StudioStore = _load_real_module("core.storage.studio_store").StudioStore
    GraphStore = _load_real_module("core.storage.graph_store").GraphStore
    DailyUploadQuota = _load_real_module("core.governance.quota_store").DailyUploadQuota
    NotebookCountCap = _load_real_module("core.governance.quota_store").NotebookCountCap
    AuditStore = _load_real_module("core.governance.audit_store").AuditStore

    with TestClient(api_main.app) as client:
        api_main.notebook_store = NotebookStore(db_path=db_path, spaces_dir=spaces_dir)
        api_main.source_registry = SourceRegistry(db_path=db_path, spaces_dir=spaces_dir)
        api_main.note_store = NoteStore(db_path=db_path, spaces_dir=spaces_dir)
        api_main.chat_history_store = ChatHistoryStore(db_path=db_path, spaces_dir=spaces_dir)
        api_main.studio_store = StudioStore(db_path=db_path, spaces_dir=spaces_dir)
        api_main.graph_store = GraphStore(db_path=db_path, spaces_dir=spaces_dir)
        api_main.upload_quota = DailyUploadQuota(db_path=db_path)
        api_main.notebook_cap = NotebookCountCap(db_path=db_path)
        api_main.audit_store = AuditStore(db_path=db_path)
        api_main.ingestion_service = MinimalIngestionService(tmp_path / "vector-db")
        api_main.safe_upload_path = lambda upload_dir, filename, content_type=None: Path(upload_dir) / filename
        api_main.validate_pdf_magic = lambda file_obj: None

        notebook = client.post("/api/v1/notebooks", json={"name": "BBox Upload"}).json()
        upload = client.post(
            f"/api/v1/notebooks/{notebook['id']}/sources/upload",
            files={"file": ("bbox.pdf", _build_pdf_bytes("Lift remains bounded."), "application/pdf")},
        )

        assert upload.status_code == 200, upload.text
        source = upload.json()["source"]
        assert source["status"] == "ready"
        assert source["page_count"] == 1
        assert source["chunk_count"] >= 1

        stored_rows = list(api_main.ingestion_service.vector_store.collection.rows.values())
        assert stored_rows
        assert isinstance(stored_rows[0]["metadata"]["bbox"], str)

        page_preview = client.get(
            f"/api/v1/notebooks/{notebook['id']}/sources/{source['id']}/pages/1"
        )
        assert page_preview.status_code == 200
        assert page_preview.headers["content-type"].startswith("image/png")


def test_upload_route_marks_zero_chunk_ingestion_as_failed(monkeypatch, tmp_path):
    vector_store_module = _load_real_module("core.retrieval.vector_store")
    monkeypatch.setattr(
        vector_store_module.chromadb,
        "PersistentClient",
        RejectListPersistentClient,
    )
    api_main = _import_api_main(monkeypatch)

    db_path = tmp_path / "notebooks.db"
    spaces_dir = tmp_path / "spaces"
    NotebookStore = _load_real_module("core.storage.notebook_store").NotebookStore
    SourceRegistry = _load_real_module("core.storage.source_registry").SourceRegistry
    NoteStore = _load_real_module("core.storage.note_store").NoteStore
    ChatHistoryStore = _load_real_module("core.storage.chat_history_store").ChatHistoryStore
    StudioStore = _load_real_module("core.storage.studio_store").StudioStore
    GraphStore = _load_real_module("core.storage.graph_store").GraphStore
    DailyUploadQuota = _load_real_module("core.governance.quota_store").DailyUploadQuota
    NotebookCountCap = _load_real_module("core.governance.quota_store").NotebookCountCap
    AuditStore = _load_real_module("core.governance.audit_store").AuditStore

    with TestClient(api_main.app) as client:
        api_main.notebook_store = NotebookStore(db_path=db_path, spaces_dir=spaces_dir)
        api_main.source_registry = SourceRegistry(db_path=db_path, spaces_dir=spaces_dir)
        api_main.note_store = NoteStore(db_path=db_path, spaces_dir=spaces_dir)
        api_main.chat_history_store = ChatHistoryStore(db_path=db_path, spaces_dir=spaces_dir)
        api_main.studio_store = StudioStore(db_path=db_path, spaces_dir=spaces_dir)
        api_main.graph_store = GraphStore(db_path=db_path, spaces_dir=spaces_dir)
        api_main.upload_quota = DailyUploadQuota(db_path=db_path)
        api_main.notebook_cap = NotebookCountCap(db_path=db_path)
        api_main.audit_store = AuditStore(db_path=db_path)
        api_main.ingestion_service = EmptyIngestionService()
        api_main.safe_upload_path = lambda upload_dir, filename, content_type=None: Path(upload_dir) / filename
        api_main.validate_pdf_magic = lambda file_obj: None

        notebook = client.post("/api/v1/notebooks", json={"name": "Empty Upload"}).json()
        upload = client.post(
            f"/api/v1/notebooks/{notebook['id']}/sources/upload",
            files={"file": ("empty.pdf", _build_pdf_bytes("Preview only."), "application/pdf")},
        )

        assert upload.status_code == 422, upload.text
        assert "no retrievable chunks" in upload.json()["detail"].lower()

        sources = client.get(f"/api/v1/notebooks/{notebook['id']}/sources").json()
        assert len(sources) == 1
        assert sources[0]["status"] == "failed"
        assert "no retrievable chunks" in (sources[0]["error_message"] or "").lower()
