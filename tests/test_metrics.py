from __future__ import annotations

import sys

import pytest

from tests.test_observability import _build_client

from core.observability.metrics import MetricsRegistry, is_loopback_client


@pytest.fixture(autouse=True)
def _cleanup_api_module():
    yield
    for name in (
        "apps.api.main",
        "services.ingestion",
        "services.ingestion.service",
        "services.ingestion.filenames",
        "core.ingestion.transaction",
        "core.governance.prompts",
        "core.governance.gateway",
        "core.models.source",
        "core.models.studio_output",
        "core.storage.notebook_store",
        "core.storage.source_registry",
        "core.storage.note_store",
        "core.storage.chat_history_store",
        "core.storage.studio_store",
        "core.storage.graph_store",
        "core.knowledge.graph_extractor",
    ):
        module = sys.modules.get(name)
        if module is not None and not getattr(module, "__file__", None):
            sys.modules.pop(name, None)


def test_metrics_disabled_by_default(monkeypatch):
    monkeypatch.delenv("NOTEBOOKLM_METRICS_ENABLED", raising=False)
    monkeypatch.delenv("NOTEBOOKLM_METRICS_ALLOW_REMOTE", raising=False)
    client = _build_client(monkeypatch)

    resp = client.get("/metrics")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Metrics disabled"


def test_metrics_restricts_non_loopback_by_default(monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_METRICS_ENABLED", "1")
    monkeypatch.delenv("NOTEBOOKLM_METRICS_ALLOW_REMOTE", raising=False)
    client = _build_client(monkeypatch)

    resp = client.get("/metrics")

    # Starlette's TestClient presents as host "testclient", which is not loopback.
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Metrics restricted to loopback"


def test_metrics_endpoint_emits_prometheus_text_when_explicitly_remote_allowed(monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_METRICS_ENABLED", "true")
    monkeypatch.setenv("NOTEBOOKLM_METRICS_ALLOW_REMOTE", "true")
    client = _build_client(monkeypatch)

    health = client.get("/health")
    resp = client.get("/metrics")

    assert health.status_code == 200
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "# TYPE notebooklm_uptime_seconds gauge" in body
    assert "# TYPE notebooklm_http_requests_total counter" in body
    assert 'notebooklm_http_requests_total{method="GET",path="/health",status="200"} 1' in body


def test_loopback_detection_does_not_trust_testclient_or_private_lan_hosts():
    assert is_loopback_client("127.0.0.1") is True
    assert is_loopback_client("127.10.20.30") is True
    assert is_loopback_client("localhost") is True
    assert is_loopback_client("::1") is True

    assert is_loopback_client("testclient") is False
    assert is_loopback_client("10.0.0.5") is False
    assert is_loopback_client("") is False
    assert is_loopback_client(None) is False


def test_metrics_registry_escapes_labels_and_tracks_duration():
    registry = MetricsRegistry(started_at=100.0)
    registry.observe_http_request(
        method="get",
        path='/api/v1/notebooks/"demo"',
        status_code=200,
        duration_ms=12.3456,
    )

    rendered = registry.render_prometheus(now=103.0)

    assert "notebooklm_uptime_seconds 3.000" in rendered
    assert (
        'notebooklm_http_requests_total{method="GET",'
        'path="/api/v1/notebooks/\\"demo\\"",status="200"} 1'
    ) in rendered
    assert "notebooklm_http_request_duration_ms_sum" in rendered
    assert "12.346" in rendered
