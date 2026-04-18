from fastapi import Depends, FastAPI, HTTPException, UploadFile, File
from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from pathlib import Path
import shutil
import os
import sys
import sqlite3
import requests
import logging
import time
import uuid

# Ensure root is in path for local service imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.ingestion.service import IngestionService
from services.ingestion.filenames import safe_upload_path, validate_pdf_magic
from core.ingestion.transaction import (
    IngestTransaction,
    cleanup_committed_transactions,
    iter_space_ids,
    recover_incomplete_transactions,
    summarize_transaction_health,
)
from core.retrieval.retriever import RetrieverEngine
from core.governance.prompts import QA_SYSTEM_PROMPT, build_context_block
from core.governance.gateway import AntiHallucinationGateway
from core.models.source import SourceStatus
from core.models.studio_output import StudioOutputType
from core.governance.prompts import STUDIO_PROMPTS

# V4.1-T2: Central DB path — all stores share the same SQLite DB
_DATA_DIR = Path("data")
_DB_PATH = _DATA_DIR / "notebooks.db"
# Mirrored from core.ingestion.transaction to avoid triggering that import
# (which is stubbed by test_cross_notebook_isolation.py) at module load time.
DEFAULT_SPACES_DIR = Path("data/spaces")
from core.knowledge.graph_extractor import GraphExtractor
from core.llm.vllm_client import (
    LLMConfigurationError,
    get_local_llm_config,
    probe_local_llm,
)
from core.security.auth import (
    AuthPrincipal,
    auth_is_enabled,
    get_current_principal as _auth_get_current_principal,
)
from core.governance.audit_events import AuditEvent
from core.governance.audit_logger import AuditLogger
from core.governance.quota_store import DailyUploadQuota, NotebookCountCap, QuotaExceededError
from core.governance.rate_limit import (
    CHAT_RATE_EXCEEDED_DETAIL,
    _get_chat_rate,
    is_admin_exempt,
    limiter,
    mark_admin_request,
    rate_limit_exception_handler,
    setup_rate_limit,
)
from core.models.notebook import Notebook
from core.observability.logging_utils import emit_json_log
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

app = FastAPI(title="COMAC Intelligent NotebookLM API")
setup_rate_limit(app)
app.add_middleware(SlowAPIMiddleware)
logger = logging.getLogger("comac.api")

# Initialize shared services (non-storage)
ingestion_service = IngestionService()
retriever_engine = RetrieverEngine()
graph_extractor = GraphExtractor()
upload_quota: Optional[DailyUploadQuota] = None
notebook_cap: Optional[NotebookCountCap] = None
audit_logger: Optional[AuditLogger] = None

# V4.1-T2: Storage store placeholders — initialized in on_startup (after all imports)
# Deferred import avoids triggering core.storage.sqlite_db when test_cross_notebook_isolation
# stubs core.storage as SimpleNamespace (which lacks sqlite_db submodule).
notebook_store = None
source_registry = None
note_store = None
chat_history_store = None
studio_store = None
graph_store = None


@app.on_event("startup")
def on_startup():
    # V4.1-T2: Deferred imports — avoid triggering sqlite_db when core.storage is stubbed
    global notebook_store, source_registry, note_store, chat_history_store, studio_store, graph_store
    global upload_quota, notebook_cap, audit_logger
    from core.storage.sqlite_db import run_migration_if_needed
    from core.storage.notebook_store import NotebookStore
    from core.storage.source_registry import SourceRegistry
    from core.storage.note_store import NoteStore
    from core.storage.chat_history_store import ChatHistoryStore
    from core.storage.studio_store import StudioStore
    from core.storage.graph_store import GraphStore

    # Run JSON → SQLite migration if not yet done
    result = run_migration_if_needed(
        base_dir=_DATA_DIR,
        db_path=_DB_PATH,
        spaces_dir=DEFAULT_SPACES_DIR,
    )
    if result.success and result.version == 1 and result.counts:
        logger.info(
            "V4.1-T2 migration complete: %s records migrated in %.1fms",
            result.counts, result.duration_ms
        )

    # Initialize storage stores
    notebook_store = NotebookStore(db_path=_DB_PATH, spaces_dir=DEFAULT_SPACES_DIR)
    source_registry = SourceRegistry(db_path=_DB_PATH, spaces_dir=DEFAULT_SPACES_DIR)
    note_store = NoteStore(db_path=_DB_PATH, spaces_dir=DEFAULT_SPACES_DIR)
    chat_history_store = ChatHistoryStore(db_path=_DB_PATH, spaces_dir=DEFAULT_SPACES_DIR)
    studio_store = StudioStore(db_path=_DB_PATH, spaces_dir=DEFAULT_SPACES_DIR)
    graph_store = GraphStore(db_path=_DB_PATH, spaces_dir=DEFAULT_SPACES_DIR)
    if upload_quota is None:
        upload_quota = DailyUploadQuota(db_path=_DB_PATH)
    if notebook_cap is None:
        notebook_cap = NotebookCountCap(db_path=_DB_PATH)
    if audit_logger is None:
        audit_logger = AuditLogger(db_path=_DB_PATH)
    app.state.audit_logger = audit_logger
    setup_rate_limit(app)

    # Gap-A: inject graph signal into the retriever
    retriever_engine.graph_store = graph_store
    retriever_engine.graph_extractor = graph_extractor

    # Existing: recover ingestion transactions
    for space_id in iter_space_ids():
        recover_incomplete_transactions(
            space_id,
            vector_store=ingestion_service.vector_store,
            registry=source_registry,
            base_dir=source_registry.spaces_dir,
        )
        cleanup_committed_transactions(space_id, base_dir=source_registry.spaces_dir)
        notebook = notebook_store.get(space_id)
        if notebook is not None:
            notebook_store.update(space_id, source_count=len(source_registry.list_by_notebook(space_id)))


@app.middleware("http")
async def add_request_observability(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    started_at = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        emit_json_log(
            logger,
            "http.request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=500,
            duration_ms=duration_ms,
            error=exc.__class__.__name__,
        )
        raise

    response.headers["X-Request-ID"] = request_id
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    emit_json_log(
        logger,
        "http.request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response

# Mount static files
static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(static_path, "index.html"))

# Domain Models
class Citation(BaseModel):
    source_file: str
    page_number: int
    content: str
    bbox: Optional[List[float]] = None

class ChatRequest(BaseModel):
    query: str
    # notebook_id is the canonical field; space_id is accepted as a legacy alias.
    notebook_id: Optional[str] = None
    space_id: Optional[str] = None
    history: Optional[List[dict]] = None
    save_history: bool = True  # set False to skip chat history persistence

    @property
    def resolved_notebook_id(self) -> Optional[str]:
        """Return notebook_id, falling back to space_id for legacy clients."""
        return self.notebook_id or self.space_id

class ChatResponse(BaseModel):
    answer: str
    is_fully_verified: bool
    citations: List[Citation]

class NotebookCreateRequest(BaseModel):
    name: str


def _principal_owner_id(principal: Optional[AuthPrincipal]) -> Optional[str]:
    return principal.principal_id if principal else None


def get_current_principal(request: Request) -> Optional[AuthPrincipal]:
    principal = _auth_get_current_principal(request)
    request.state.principal = principal
    mark_admin_request(bool(getattr(principal, "is_admin", False)))
    return principal


@app.exception_handler(QuotaExceededError)
async def handle_quota_exceeded(
    request: Request,
    exc: QuotaExceededError,
) -> JSONResponse:
    _record_quota_denied(request, dimension=exc.dimension)
    return JSONResponse(
        status_code=429,
        content={"detail": exc.detail, "retry_after": exc.retry_after},
        headers={"Retry-After": str(exc.retry_after)},
    )


@app.exception_handler(RateLimitExceeded)
async def handle_rate_limit_exceeded(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    detail = getattr(exc, "detail", CHAT_RATE_EXCEEDED_DETAIL) or CHAT_RATE_EXCEEDED_DETAIL
    dimension = str(detail).split(": ", 1)[1] if ": " in str(detail) else "chat_requests"
    _record_quota_denied(request, dimension=dimension)
    return rate_limit_exception_handler(request, exc)


@app.exception_handler(HTTPException)
async def handle_http_exception(
    request: Request,
    exc: HTTPException,
) -> Response:
    if exc.status_code in (401, 403):
        get_audit_logger(request).record(
            request=request,
            event=AuditEvent.AUTH_DENIED,
            outcome="failure",
            resource_type="-",
            resource_id="-",
            parent_resource_id="-",
            http_status=exc.status_code,
            error_code=_auth_denied_error_code(exc),
        )
    return await http_exception_handler(request, exc)


def _get_upload_quota() -> DailyUploadQuota:
    global upload_quota
    if upload_quota is None:
        upload_quota = DailyUploadQuota(db_path=_DB_PATH)
    return upload_quota


def _get_notebook_cap() -> NotebookCountCap:
    global notebook_cap
    if notebook_cap is None:
        notebook_cap = NotebookCountCap(db_path=_DB_PATH)
    return notebook_cap


def get_audit_logger(request: Request) -> AuditLogger:
    logger_instance = getattr(request.app.state, "audit_logger", None)
    if logger_instance is not None:
        return logger_instance

    global audit_logger
    if audit_logger is None:
        audit_logger = AuditLogger(db_path=_DB_PATH)
    request.app.state.audit_logger = audit_logger
    return audit_logger


def _audit_error_code(status_code: int) -> str:
    codes = {
        400: "bad_request",
        401: "auth_required",
        403: "auth_denied",
        404: "not_found",
        422: "validation_error",
        429: "quota_denied",
        500: "internal_error",
        503: "service_unavailable",
    }
    return codes.get(status_code, f"http_{status_code}")


def _record_audit_success(
    request: Request,
    *,
    event: AuditEvent,
    resource_type: str,
    http_status: int,
    resource_id: str = "-",
    parent_resource_id: str = "-",
    payload: Optional[dict] = None,
) -> None:
    get_audit_logger(request).record(
        request=request,
        event=event,
        outcome="success",
        resource_type=resource_type,
        resource_id=resource_id,
        parent_resource_id=parent_resource_id,
        http_status=http_status,
        payload=payload,
    )


def _record_audit_failure(
    request: Request,
    *,
    event: AuditEvent,
    resource_type: str,
    http_status: int,
    error_code: str,
    resource_id: str = "-",
    parent_resource_id: str = "-",
    payload: Optional[dict] = None,
) -> None:
    if http_status in (401, 403):
        return

    get_audit_logger(request).record(
        request=request,
        event=event,
        outcome="failure",
        resource_type=resource_type,
        resource_id=resource_id,
        parent_resource_id=parent_resource_id,
        http_status=http_status,
        error_code=error_code,
        payload=payload,
    )


def _record_quota_denied(
    request: Request,
    *,
    dimension: str,
) -> None:
    get_audit_logger(request).record(
        request=request,
        event=AuditEvent.QUOTA_DENIED,
        outcome="failure",
        resource_type="-",
        resource_id="-",
        parent_resource_id="-",
        http_status=429,
        error_code=f"quota_{dimension}",
        payload={"quota.dimension": dimension},
    )


def _auth_denied_error_code(exc: HTTPException) -> str:
    detail = str(exc.detail).lower() if exc.detail is not None else ""
    if exc.status_code == 401 and "required" in detail:
        return "auth_required"
    if exc.status_code == 401 and "invalid" in detail:
        return "auth_invalid_api_key"
    return "auth_denied"


def _build_notebook(name: str, owner_id: Optional[str]) -> Notebook:
    try:
        from core.ingestion.transaction import utc_now_iso as _utc_now_iso
        now = _utc_now_iso()
    except (ImportError, AttributeError):
        now = datetime.now(timezone.utc).isoformat()
    return Notebook(
        id=str(uuid.uuid4()),
        name=name.strip(),
        created_at=now,
        updated_at=now,
        source_count=0,
        owner_id=owner_id,
    )


def _insert_notebook_row(conn: sqlite3.Connection, notebook: Notebook) -> None:
    conn.execute(
        """INSERT INTO notebooks
           (id, name, created_at, updated_at, source_count, owner_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            notebook.id,
            notebook.name,
            notebook.created_at,
            notebook.updated_at,
            notebook.source_count,
            notebook.owner_id,
        ),
    )


def _create_owned_notebook(name: str, owner_id: Optional[str]) -> Notebook:
    store_module = getattr(getattr(notebook_store, "__class__", None), "__module__", "")
    if owner_id is None or store_module != "core.storage.notebook_store":
        return notebook_store.create(name, owner_id=owner_id)

    notebook = _build_notebook(name, owner_id)
    _get_notebook_cap().execute_with_slot(
        owner_id,
        lambda conn: _insert_notebook_row(conn, notebook),
    )
    (DEFAULT_SPACES_DIR / notebook.id).mkdir(parents=True, exist_ok=True)
    return notebook


def _require_notebook_access(
    notebook_id: str,
    principal: Optional[AuthPrincipal],
):
    notebook = notebook_store.get(notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail="Notebook not found")

    if auth_is_enabled():
        owner_id = getattr(notebook, "owner_id", None)
        if owner_id != _principal_owner_id(principal):
            raise HTTPException(status_code=403, detail="Notebook access denied")

    return notebook


def _measure_upload_bytes(upload: UploadFile) -> int:
    original_position = upload.file.tell()
    upload.file.seek(0, os.SEEK_END)
    size = upload.file.tell()
    upload.file.seek(original_position)
    return size

# --- Notes models ---
class NoteCreateRequest(BaseModel):
    content: str
    citations: Optional[List[dict]] = None
    title: Optional[str] = None

class NotePatchRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

# Routes
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "COMAC NotebookLM"}

@app.get("/api/v1/health")
def api_health_check():
    return {
        "status": "ok",
        "service": "COMAC NotebookLM",
        "transactions": summarize_transaction_health(base_dir=source_registry.spaces_dir),
    }

@app.get("/api/v1/llm/health")
def llm_health_check():
    try:
        return probe_local_llm()
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@app.post("/api/v1/spaces")
def create_space(
    request: Request,
    name: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Legacy alias for creating a notebook-backed knowledge space."""
    owner_id = _principal_owner_id(principal)
    audit_payload = {"title": name}
    try:
        notebook = _create_owned_notebook(name, owner_id)
    except ValueError as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.SPACE_CREATE,
            resource_type="space",
            http_status=400,
            error_code=_audit_error_code(400),
            payload=audit_payload,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_audit_success(
        request,
        event=AuditEvent.SPACE_CREATE,
        resource_type="space",
        resource_id=notebook.id,
        http_status=200,
        payload={"title": notebook.name, "space_id": notebook.id},
    )
    return {"space_id": notebook.id, "name": notebook.name}

@app.post("/api/v1/notebooks", status_code=201)
def create_notebook(
    request: Request,
    payload: NotebookCreateRequest,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    owner_id = _principal_owner_id(principal)
    audit_payload = {"title": payload.name}
    try:
        notebook = _create_owned_notebook(payload.name, owner_id)
    except ValueError as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.NOTEBOOK_CREATE,
            resource_type="notebook",
            http_status=400,
            error_code=_audit_error_code(400),
            payload=audit_payload,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_audit_success(
        request,
        event=AuditEvent.NOTEBOOK_CREATE,
        resource_type="notebook",
        resource_id=notebook.id,
        http_status=201,
        payload={"title": notebook.name, "notebook_id": notebook.id},
    )
    return notebook.to_dict()

@app.get("/api/v1/notebooks")
def list_notebooks(
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    notebooks = notebook_store.list_all()
    if auth_is_enabled():
        owner_id = _principal_owner_id(principal)
        notebooks = [
            notebook
            for notebook in notebooks
            if getattr(notebook, "owner_id", None) == owner_id
        ]
    return [notebook.to_dict() for notebook in notebooks]

@app.get("/api/v1/notebooks/{notebook_id}")
def get_notebook(
    notebook_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    notebook = _require_notebook_access(notebook_id, principal)
    return notebook.to_dict()

@app.delete("/api/v1/notebooks/{notebook_id}", status_code=204)
def delete_notebook(
    request: Request,
    notebook_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    audit_payload = {"notebook_id": notebook_id}
    try:
        _require_notebook_access(notebook_id, principal)

        for source in source_registry.list_by_notebook(notebook_id):
            ingestion_service.vector_store.delete(where={"source_id": source.id})

        if not notebook_store.delete(notebook_id):
            raise HTTPException(status_code=404, detail="Notebook not found")
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.NOTEBOOK_DELETE,
            resource_type="notebook",
            resource_id=notebook_id,
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload=audit_payload,
        )
        raise
    _record_audit_success(
        request,
        event=AuditEvent.NOTEBOOK_DELETE,
        resource_type="notebook",
        resource_id=notebook_id,
        http_status=204,
        payload=audit_payload,
    )

@app.get("/api/v1/notebooks/{notebook_id}/sources")
def list_sources(
    notebook_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    _require_notebook_access(notebook_id, principal)
    return [source.to_dict() for source in source_registry.list_by_notebook(notebook_id)]

@app.get("/api/v1/notebooks/{notebook_id}/sources/{source_id}")
def get_source(
    notebook_id: str,
    source_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    _require_notebook_access(notebook_id, principal)
    source = source_registry.get(notebook_id, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source.to_dict()

@app.delete("/api/v1/notebooks/{notebook_id}/sources/{source_id}", status_code=204)
def delete_source(
    request: Request,
    notebook_id: str,
    source_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    audit_payload = {"notebook_id": notebook_id, "source_id": source_id}
    try:
        _require_notebook_access(notebook_id, principal)
        source = source_registry.get(notebook_id, source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Source not found")

        ingestion_service.vector_store.delete(where={"source_id": source_id})
        Path(source.file_path).unlink(missing_ok=True)
        source_registry.delete(notebook_id, source_id)
        notebook_store.increment_source_count(notebook_id, -1)
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.SOURCE_DELETE,
            resource_type="source",
            resource_id=source_id,
            parent_resource_id=notebook_id,
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload=audit_payload,
        )
        raise
    _record_audit_success(
        request,
        event=AuditEvent.SOURCE_DELETE,
        resource_type="source",
        resource_id=source_id,
        parent_resource_id=notebook_id,
        http_status=204,
        payload=audit_payload,
    )

class LLMUnavailableError(Exception):
    """Raised when the local vLLM service cannot be reached."""


def invoke_local_llm(system_prompt: str, user_query: str) -> str:
    """
    Invokes local vLLM (Qwen-2.5/GLM-4) via OpenAI-compatible API.

    Raises:
        LLMUnavailableError: If the vLLM service is unreachable or returns
            a non-2xx response, so callers can return HTTP 503.
    """
    try:
        config = get_local_llm_config()
    except LLMConfigurationError as exc:
        raise LLMUnavailableError(str(exc)) from exc

    try:
        resp = requests.post(
            f"{config.base_url}/chat/completions",
            json={
                "model": config.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query},
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        raise LLMUnavailableError(
            f"Local LLM service unavailable at {config.base_url}: {exc}"
        ) from exc

@app.post("/api/v1/chat", response_model=ChatResponse)
@limiter.limit(
    _get_chat_rate,
    error_message=CHAT_RATE_EXCEEDED_DETAIL,
    exempt_when=is_admin_exempt,
)
async def chat_endpoint(
    request: Request,
    chat_request: ChatRequest,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """
    Core Q&A endpoint.
    Triggers RAG retrieval scoped to the notebook's sources, LLM generation,
    and Gateway citation validation.

    Returns HTTP 400 if the notebook does not exist.
    Returns HTTP 503 if the local LLM service is unavailable.
    """
    notebook_id = chat_request.resolved_notebook_id
    audit_payload = {
        "notebook_id": notebook_id or "-",
        "chat.message_length": len(chat_request.query or ""),
        "chat.history_turns": len(chat_request.history or []),
    }

    try:
        # 1. Resolve notebook and its source_ids for retrieval scoping
        source_ids: list[str] | None = None
        if notebook_id:
            notebook = notebook_store.get(notebook_id)
            if notebook is None:
                raise HTTPException(status_code=400, detail=f"Notebook '{notebook_id}' not found")
            if auth_is_enabled():
                owner_id = getattr(notebook, "owner_id", None)
                if owner_id != _principal_owner_id(principal):
                    raise HTTPException(status_code=403, detail="Notebook access denied")
            sources = source_registry.list_by_notebook(notebook_id)
            source_ids = [s.id for s in sources] if sources else []
            if not source_ids:
                response = ChatResponse(
                    answer="未在当前知识库中检索到相关内容，请上传相关文档后再试。",
                    is_fully_verified=False,
                    citations=[],
                )
                _record_audit_success(
                    request,
                    event=AuditEvent.CHAT_REQUEST,
                    resource_type="chat",
                    resource_id="-",
                    parent_resource_id=notebook_id or "-",
                    http_status=200,
                    payload=audit_payload,
                )
                return response

        # 2. Retrieve — scoped to this notebook's source_ids when available
        retrieval_started_at = time.perf_counter()
        contexts = retriever_engine.retrieve(
            chat_request.query,
            top_k=5,
            final_k=3,
            source_ids=source_ids if source_ids else None,
            notebook_id=notebook_id,
        )
        retrieval_duration_ms = round((time.perf_counter() - retrieval_started_at) * 1000, 2)

        if not contexts:
            emit_json_log(
                logger,
                "retrieval.summary",
                request_id=getattr(request.state, "request_id", None),
                notebook_id=notebook_id,
                source_scope_size=len(source_ids or []),
                contexts_returned=0,
                citations_returned=0,
                retrieval_duration_ms=retrieval_duration_ms,
                is_fully_verified=False,
                llm_available=None,
            )
            response = ChatResponse(
                answer="未在当前知识库中检索到相关内容，请上传相关文档后再试。",
                is_fully_verified=False,
                citations=[],
            )
            _record_audit_success(
                request,
                event=AuditEvent.CHAT_REQUEST,
                resource_type="chat",
                resource_id="-",
                parent_resource_id=notebook_id or "-",
                http_status=200,
                payload=audit_payload,
            )
            return response

        # 3. Build Prompt
        context_str = build_context_block(contexts)
        system_prompt = QA_SYSTEM_PROMPT.format(context_blocks=context_str)

        # 4. Generate (LLM) — raise 503 if service unavailable
        try:
            raw_response = invoke_local_llm(system_prompt, chat_request.query)
        except LLMUnavailableError as exc:
            emit_json_log(
                logger,
                "retrieval.summary",
                request_id=getattr(request.state, "request_id", None),
                notebook_id=notebook_id,
                source_scope_size=len(source_ids or []),
                contexts_returned=len(contexts),
                citations_returned=0,
                retrieval_duration_ms=retrieval_duration_ms,
                is_fully_verified=False,
                llm_available=False,
            )
            raise HTTPException(
                status_code=503,
                detail=f"LLM service unavailable. Please ensure vLLM is running. ({exc})",
            ) from exc

        # 5. Anti-Hallucination Gate
        is_valid, safe_response, verified_citations = AntiHallucinationGateway.validate_and_parse(
            raw_response, contexts
        )

        citations_data = [
            Citation(
                source_file=c["source_file"],
                page_number=c["page_number"],
                content=c["content"],
                bbox=c["bbox"],
            )
            for c in verified_citations
        ]

        # 6. Persist chat history
        if chat_request.save_history and notebook_id:
            try:
                chat_history_store.append(notebook_id, "user", chat_request.query)
                chat_history_store.append(
                    notebook_id,
                    "assistant",
                    safe_response,
                    citations=[c.model_dump() for c in citations_data],
                    is_fully_verified=is_valid,
                )
            except Exception:
                pass  # history persistence must never break the response

        emit_json_log(
            logger,
            "retrieval.summary",
            request_id=getattr(request.state, "request_id", None),
            notebook_id=notebook_id,
            source_scope_size=len(source_ids or []),
            contexts_returned=len(contexts),
            citations_returned=len(citations_data),
            retrieval_duration_ms=retrieval_duration_ms,
            is_fully_verified=is_valid,
            llm_available=True,
        )

        response = ChatResponse(
            answer=safe_response,
            is_fully_verified=is_valid,
            citations=citations_data,
        )
        _record_audit_success(
            request,
            event=AuditEvent.CHAT_REQUEST,
            resource_type="chat",
            resource_id="-",
            parent_resource_id=notebook_id or "-",
            http_status=200,
            payload=audit_payload,
        )
        return response
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.CHAT_REQUEST,
            resource_type="chat",
            resource_id="-",
            parent_resource_id=notebook_id or "-",
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload=audit_payload,
        )
        raise

@app.post("/api/v1/notebooks/{notebook_id}/sources/upload")
async def upload_source(
    request: Request,
    notebook_id: str,
    file: UploadFile = File(...),
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Uploads and triggers ingestion for a document."""
    upload_bytes = _measure_upload_bytes(file)
    audit_payload = {
        "notebook_id": notebook_id,
        "source_type": "upload",
        "content_type": file.content_type,
        "bytes_size": upload_bytes,
        "filename": file.filename or "",
    }
    source = None
    try:
        _require_notebook_access(notebook_id, principal)
        owner_id = _principal_owner_id(principal)
        if owner_id is not None:
            _get_upload_quota().check_and_record(owner_id, upload_bytes)

        upload_dir = source_registry.spaces_dir / notebook_id / "docs"
        os.makedirs(upload_dir, exist_ok=True)
        try:
            file_path = safe_upload_path(upload_dir, file.filename, file.content_type)
            validate_pdf_magic(file.file)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        source = source_registry.register(notebook_id, file_path.name, str(file_path))
        notebook_store.increment_source_count(notebook_id, 1)
        transaction = IngestTransaction(space_id=notebook_id, base_dir=source_registry.spaces_dir)
        transaction.record_source(notebook_id, source.id)

        try:
            source_registry.update_status(notebook_id, source.id, SourceStatus.PROCESSING)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            transaction.record_file(file_path)

            chunk_count, page_count = ingestion_service.process_file(
                str(file_path),
                space_id=notebook_id,
                source_id=source.id,
                transaction=transaction,
            )
            source = source_registry.update_status(
                notebook_id,
                source.id,
                SourceStatus.READY,
                page_count=page_count,
                chunk_count=chunk_count,
            )
        except Exception as exc:
            try:
                source_registry.update_status(notebook_id, source.id, SourceStatus.FAILED, error_message=str(exc))
            except Exception:
                pass
            if transaction.status == "in_progress":
                transaction.rollback(
                    vector_store=ingestion_service.vector_store,
                    registry=getattr(ingestion_service, "parameter_registry", None),
                )
            raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(exc)}") from exc

        _record_audit_success(
            request,
            event=AuditEvent.SOURCE_UPLOAD,
            resource_type="source",
            resource_id=source.id,
            parent_resource_id=notebook_id,
            http_status=200,
            payload={
                **audit_payload,
                "source_id": source.id,
            },
        )
        return {
            "source": source.to_dict(),
            "filename": source.filename,
            "space_id": notebook_id,
            "chunks_indexed": chunk_count,
            "status": "completed"
        }
    except QuotaExceededError:
        raise
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.SOURCE_UPLOAD,
            resource_type="source",
            resource_id=getattr(source, "id", "-"),
            parent_resource_id=notebook_id,
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload={
                **audit_payload,
                **({"source_id": source.id} if getattr(source, "id", None) else {}),
            },
        )
        raise

@app.post("/api/v1/documents/upload")
async def upload_document(
    request: Request,
    space_id: str,
    file: UploadFile = File(...),
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Legacy upload route, backed by notebook sources."""
    _require_notebook_access(space_id, principal)
    return await upload_source(request, space_id, file, principal)


# ---------------------------------------------------------------------------
# S-19: PDF Source Viewer endpoints
# ---------------------------------------------------------------------------

def _resolve_source_for_file(
    notebook_id: str,
    source_id: str,
    principal: Optional[AuthPrincipal],
):
    """Helper: resolve and validate notebook + source, returning the Source object."""
    _require_notebook_access(notebook_id, principal)
    source = source_registry.get(notebook_id, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


def _safe_source_path(source, spaces_dir: Path) -> Path:
    """
    Return resolved file path, raising 403 if it escapes the spaces directory.
    Prevents path traversal attacks.
    """
    file_path = Path(source.file_path).resolve()
    spaces_resolved = spaces_dir.resolve()
    try:
        file_path.relative_to(spaces_resolved)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Access denied: source file is outside the permitted storage area.",
        )
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Source file not found on disk")
    return file_path


@app.get("/api/v1/notebooks/{notebook_id}/sources/{source_id}/file")
def serve_source_file(
    notebook_id: str,
    source_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """
    Stream the raw PDF file for a source.
    Used by the frontend PDF viewer to load the document.
    """
    source = _resolve_source_for_file(notebook_id, source_id, principal)
    file_path = _safe_source_path(source, source_registry.spaces_dir)
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=source.filename,
    )


@app.get("/api/v1/notebooks/{notebook_id}/sources/{source_id}/pages/{page_number}")
def render_source_page(
    notebook_id: str,
    source_id: str,
    page_number: int,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """
    Render a single PDF page as a PNG image at 144 DPI (2× scale).
    page_number is 1-indexed.
    Used by the frontend canvas renderer for citation evidence display.
    """
    import fitz  # PyMuPDF — local, C1 compliant

    source = _resolve_source_for_file(notebook_id, source_id, principal)
    file_path = _safe_source_path(source, source_registry.spaces_dir)

    # Validate page range
    if source.page_count is not None:
        if page_number < 1 or page_number > source.page_count:
            raise HTTPException(
                status_code=422,
                detail=f"Page {page_number} out of range (1–{source.page_count})",
            )

    try:
        doc = fitz.open(str(file_path))
        # fitz uses 0-indexed pages
        page = doc[page_number - 1]
        mat = fitz.Matrix(2.0, 2.0)  # 144 DPI
        pix = page.get_pixmap(matrix=mat, alpha=False)
        png_bytes = pix.tobytes("png")
        doc.close()
    except IndexError:
        raise HTTPException(status_code=422, detail=f"Page {page_number} not found in document")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Page render failed: {exc}")

    return Response(content=png_bytes, media_type="image/png")


# ---------------------------------------------------------------------------
# S-20: Chat History endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/notebooks/{notebook_id}/history")
def get_chat_history(
    notebook_id: str,
    limit: int = 100,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Return the most recent chat messages for a notebook."""
    _require_notebook_access(notebook_id, principal)
    messages = chat_history_store.list_by_notebook(notebook_id, limit=limit)
    return [m.to_dict() for m in messages]


@app.delete("/api/v1/notebooks/{notebook_id}/history")
def clear_chat_history(
    request: Request,
    notebook_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Clear all chat history for a notebook. Returns count of deleted messages."""
    audit_payload = {"notebook_id": notebook_id}
    try:
        _require_notebook_access(notebook_id, principal)
        deleted = chat_history_store.clear(notebook_id)
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.CHAT_HISTORY_CLEAR,
            resource_type="chat",
            resource_id="-",
            parent_resource_id=notebook_id,
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload=audit_payload,
        )
        raise
    _record_audit_success(
        request,
        event=AuditEvent.CHAT_HISTORY_CLEAR,
        resource_type="chat",
        resource_id="-",
        parent_resource_id=notebook_id,
        http_status=200,
        payload={**audit_payload, "chat.history_turns": deleted},
    )
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# S-20: Notes CRUD endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/notebooks/{notebook_id}/notes")
def list_notes(
    notebook_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """List all saved notes for a notebook."""
    _require_notebook_access(notebook_id, principal)
    return [n.to_dict() for n in note_store.list_by_notebook(notebook_id)]


@app.post("/api/v1/notebooks/{notebook_id}/notes", status_code=201)
def create_note(
    request: Request,
    notebook_id: str,
    payload: NoteCreateRequest,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Save an AI response as a note."""
    audit_payload = {"notebook_id": notebook_id, "title": payload.title}
    try:
        _require_notebook_access(notebook_id, principal)
        note = note_store.create(
            notebook_id=notebook_id,
            content=payload.content,
            citations=payload.citations or [],
            title=payload.title,
        )
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.NOTE_CREATE,
            resource_type="note",
            resource_id="-",
            parent_resource_id=notebook_id,
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload=audit_payload,
        )
        raise
    _record_audit_success(
        request,
        event=AuditEvent.NOTE_CREATE,
        resource_type="note",
        resource_id=note.id,
        parent_resource_id=notebook_id,
        http_status=201,
        payload={**audit_payload, "note_id": note.id},
    )
    return note.to_dict()


@app.get("/api/v1/notebooks/{notebook_id}/notes/{note_id}")
def get_note(
    notebook_id: str,
    note_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Retrieve a single note."""
    _require_notebook_access(notebook_id, principal)
    note = note_store.get(notebook_id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note.to_dict()


@app.patch("/api/v1/notebooks/{notebook_id}/notes/{note_id}")
def update_note(
    request: Request,
    notebook_id: str,
    note_id: str,
    payload: NotePatchRequest,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Update a note's title and/or content."""
    audit_payload = {
        "notebook_id": notebook_id,
        "note_id": note_id,
        "title": payload.title,
    }
    try:
        _require_notebook_access(notebook_id, principal)
        note = note_store.update(
            notebook_id=notebook_id,
            note_id=note_id,
            title=payload.title,
            content=payload.content,
        )
    except KeyError:
        _record_audit_failure(
            request,
            event=AuditEvent.NOTE_UPDATE,
            resource_type="note",
            resource_id=note_id,
            parent_resource_id=notebook_id,
            http_status=404,
            error_code=_audit_error_code(404),
            payload=audit_payload,
        )
        raise HTTPException(status_code=404, detail="Note not found")
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.NOTE_UPDATE,
            resource_type="note",
            resource_id=note_id,
            parent_resource_id=notebook_id,
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload=audit_payload,
        )
        raise
    _record_audit_success(
        request,
        event=AuditEvent.NOTE_UPDATE,
        resource_type="note",
        resource_id=note.id,
        parent_resource_id=notebook_id,
        http_status=200,
        payload={**audit_payload, "note_id": note.id, "title": note.title},
    )
    return note.to_dict()


@app.delete("/api/v1/notebooks/{notebook_id}/notes/{note_id}", status_code=204)
def delete_note(
    request: Request,
    notebook_id: str,
    note_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Delete a note."""
    audit_payload = {"notebook_id": notebook_id, "note_id": note_id}
    try:
        _require_notebook_access(notebook_id, principal)
        if not note_store.delete(notebook_id, note_id):
            raise HTTPException(status_code=404, detail="Note not found")
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.NOTE_DELETE,
            resource_type="note",
            resource_id=note_id,
            parent_resource_id=notebook_id,
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload=audit_payload,
        )
        raise
    _record_audit_success(
        request,
        event=AuditEvent.NOTE_DELETE,
        resource_type="note",
        resource_id=note_id,
        parent_resource_id=notebook_id,
        http_status=204,
        payload=audit_payload,
    )


# ---------------------------------------------------------------------------
# S-21: Text Studio endpoints
# ---------------------------------------------------------------------------

class StudioGenerateRequest(BaseModel):
    output_type: str          # one of StudioOutputType values
    source_ids: Optional[List[str]] = None  # None = all READY sources in notebook


@app.post("/api/v1/notebooks/{notebook_id}/studio/generate", status_code=201)
async def generate_studio_output(
    request: Request,
    notebook_id: str,
    payload: StudioGenerateRequest,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Generate a structured text output from notebook sources using the local LLM."""
    audit_payload = {"notebook_id": notebook_id}
    try:
        _require_notebook_access(notebook_id, principal)

        # Validate output type
        if payload.output_type not in StudioOutputType.values():
            raise HTTPException(
                status_code=422,
                detail=f"Invalid output_type '{payload.output_type}'. "
                       f"Must be one of: {StudioOutputType.values()}"
            )

        # Resolve source_ids (use all READY sources if not specified)
        source_ids = payload.source_ids
        if not source_ids:
            all_sources = source_registry.list_by_notebook(notebook_id)
            source_ids = [
                s.id for s in all_sources
                if getattr(s, "status", None) in ("ready", "READY")
            ]

        if not source_ids:
            raise HTTPException(
                status_code=422,
                detail="No READY sources available in this notebook for generation."
            )

        # Retrieve context chunks
        try:
            chunks = retriever_engine.retrieve(
                query=payload.output_type,
                top_k=20,
                final_k=20,
                source_ids=source_ids,
                notebook_id=notebook_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Retrieval error: {exc}") from exc

        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="No relevant content found in the specified sources."
            )

        # Build prompt and invoke LLM
        context_blocks = build_context_block(chunks)
        studio_prompt = STUDIO_PROMPTS[payload.output_type].format(
            context_blocks=context_blocks
        )

        try:
            raw_response = invoke_local_llm(
                system_prompt=studio_prompt,
                user_query=f"请生成: {payload.output_type}",
            )
        except LLMUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        # Gateway validation (citations optional for studio outputs)
        try:
            _is_valid, safe_content, citations = AntiHallucinationGateway.validate_and_parse(
                raw_response, chunks
            )
        except Exception:
            # If gateway fails, use raw response with empty citations
            safe_content = raw_response
            citations = []

        # Persist and return
        output = studio_store.create(
            notebook_id=notebook_id,
            output_type=payload.output_type,
            content=safe_content,
            citations=citations,
        )
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.STUDIO_CREATE,
            resource_type="studio",
            resource_id="-",
            parent_resource_id=notebook_id,
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload=audit_payload,
        )
        raise
    _record_audit_success(
        request,
        event=AuditEvent.STUDIO_CREATE,
        resource_type="studio",
        resource_id=output.id,
        parent_resource_id=notebook_id,
        http_status=201,
        payload=audit_payload,
    )
    return output.to_dict()


@app.get("/api/v1/notebooks/{notebook_id}/studio")
def list_studio_outputs(
    notebook_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """List all generated studio outputs for a notebook."""
    _require_notebook_access(notebook_id, principal)
    return [o.to_dict() for o in studio_store.list_by_notebook(notebook_id)]


@app.get("/api/v1/notebooks/{notebook_id}/studio/{output_id}")
def get_studio_output(
    notebook_id: str,
    output_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Get a specific studio output."""
    _require_notebook_access(notebook_id, principal)
    output = studio_store.get(notebook_id, output_id)
    if output is None:
        raise HTTPException(status_code=404, detail="Studio output not found")
    return output.to_dict()


@app.delete("/api/v1/notebooks/{notebook_id}/studio/{output_id}", status_code=204)
def delete_studio_output(
    request: Request,
    notebook_id: str,
    output_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Delete a studio output."""
    audit_payload = {"notebook_id": notebook_id}
    try:
        _require_notebook_access(notebook_id, principal)
        if not studio_store.delete(notebook_id, output_id):
            raise HTTPException(status_code=404, detail="Studio output not found")
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.STUDIO_DELETE,
            resource_type="studio",
            resource_id=output_id,
            parent_resource_id=notebook_id,
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload=audit_payload,
        )
        raise
    _record_audit_success(
        request,
        event=AuditEvent.STUDIO_DELETE,
        resource_type="studio",
        resource_id=output_id,
        parent_resource_id=notebook_id,
        http_status=204,
        payload=audit_payload,
    )


@app.post("/api/v1/notebooks/{notebook_id}/studio/{output_id}/save-as-note", status_code=201)
def save_studio_as_note(
    request: Request,
    notebook_id: str,
    output_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """Save a studio output as a Note (persisted in NoteStore)."""
    audit_payload = {"notebook_id": notebook_id}
    try:
        _require_notebook_access(notebook_id, principal)
        output = studio_store.get(notebook_id, output_id)
        if output is None:
            raise HTTPException(status_code=404, detail="Studio output not found")
        note = note_store.create(
            notebook_id=notebook_id,
            content=output.content,
            citations=output.citations,
            title=output.title,
        )
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.NOTE_CREATE,
            resource_type="note",
            resource_id="-",
            parent_resource_id=notebook_id,
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload=audit_payload,
        )
        raise
    _record_audit_success(
        request,
        event=AuditEvent.NOTE_CREATE,
        resource_type="note",
        resource_id=note.id,
        parent_resource_id=notebook_id,
        http_status=201,
        payload={**audit_payload, "note_id": note.id, "title": note.title},
    )
    return note.to_dict()


# ---------------------------------------------------------------------------
# S-23: Knowledge Graph / Mind Map endpoints
# ---------------------------------------------------------------------------

@app.post("/api/v1/notebooks/{notebook_id}/graph/generate", status_code=201)
def generate_graph(
    request: Request,
    notebook_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """
    Extract entities and relations from all READY sources in a notebook,
    build a knowledge graph + mind-map tree, and persist it.

    Returns the full graph JSON.
    """
    audit_payload = {"notebook_id": notebook_id}
    try:
        _require_notebook_access(notebook_id, principal)

        sources = [
            s for s in source_registry.list_by_notebook(notebook_id)
            if s.status == "ready"
        ]
        if not sources:
            raise HTTPException(status_code=422, detail="No ready sources in notebook")

        source_ids = [s.id for s in sources]
        chunks = retriever_engine.retrieve(
            query="主要概念实体技术术语 key concepts technical terms",
            top_k=50,
            final_k=50,
            source_ids=source_ids,
            hybrid=False,      # pure vector for broad coverage
            expand_query=False,
            mmr_threshold=1.0, # no de-dup — we want max coverage for graph building
        )

        graph = graph_extractor.extract(chunks)
        graph_store.save(notebook_id, graph)
    except HTTPException as exc:
        _record_audit_failure(
            request,
            event=AuditEvent.GRAPH_GENERATE,
            resource_type="graph",
            resource_id=notebook_id,
            parent_resource_id=notebook_id,
            http_status=exc.status_code,
            error_code=_audit_error_code(exc.status_code),
            payload=audit_payload,
        )
        raise
    _record_audit_success(
        request,
        event=AuditEvent.GRAPH_GENERATE,
        resource_type="graph",
        resource_id=notebook_id,
        parent_resource_id=notebook_id,
        http_status=201,
        payload=audit_payload,
    )
    return graph.to_dict()


@app.get("/api/v1/notebooks/{notebook_id}/graph")
def get_graph(
    notebook_id: str,
    principal: Optional[AuthPrincipal] = Depends(get_current_principal),
):
    """
    Return the previously generated knowledge graph for a notebook.
    Returns 404 if graph has not been generated yet.
    """
    _require_notebook_access(notebook_id, principal)

    graph = graph_store.load(notebook_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not yet generated")

    return graph.to_dict()
