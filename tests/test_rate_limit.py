from __future__ import annotations

import concurrent.futures
import importlib
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi.middleware import SlowAPIMiddleware

from core.governance.quota_store import DailyUploadQuota, NotebookCountCap, QuotaExceededError
from core.storage.sqlite_db import get_connection, init_schema


_STUBBED_MAIN_API_MODULES = (
    "apps.api.main",
    "services.ingestion",
    "services.ingestion.service",
    "services.ingestion.filenames",
    "core.ingestion.transaction",
    "core.retrieval.retriever",
    "core.governance.prompts",
    "core.governance.gateway",
    "core.models.source",
    "core.models.studio_output",
    "core.knowledge.graph_extractor",
    "core.llm.vllm_client",
    "core.storage.notebook_store",
    "core.storage.source_registry",
    "core.storage.note_store",
    "core.storage.chat_history_store",
    "core.storage.studio_store",
    "core.storage.graph_store",
)


class _TimeTravel:
    def __init__(self) -> None:
        self._now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def set(self, year: int, month: int, day: int) -> None:
        self._now = datetime(year, month, day, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._now


def _insert_notebook(db_path: Path, owner_id: str, index: int) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO notebooks (id, name, created_at, updated_at, source_count, owner_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{owner_id}-{index}-{uuid4()}",
                f"{owner_id}-notebook-{index}",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                0,
                owner_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def api_keys_env(monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice,bob:key-bob")
    yield
    monkeypatch.delenv("NOTEBOOKLM_API_KEYS", raising=False)


@pytest.fixture(autouse=True)
def cleanup_stubbed_main_api_modules():
    yield
    sys.modules.pop("apps.api.main", None)
    for module_name in _STUBBED_MAIN_API_MODULES:
        if module_name == "apps.api.main":
            continue
        module = sys.modules.get(module_name)
        if getattr(module, "__rate_limit_stub__", False):
            sys.modules.pop(module_name, None)


@pytest.fixture
def time_travel() -> _TimeTravel:
    return _TimeTravel()


@pytest.fixture
def fresh_rate_limit_state(tmp_path, monkeypatch) -> Path:
    for env_name in (
        "NOTEBOOKLM_CHAT_RATE",
        "NOTEBOOKLM_UPLOAD_DAILY_BYTES",
        "NOTEBOOKLM_NOTEBOOK_MAX",
    ):
        monkeypatch.delenv(env_name, raising=False)

    db_path = tmp_path / "notebooks.db"
    conn = get_connection(db_path)
    init_schema(conn)
    conn.execute("DELETE FROM daily_upload_usage")
    conn.commit()
    conn.close()
    return db_path


def _build_chat_client(
    rate_limit_module,
    *,
    inject_principal: bool = False,
) -> TestClient:
    app = FastAPI()
    rate_limit_module.setup_rate_limit(app)
    app.add_middleware(SlowAPIMiddleware)

    if inject_principal:
        @app.middleware("http")
        async def add_principal(request: Request, call_next):
            principal_id = request.headers.get("x-principal-id")
            if principal_id:
                request.state.principal = SimpleNamespace(principal_id=principal_id)
            return await call_next(request)

    @app.post("/api/v1/chat")
    @rate_limit_module.limiter.limit(
        rate_limit_module._get_chat_rate,
        error_message=rate_limit_module.CHAT_RATE_EXCEEDED_DETAIL,
    )
    async def chat(request: Request):
        return {"ok": True}

    return TestClient(app)


def _load_rate_limit_module():
    import core.governance.rate_limit as rate_limit_module

    return importlib.reload(rate_limit_module)


def _stub_module(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__rate_limit_stub__ = True
    sys.modules[name] = module
    return module


def _install_main_api_stubs(tmp_path: Path) -> None:
    if "services.ingestion" not in sys.modules:
        _stub_module("services.ingestion")
    if "services.ingestion.service" not in sys.modules:
        service_mod = _stub_module("services.ingestion.service")

        class _FakeIngestionService:
            def __init__(self):
                self.vector_store = MagicMock()

            def process_file(self, *args, **kwargs):
                return 0, 0

        service_mod.IngestionService = _FakeIngestionService

    if "services.ingestion.filenames" not in sys.modules:
        filenames_mod = _stub_module("services.ingestion.filenames")
        filenames_mod.safe_upload_path = lambda upload_dir, filename, content_type=None: Path(upload_dir) / (filename or "upload.pdf")
        filenames_mod.validate_pdf_magic = lambda file_obj: None

    transaction_mod = _stub_module("core.ingestion.transaction")
    transaction_mod.DEFAULT_SPACES_DIR = tmp_path / "spaces"
    transaction_mod.IngestTransaction = MagicMock
    transaction_mod.cleanup_committed_transactions = MagicMock()
    transaction_mod.iter_space_ids = MagicMock(return_value=[])
    transaction_mod.recover_incomplete_transactions = MagicMock()
    transaction_mod.summarize_transaction_health = MagicMock(return_value={})
    transaction_mod.utc_now_iso = lambda: "2026-01-01T00:00:00+00:00"

    if "core.retrieval.retriever" not in sys.modules:
        retriever_mod = _stub_module("core.retrieval.retriever")

        class _FakeRetrieverEngine:
            def __init__(self):
                self.graph_store = None
                self.graph_extractor = None

            def retrieve(self, *args, **kwargs):
                return []

        retriever_mod.RetrieverEngine = _FakeRetrieverEngine

    if "core.governance.prompts" not in sys.modules:
        prompts_mod = _stub_module("core.governance.prompts")
        prompts_mod.QA_SYSTEM_PROMPT = "{context_blocks}"
        prompts_mod.build_context_block = lambda contexts: str(contexts)
        prompts_mod.STUDIO_PROMPTS = {
            key: "{context_blocks}"
            for key in ("summary", "faq", "briefing", "glossary", "action_items")
        }

    if "core.governance.gateway" not in sys.modules:
        gateway_mod = _stub_module("core.governance.gateway")
        gateway_mod.AntiHallucinationGateway = type(
            "_Gateway",
            (),
            {
                "validate_and_parse": staticmethod(
                    lambda raw_response, contexts: (True, "safe response", [])
                )
            },
        )

    if "core.models.source" not in sys.modules:
        source_mod = _stub_module("core.models.source")

        class _SourceStatus:
            PROCESSING = "PROCESSING"
            READY = "READY"
            FAILED = "FAILED"

        source_mod.SourceStatus = _SourceStatus

    if "core.models.studio_output" not in sys.modules:
        studio_output_mod = _stub_module("core.models.studio_output")
        studio_output_mod.StudioOutputType = type(
            "_StudioOutputType",
            (),
            {"values": staticmethod(lambda: ["summary"])},
        )

    if "core.knowledge.graph_extractor" not in sys.modules:
        graph_mod = _stub_module("core.knowledge.graph_extractor")
        graph_mod.GraphExtractor = type("_GraphExtractor", (), {})

    if "core.llm.vllm_client" not in sys.modules:
        llm_mod = _stub_module("core.llm.vllm_client")

        class _LLMConfigurationError(Exception):
            pass

        llm_mod.LLMConfigurationError = _LLMConfigurationError
        llm_mod.get_local_llm_config = lambda: SimpleNamespace(
            base_url="http://localhost:8000/v1",
            model_name="stub-model",
        )
        llm_mod.probe_local_llm = lambda: {"status": "ok"}

    for module_name in (
        "core.storage.notebook_store",
        "core.storage.source_registry",
        "core.storage.note_store",
        "core.storage.chat_history_store",
        "core.storage.studio_store",
        "core.storage.graph_store",
    ):
        if module_name not in sys.modules:
            storage_mod = _stub_module(module_name)
            class_name = "".join(part.capitalize() for part in module_name.rsplit(".", 1)[-1].split("_"))
            storage_class = type(
                class_name,
                (),
                {
                    "__init__": lambda self, *args, **kwargs: None,
                    "get": lambda self, notebook_id=None: None,
                    "list_by_notebook": lambda self, notebook_id=None: [],
                    "update": lambda self, *args, **kwargs: None,
                },
            )
            setattr(storage_mod, class_name, storage_class)


def _import_main_api(tmp_path: Path):
    _install_main_api_stubs(tmp_path)
    sys.modules.pop("apps.api.main", None)
    import apps.api.main as api_main

    api_main = importlib.reload(api_main)
    api_main._DATA_DIR = tmp_path / "data"
    api_main._DATA_DIR.mkdir(parents=True, exist_ok=True)
    api_main._DB_PATH = api_main._DATA_DIR / "notebooks.db"
    api_main.DEFAULT_SPACES_DIR = tmp_path / "spaces"
    return api_main


def test_chat_rate_limit_enforced(fresh_rate_limit_state):
    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=True)

    for _ in range(30):
        response = client.post(
            "/api/v1/chat",
            headers={"x-principal-id": "alice"},
        )
        assert response.status_code == 200

    response = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})

    assert response.status_code == 429
    assert response.json()["detail"] == rate_limit_module.CHAT_RATE_EXCEEDED_DETAIL


def test_chat_rate_limit_per_principal_isolation(fresh_rate_limit_state):
    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=True)

    for _ in range(30):
        response = client.post(
            "/api/v1/chat",
            headers={"x-principal-id": "alice"},
        )
        assert response.status_code == 200

    alice_limited = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})
    bob_allowed = client.post("/api/v1/chat", headers={"x-principal-id": "bob"})

    assert alice_limited.status_code == 429
    assert bob_allowed.status_code == 200


def test_chat_rate_limit_state_resets_per_app_instance(fresh_rate_limit_state):
    rate_limit_module = _load_rate_limit_module()
    first_client = _build_chat_client(rate_limit_module, inject_principal=True)

    for _ in range(30):
        response = first_client.post(
            "/api/v1/chat",
            headers={"x-principal-id": "alice"},
        )
        assert response.status_code == 200

    assert (
        first_client.post("/api/v1/chat", headers={"x-principal-id": "alice"}).status_code
        == 429
    )

    second_client = _build_chat_client(rate_limit_module, inject_principal=True)
    fresh_response = second_client.post(
        "/api/v1/chat",
        headers={"x-principal-id": "alice"},
    )

    assert fresh_response.status_code == 200


def test_429_response_format(fresh_rate_limit_state, monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_CHAT_RATE", "1/minute")
    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=True)

    allowed = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})
    blocked = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})

    assert allowed.status_code == 200
    assert blocked.status_code == 429
    assert blocked.json() == {
        "detail": rate_limit_module.CHAT_RATE_EXCEEDED_DETAIL,
        "retry_after": 60,
    }
    assert blocked.headers["Retry-After"] == "60"


def test_upload_daily_quota_enforced(fresh_rate_limit_state):
    store = DailyUploadQuota(db_path=fresh_rate_limit_state)

    assert store.check_and_record("alice", 499 * 1024 * 1024) == 499 * 1024 * 1024

    with pytest.raises(QuotaExceededError) as exc_info:
        store.check_and_record("alice", 2 * 1024 * 1024)

    assert exc_info.value.detail == "Rate limit exceeded: upload_bytes"
    assert exc_info.value.retry_after == 60


def test_upload_quota_persists_across_restart(fresh_rate_limit_state):
    store = DailyUploadQuota(db_path=fresh_rate_limit_state)
    assert store.check_and_record("alice", 400 * 1024 * 1024) == 400 * 1024 * 1024

    restarted_store = DailyUploadQuota(db_path=fresh_rate_limit_state)

    with pytest.raises(QuotaExceededError):
        restarted_store.check_and_record("alice", 200 * 1024 * 1024)


def test_upload_quota_rejected_write_does_not_change_usage(fresh_rate_limit_state):
    store = DailyUploadQuota(db_path=fresh_rate_limit_state)

    assert store.check_and_record("alice", 499 * 1024 * 1024) == 499 * 1024 * 1024

    with pytest.raises(QuotaExceededError):
        store.check_and_record("alice", 2 * 1024 * 1024)

    assert store.get_usage("alice") == 499 * 1024 * 1024


def test_upload_quota_resets_next_day(fresh_rate_limit_state, time_travel):
    time_travel.set(2026, 1, 1)
    store = DailyUploadQuota(db_path=fresh_rate_limit_state, now_fn=time_travel.now)
    assert store.check_and_record("alice", 500 * 1024 * 1024) == 500 * 1024 * 1024

    with pytest.raises(QuotaExceededError):
        store.check_and_record("alice", 1)

    time_travel.set(2026, 1, 2)
    assert store.check_and_record("alice", 200 * 1024 * 1024) == 200 * 1024 * 1024


def test_notebook_count_hard_cap(fresh_rate_limit_state):
    cap = NotebookCountCap(db_path=fresh_rate_limit_state)
    for index in range(50):
        _insert_notebook(fresh_rate_limit_state, "alice", index)

    with pytest.raises(QuotaExceededError) as exc_info:
        cap.check("alice")

    assert exc_info.value.detail == "Rate limit exceeded: notebook_count"
    assert exc_info.value.retry_after == 60


def test_notebook_cap_per_owner(fresh_rate_limit_state):
    cap = NotebookCountCap(db_path=fresh_rate_limit_state)
    for index in range(50):
        _insert_notebook(fresh_rate_limit_state, "alice", index)
    _insert_notebook(fresh_rate_limit_state, "bob", 0)

    with pytest.raises(QuotaExceededError):
        cap.check("alice")

    assert cap.check("bob") == 1


def test_notebook_cap_serializes_concurrent_creates(fresh_rate_limit_state):
    cap = NotebookCountCap(db_path=fresh_rate_limit_state)
    for index in range(49):
        _insert_notebook(fresh_rate_limit_state, "alice", index)

    def create_once() -> str:
        def _insert(conn):
            conn.execute(
                """
                INSERT INTO notebooks (id, name, created_at, updated_at, source_count, owner_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    "alice-concurrent",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                    0,
                    "alice",
                ),
            )
            return "created"

        return cap.execute_with_slot("alice", _insert)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(create_once) for _ in range(10)]

    created = 0
    blocked = 0
    for future in futures:
        try:
            assert future.result() == "created"
            created += 1
        except QuotaExceededError as exc:
            assert exc.detail == "Rate limit exceeded: notebook_count"
            blocked += 1

    assert created == 1
    assert blocked == 9
    assert cap.count("alice") == 50


def test_daily_upload_usage_table_atomic(fresh_rate_limit_state):
    chunk_size = 100 * 1024 * 1024
    store = DailyUploadQuota(
        db_path=fresh_rate_limit_state,
        daily_limit=3 * 1024 * 1024 * 1024,
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [
            executor.submit(store.check_and_record, "alice", chunk_size)
            for _ in range(20)
        ]
        results = [future.result() for future in futures]

    assert len(results) == 20
    assert store.get_usage("alice") == 20 * chunk_size


def test_env_override_chat_rate(fresh_rate_limit_state, monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_CHAT_RATE", "5/minute")
    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=True)

    for _ in range(5):
        response = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})
        assert response.status_code == 200

    blocked = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})

    assert blocked.status_code == 429
    assert blocked.json()["detail"] == rate_limit_module.CHAT_RATE_EXCEEDED_DETAIL


def test_env_override_invalid_format_fallback(fresh_rate_limit_state, monkeypatch, caplog):
    monkeypatch.setenv("NOTEBOOKLM_CHAT_RATE", "invalid")
    caplog.set_level("WARNING", logger="comac.rate_limit")

    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=True)

    assert rate_limit_module._get_chat_rate() == "30/minute"
    assert any(
        "NOTEBOOKLM_CHAT_RATE='invalid' is invalid" in record.getMessage()
        for record in caplog.records
    )

    response = client.post("/api/v1/chat", headers={"x-principal-id": "alice"})
    assert response.status_code == 200


def test_auth_disabled_key_func_uses_client_ip():
    rate_limit_module = _load_rate_limit_module()
    request_a = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("10.0.0.1", 1234),
            "state": {},
        }
    )
    request_b = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("10.0.0.2", 1234),
            "state": {},
        }
    )

    assert rate_limit_module._principal_key(request_a) == "ip:10.0.0.1"
    assert rate_limit_module._principal_key(request_b) == "ip:10.0.0.2"


def test_auth_disabled_falls_back_to_ip(fresh_rate_limit_state, monkeypatch):
    monkeypatch.delenv("NOTEBOOKLM_API_KEYS", raising=False)
    monkeypatch.setenv("NOTEBOOKLM_CHAT_RATE", "5/minute")
    rate_limit_module = _load_rate_limit_module()
    client = _build_chat_client(rate_limit_module, inject_principal=False)

    for _ in range(5):
        response = client.post("/api/v1/chat")
        assert response.status_code == 200

    blocked = client.post("/api/v1/chat")

    assert blocked.status_code == 429
    assert (
        blocked.json()["detail"]
        == f"Rate limit exceeded: {rate_limit_module.CHAT_RATE_DIMENSION}"
    )


def _build_admin_aware_chat_client(rate_limit_module) -> TestClient:
    """Chat client that attaches principal (with is_admin) from headers.

    Headers honored:
      x-principal-id — principal id
      x-is-admin     — "1" to flag as admin
    """
    app = FastAPI()
    rate_limit_module.setup_rate_limit(app)
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def add_principal(request: Request, call_next):
        principal_id = request.headers.get("x-principal-id")
        if principal_id:
            is_admin = request.headers.get("x-is-admin") == "1"
            request.state.principal = SimpleNamespace(
                principal_id=principal_id, is_admin=is_admin
            )
            rate_limit_module.mark_admin_request(is_admin)
        else:
            rate_limit_module.mark_admin_request(False)
        return await call_next(request)

    @app.post("/api/v1/chat")
    @rate_limit_module.limiter.limit(
        rate_limit_module._get_chat_rate,
        error_message=rate_limit_module.CHAT_RATE_EXCEEDED_DETAIL,
        exempt_when=rate_limit_module.is_admin_exempt,
    )
    async def chat(request: Request):
        return {"ok": True}

    return TestClient(app)


def test_admin_role_bypass_quota(fresh_rate_limit_state, monkeypatch):
    """V4.2-T3 Step 5: admin principals bypass the chat rate limit.

    Non-admin caller: hits the limit at N requests → 429.
    Admin caller: same endpoint, 5N requests all return 200.
    """
    monkeypatch.setenv("NOTEBOOKLM_CHAT_RATE", "3/minute")
    rate_limit_module = _load_rate_limit_module()

    # Non-admin baseline: 4th request blocked.
    non_admin_client = _build_admin_aware_chat_client(rate_limit_module)
    for _ in range(3):
        r = non_admin_client.post("/api/v1/chat", headers={"x-principal-id": "alice"})
        assert r.status_code == 200
    blocked = non_admin_client.post("/api/v1/chat", headers={"x-principal-id": "alice"})
    assert blocked.status_code == 429

    # Admin caller on a fresh app: 15 requests all pass (5× the limit).
    admin_client = _build_admin_aware_chat_client(rate_limit_module)
    for _ in range(15):
        r = admin_client.post(
            "/api/v1/chat",
            headers={"x-principal-id": "root", "x-is-admin": "1"},
        )
        assert r.status_code == 200, r.text


def test_is_admin_exempt_reads_contextvar():
    """is_admin_exempt() returns the contextvar set by mark_admin_request."""
    rate_limit_module = _load_rate_limit_module()

    rate_limit_module.mark_admin_request(False)
    assert rate_limit_module.is_admin_exempt() is False

    rate_limit_module.mark_admin_request(True)
    assert rate_limit_module.is_admin_exempt() is True

    # Reset for isolation between tests.
    rate_limit_module.mark_admin_request(False)


def test_multi_worker_warning_emitted(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    caplog.set_level("INFO", logger="comac.rate_limit")

    api_main = _import_main_api(tmp_path)
    api_main.upload_quota = None
    api_main.notebook_cap = None

    with TestClient(api_main.app) as client:
        response = client.get("/health")
        assert response.status_code == 200

    assert any(
        "rate_limit.multi_worker_warning" in record.getMessage()
        for record in caplog.records
    )
