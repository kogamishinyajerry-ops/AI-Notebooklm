from fastapi.testclient import TestClient

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
