from fastapi.testclient import TestClient
import networkx as nx

import apps.api.main as main


class DummyRetriever:
    def retrieve(self, query: str, top_k: int = 5, final_k: int = 3):
        return [
            {
                "text": "飞控系统依赖控制律保持姿态稳定。",
                "metadata": {
                    "source": "manual.pdf",
                    "page": "1",
                    "bbox": [10, 20, 30, 40],
                },
            }
        ]

    def get_by_source(self, filename: str, limit: int = 10):
        return self.retrieve(filename, top_k=limit, final_k=limit)


class DummyGraphInspector:
    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self.graph.add_node("FAA Part 25", type="regulatory")
        self.graph.add_node("Fuel Tank", type="system")
        self.graph.add_edge("FAA Part 25", "Fuel Tank", relation="governs")

    def get_stats(self):
        return {
            "nodes": 2,
            "edges": 1,
            "unsaved_chunks": 0,
            "needs_reclustering": True,
        }


class DummyCommunitySummarizer:
    def get_cached_communities(self):
        return [
            {
                "community_id": 1,
                "node_count": 2,
                "summary": "燃油系统相关的适航规则群。",
                "sources": ["manual.pdf"],
            }
        ]

    def rebuild(self):
        return {
            "status": "success",
            "communities_detected": 1,
            "communities_indexed": 1,
        }


class DummyIngestionService:
    def __init__(self):
        self.paths = []

    def process_file(self, file_path: str):
        self.paths.append(file_path)
        return 7


class FailingIngestionService:
    def process_file(self, file_path: str):
        raise RuntimeError("vector store unavailable")


def test_chat_endpoint_returns_grounded_citations(monkeypatch):
    monkeypatch.setattr(main, "get_retriever_engine", lambda: DummyRetriever())
    monkeypatch.setattr(
        main,
        "call_local_llm",
        lambda system_prompt, user_query: (
            '飞行控制律的核心是稳定性与包线保护。'
            '<citation src="manual.pdf" page="1">飞控系统依赖控制律保持姿态稳定。</citation>'
        ),
    )

    client = TestClient(main.app)
    response = client.post(
        "/api/v1/chat",
        json={"query": "请解释飞行控制律的核心要素。", "space_id": "test-space"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_fully_verified"] is True
    assert payload["citations"][0]["source_file"] == "manual.pdf"
    assert payload["citations"][0]["page_number"] == 1


def test_chat_stream_endpoint_emits_sse_events(monkeypatch):
    monkeypatch.setattr(main, "get_retriever_engine", lambda: DummyRetriever())

    async def fake_stream_local_llm(system_prompt: str, user_query: str):
        yield "飞行控制律用于维持姿态稳定。"
        yield '<citation src="manual.pdf" page="1">飞控系统依赖控制律保持姿态稳定。</citation>'

    monkeypatch.setattr(main, "stream_local_llm", fake_stream_local_llm)

    client = TestClient(main.app)
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"query": "请解释飞行控制律的核心要素。", "space_id": "test-space"},
    ) as response:
        body = "".join(chunk.decode("utf-8") for chunk in response.iter_bytes())

    assert response.status_code == 200
    assert '"type": "delta"' in body
    assert '"type": "citations"' in body
    assert '"type": "done"' in body
    assert '"is_verified": true' in body
    assert '"answer":' in body


def test_chat_stream_endpoint_returns_safe_answer_on_gateway_failure(monkeypatch):
    monkeypatch.setattr(main, "get_retriever_engine", lambda: DummyRetriever())

    async def fake_stream_local_llm(system_prompt: str, user_query: str):
        yield "未经校验的原始回答。"

    monkeypatch.setattr(main, "stream_local_llm", fake_stream_local_llm)
    monkeypatch.setattr(
        main.AntiHallucinationGateway,
        "validate_and_parse",
        lambda llm_response, contexts: (False, "[拦截] 引用校验失败，已返回安全结果。", []),
    )

    client = TestClient(main.app)
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"query": "请解释飞行控制律的核心要素。", "space_id": "test-space"},
    ) as response:
        body = "".join(chunk.decode("utf-8") for chunk in response.iter_bytes())

    assert response.status_code == 200
    assert '"type": "done"' in body
    assert '"is_verified": false' in body
    assert '[拦截] 引用校验失败，已返回安全结果。' in body


def test_artifact_endpoint_returns_verified_citations(monkeypatch):
    monkeypatch.setattr(
        main,
        "call_local_llm",
        lambda system_prompt, user_query: (
            "技术简报：飞控系统的稳定性依赖控制律设计。"
            '<citation src="manual.pdf" page="1">飞控系统依赖控制律保持姿态稳定。</citation>'
        ),
    )

    client = TestClient(main.app)
    response = client.post(
        "/api/v1/artifacts/generate",
        json={
            "artifact_type": "technical_brief",
            "topic": "飞控系统稳定性",
            "space_id": "test-space",
            "cited_sources": [
                {
                    "source_file": "manual.pdf",
                    "page_number": 1,
                    "content": "飞控系统依赖控制律保持姿态稳定。",
                    "bbox": [10, 20, 30, 40],
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "technical_brief"
    assert payload["is_fully_verified"] is True
    assert payload["citations"][0]["source_file"] == "manual.pdf"
    assert payload["citations"][0]["page_number"] == 1
    assert "技术简报" in payload["content"]


def test_knowledge_graph_endpoint_returns_graph_payload(monkeypatch):
    monkeypatch.setattr(main, "get_graph_inspector", lambda: DummyGraphInspector())
    monkeypatch.setattr(main, "get_community_summarizer", lambda: DummyCommunitySummarizer())

    client = TestClient(main.app)
    response = client.get("/api/v1/knowledge-graph?space_id=test-space")

    assert response.status_code == 200
    payload = response.json()
    assert payload["nodes"][0]["id"] == "FAA Part 25"
    assert payload["links"][0]["relation"] == "governs"
    assert payload["communities"][0]["community_id"] == 1
    assert payload["graph_stats"]["needs_reclustering"] is True


def test_knowledge_graph_rebuild_endpoint_returns_report(monkeypatch):
    monkeypatch.setattr(main, "get_community_summarizer", lambda: DummyCommunitySummarizer())

    client = TestClient(main.app)
    response = client.post("/api/v1/knowledge-graph/rebuild?space_id=test-space")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["report"]["communities_indexed"] == 1


def test_upload_document_sanitizes_filename_and_indexes(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    ingestion = DummyIngestionService()
    monkeypatch.setattr(main, "get_ingestion_service", lambda: ingestion)

    client = TestClient(main.app)
    response = client.post(
        "/api/v1/documents/upload",
        params={"space_id": "test-space"},
        files={"file": ("../../unsafe.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "unsafe.pdf"
    assert payload["chunks_indexed"] == 7
    assert ingestion.paths[0].endswith("data/docs/unsafe.pdf")
    assert (tmp_path / "data" / "docs" / "unsafe.pdf").exists()


def test_upload_document_rejects_non_pdf(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    client = TestClient(main.app)
    response = client.post(
        "/api/v1/documents/upload",
        params={"space_id": "test-space"},
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF uploads are supported"


def test_documents_list_and_preview_return_expected_payload(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    docs_dir = tmp_path / "data" / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "ops_manual.pdf").write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(main, "get_retriever_engine", lambda: DummyRetriever())

    client = TestClient(main.app)

    list_response = client.get("/api/v1/documents")
    assert list_response.status_code == 200
    assert list_response.json() == [
        {"filename": "ops_manual.pdf", "display_name": "ops manual.pdf"}
    ]

    preview_response = client.get("/api/v1/documents/ops_manual.pdf/preview")
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload[0]["metadata"]["source"] == "manual.pdf"


def test_upload_document_cleans_up_file_on_ingestion_failure(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "get_ingestion_service", lambda: FailingIngestionService())

    client = TestClient(main.app)
    response = client.post(
        "/api/v1/documents/upload",
        params={"space_id": "test-space"},
        files={"file": ("broken.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Ingestion failed: vector store unavailable"
    assert not (tmp_path / "data" / "docs" / "broken.pdf").exists()


def test_notes_roundtrip_and_export_preserve_source_refs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = TestClient(main.app)

    note_payload = {
        "id": "note-1",
        "content": "燃油箱防雷设计必须满足条款要求。",
        "source_refs": [
            {
                "source_file": "manual.pdf",
                "page_number": 3,
                "content": "燃油箱防雷设计要求见本节说明。",
            }
        ],
        "created_at": 1713146400.0,
    }

    create_response = client.post("/api/v1/notes", json=note_payload)
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "success"

    notes_response = client.get("/api/v1/notes")
    assert notes_response.status_code == 200
    notes_payload = notes_response.json()
    assert notes_payload[0]["content"] == note_payload["content"]
    assert notes_payload[0]["source_refs"][0]["source_file"] == "manual.pdf"

    export_response = client.get("/api/v1/studio/export")
    assert export_response.status_code == 200
    export_body = export_response.text
    assert "知识点记录 1" in export_body
    assert "manual.pdf p.3" in export_body
    assert "燃油箱防雷设计要求见本节说明。" in export_body
