from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import shutil
import os
import sys
import requests

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
from core.storage.notebook_store import NotebookStore
from core.storage.source_registry import SourceRegistry
from core.storage.note_store import NoteStore
from core.storage.chat_history_store import ChatHistoryStore
from core.storage.studio_store import StudioStore
from core.models.studio_output import StudioOutputType
from core.governance.prompts import STUDIO_PROMPTS
from core.storage.graph_store import GraphStore
from core.knowledge.graph_extractor import GraphExtractor

app = FastAPI(title="COMAC Intelligent NotebookLM API")

# Initialize shared services
ingestion_service = IngestionService()
retriever_engine = RetrieverEngine()
notebook_store = NotebookStore()
source_registry = SourceRegistry()
note_store = NoteStore()
chat_history_store = ChatHistoryStore()
studio_store = StudioStore()
graph_store = GraphStore()
graph_extractor = GraphExtractor()

# Gap-A: inject graph signal into the retriever
retriever_engine.graph_store = graph_store
retriever_engine.graph_extractor = graph_extractor


@app.on_event("startup")
def recover_ingestion_transactions():
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

@app.post("/api/v1/spaces")
def create_space(name: str):
    """Legacy alias for creating a notebook-backed knowledge space."""
    try:
        notebook = notebook_store.create(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"space_id": notebook.id, "name": notebook.name}

@app.post("/api/v1/notebooks", status_code=201)
def create_notebook(request: NotebookCreateRequest):
    try:
        notebook = notebook_store.create(request.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return notebook.to_dict()

@app.get("/api/v1/notebooks")
def list_notebooks():
    return [notebook.to_dict() for notebook in notebook_store.list_all()]

@app.get("/api/v1/notebooks/{notebook_id}")
def get_notebook(notebook_id: str):
    notebook = notebook_store.get(notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return notebook.to_dict()

@app.delete("/api/v1/notebooks/{notebook_id}", status_code=204)
def delete_notebook(notebook_id: str):
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")

    for source in source_registry.list_by_notebook(notebook_id):
        ingestion_service.vector_store.delete(where={"source_id": source.id})

    if not notebook_store.delete(notebook_id):
        raise HTTPException(status_code=404, detail="Notebook not found")

@app.get("/api/v1/notebooks/{notebook_id}/sources")
def list_sources(notebook_id: str):
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return [source.to_dict() for source in source_registry.list_by_notebook(notebook_id)]

@app.get("/api/v1/notebooks/{notebook_id}/sources/{source_id}")
def get_source(notebook_id: str, source_id: str):
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    source = source_registry.get(notebook_id, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source.to_dict()

@app.delete("/api/v1/notebooks/{notebook_id}/sources/{source_id}", status_code=204)
def delete_source(notebook_id: str, source_id: str):
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    source = source_registry.get(notebook_id, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    ingestion_service.vector_store.delete(where={"source_id": source_id})
    Path(source.file_path).unlink(missing_ok=True)
    source_registry.delete(notebook_id, source_id)
    notebook_store.increment_source_count(notebook_id, -1)

class LLMUnavailableError(Exception):
    """Raised when the local vLLM service cannot be reached."""


def invoke_local_llm(system_prompt: str, user_query: str) -> str:
    """
    Invokes local vLLM (Qwen-2.5/GLM-4) via OpenAI-compatible API.

    Raises:
        LLMUnavailableError: If the vLLM service is unreachable or returns
            a non-2xx response, so callers can return HTTP 503.
    """
    vllm_url = os.getenv("VLLM_URL", "http://localhost:8000/v1").rstrip("/")
    model_name = os.getenv("LOCAL_LLM_MODEL", "qwen-2.5")
    try:
        resp = requests.post(
            f"{vllm_url}/chat/completions",
            json={
                "model": model_name,
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
            f"Local LLM service unavailable at {vllm_url}: {exc}"
        ) from exc

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Core Q&A endpoint.
    Triggers RAG retrieval scoped to the notebook's sources, LLM generation,
    and Gateway citation validation.

    Returns HTTP 400 if the notebook does not exist.
    Returns HTTP 503 if the local LLM service is unavailable.
    """
    notebook_id = request.resolved_notebook_id

    # 1. Resolve notebook and its source_ids for retrieval scoping
    source_ids: list[str] | None = None
    if notebook_id:
        notebook = notebook_store.get(notebook_id)
        if notebook is None:
            raise HTTPException(status_code=400, detail=f"Notebook '{notebook_id}' not found")
        sources = source_registry.list_by_notebook(notebook_id)
        source_ids = [s.id for s in sources] if sources else []

    # 2. Retrieve — scoped to this notebook's source_ids when available
    contexts = retriever_engine.retrieve(
        request.query,
        top_k=5,
        final_k=3,
        source_ids=source_ids if source_ids else None,
        notebook_id=notebook_id,
    )

    if not contexts:
        return ChatResponse(
            answer="未在当前知识库中检索到相关内容，请上传相关文档后再试。",
            is_fully_verified=False,
            citations=[],
        )

    # 3. Build Prompt
    context_str = build_context_block(contexts)
    system_prompt = QA_SYSTEM_PROMPT.format(context_blocks=context_str)

    # 4. Generate (LLM) — raise 503 if service unavailable
    try:
        raw_response = invoke_local_llm(system_prompt, request.query)
    except LLMUnavailableError as exc:
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
    if request.save_history and notebook_id:
        try:
            chat_history_store.append(notebook_id, "user", request.query)
            chat_history_store.append(
                notebook_id,
                "assistant",
                safe_response,
                citations=[c.model_dump() for c in citations_data],
                is_fully_verified=is_valid,
            )
        except Exception:
            pass  # history persistence must never break the response

    return ChatResponse(
        answer=safe_response,
        is_fully_verified=is_valid,
        citations=citations_data,
    )

@app.post("/api/v1/notebooks/{notebook_id}/sources/upload")
async def upload_source(notebook_id: str, file: UploadFile = File(...)):
    """Uploads and triggers ingestion for a document."""
    notebook = notebook_store.get(notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail="Notebook not found")

    upload_dir = source_registry.spaces_dir / notebook_id / "docs"
    os.makedirs(upload_dir, exist_ok=True)
    try:
        file_path = safe_upload_path(upload_dir, file.filename, file.content_type)
        validate_pdf_magic(file.file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    except Exception as e:
        try:
            source_registry.update_status(notebook_id, source.id, SourceStatus.FAILED, error_message=str(e))
        except Exception:
            pass
        if transaction.status == "in_progress":
            transaction.rollback(
                vector_store=ingestion_service.vector_store,
                registry=getattr(ingestion_service, "parameter_registry", None),
            )
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    
    return {
        "source": source.to_dict(),
        "filename": source.filename,
        "space_id": notebook_id,
        "chunks_indexed": chunk_count,
        "status": "completed"
    }

@app.post("/api/v1/documents/upload")
async def upload_document(space_id: str, file: UploadFile = File(...)):
    """Legacy upload route, backed by notebook sources."""
    if notebook_store.get(space_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return await upload_source(space_id, file)


# ---------------------------------------------------------------------------
# S-19: PDF Source Viewer endpoints
# ---------------------------------------------------------------------------

def _resolve_source_for_file(notebook_id: str, source_id: str):
    """Helper: resolve and validate notebook + source, returning the Source object."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
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
def serve_source_file(notebook_id: str, source_id: str):
    """
    Stream the raw PDF file for a source.
    Used by the frontend PDF viewer to load the document.
    """
    source = _resolve_source_for_file(notebook_id, source_id)
    file_path = _safe_source_path(source, source_registry.spaces_dir)
    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=source.filename,
    )


@app.get("/api/v1/notebooks/{notebook_id}/sources/{source_id}/pages/{page_number}")
def render_source_page(notebook_id: str, source_id: str, page_number: int):
    """
    Render a single PDF page as a PNG image at 144 DPI (2× scale).
    page_number is 1-indexed.
    Used by the frontend canvas renderer for citation evidence display.
    """
    import fitz  # PyMuPDF — local, C1 compliant

    source = _resolve_source_for_file(notebook_id, source_id)
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
def get_chat_history(notebook_id: str, limit: int = 100):
    """Return the most recent chat messages for a notebook."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    messages = chat_history_store.list_by_notebook(notebook_id, limit=limit)
    return [m.to_dict() for m in messages]


@app.delete("/api/v1/notebooks/{notebook_id}/history")
def clear_chat_history(notebook_id: str):
    """Clear all chat history for a notebook. Returns count of deleted messages."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    deleted = chat_history_store.clear(notebook_id)
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# S-20: Notes CRUD endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/notebooks/{notebook_id}/notes")
def list_notes(notebook_id: str):
    """List all saved notes for a notebook."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return [n.to_dict() for n in note_store.list_by_notebook(notebook_id)]


@app.post("/api/v1/notebooks/{notebook_id}/notes", status_code=201)
def create_note(notebook_id: str, request: NoteCreateRequest):
    """Save an AI response as a note."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    note = note_store.create(
        notebook_id=notebook_id,
        content=request.content,
        citations=request.citations or [],
        title=request.title,
    )
    return note.to_dict()


@app.get("/api/v1/notebooks/{notebook_id}/notes/{note_id}")
def get_note(notebook_id: str, note_id: str):
    """Retrieve a single note."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    note = note_store.get(notebook_id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note.to_dict()


@app.patch("/api/v1/notebooks/{notebook_id}/notes/{note_id}")
def update_note(notebook_id: str, note_id: str, request: NotePatchRequest):
    """Update a note's title and/or content."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    try:
        note = note_store.update(
            notebook_id=notebook_id,
            note_id=note_id,
            title=request.title,
            content=request.content,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Note not found")
    return note.to_dict()


@app.delete("/api/v1/notebooks/{notebook_id}/notes/{note_id}", status_code=204)
def delete_note(notebook_id: str, note_id: str):
    """Delete a note."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    if not note_store.delete(notebook_id, note_id):
        raise HTTPException(status_code=404, detail="Note not found")


# ---------------------------------------------------------------------------
# S-21: Text Studio endpoints
# ---------------------------------------------------------------------------

class StudioGenerateRequest(BaseModel):
    output_type: str          # one of StudioOutputType values
    source_ids: Optional[List[str]] = None  # None = all READY sources in notebook


@app.post("/api/v1/notebooks/{notebook_id}/studio/generate", status_code=201)
async def generate_studio_output(notebook_id: str, request: StudioGenerateRequest):
    """Generate a structured text output from notebook sources using the local LLM."""
    notebook = notebook_store.get(notebook_id)
    if notebook is None:
        raise HTTPException(status_code=404, detail="Notebook not found")

    # Validate output type
    if request.output_type not in StudioOutputType.values():
        raise HTTPException(
            status_code=422,
            detail=f"Invalid output_type '{request.output_type}'. "
                   f"Must be one of: {StudioOutputType.values()}"
        )

    # Resolve source_ids (use all READY sources if not specified)
    source_ids = request.source_ids
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
            query=request.output_type,
            top_k=20,
            final_k=20,
            source_ids=source_ids,
            notebook_id=notebook_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Retrieval error: {exc}")

    if not chunks:
        raise HTTPException(
            status_code=422,
            detail="No relevant content found in the specified sources."
        )

    # Build prompt and invoke LLM
    context_blocks = build_context_block(chunks)
    studio_prompt = STUDIO_PROMPTS[request.output_type].format(
        context_blocks=context_blocks
    )

    try:
        raw_response = invoke_local_llm(
            system_prompt=studio_prompt,
            user_query=f"请生成: {request.output_type}",
        )
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

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
        output_type=request.output_type,
        content=safe_content,
        citations=citations,
    )
    return output.to_dict()


@app.get("/api/v1/notebooks/{notebook_id}/studio")
def list_studio_outputs(notebook_id: str):
    """List all generated studio outputs for a notebook."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return [o.to_dict() for o in studio_store.list_by_notebook(notebook_id)]


@app.get("/api/v1/notebooks/{notebook_id}/studio/{output_id}")
def get_studio_output(notebook_id: str, output_id: str):
    """Get a specific studio output."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    output = studio_store.get(notebook_id, output_id)
    if output is None:
        raise HTTPException(status_code=404, detail="Studio output not found")
    return output.to_dict()


@app.delete("/api/v1/notebooks/{notebook_id}/studio/{output_id}", status_code=204)
def delete_studio_output(notebook_id: str, output_id: str):
    """Delete a studio output."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    if not studio_store.delete(notebook_id, output_id):
        raise HTTPException(status_code=404, detail="Studio output not found")


@app.post("/api/v1/notebooks/{notebook_id}/studio/{output_id}/save-as-note", status_code=201)
def save_studio_as_note(notebook_id: str, output_id: str):
    """Save a studio output as a Note (persisted in NoteStore)."""
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")
    output = studio_store.get(notebook_id, output_id)
    if output is None:
        raise HTTPException(status_code=404, detail="Studio output not found")
    note = note_store.create(
        notebook_id=notebook_id,
        content=output.content,
        citations=output.citations,
        title=output.title,
    )
    return note.to_dict()


# ---------------------------------------------------------------------------
# S-23: Knowledge Graph / Mind Map endpoints
# ---------------------------------------------------------------------------

@app.post("/api/v1/notebooks/{notebook_id}/graph/generate", status_code=201)
def generate_graph(notebook_id: str):
    """
    Extract entities and relations from all READY sources in a notebook,
    build a knowledge graph + mind-map tree, and persist it.

    Returns the full graph JSON.
    """
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")

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
    return graph.to_dict()


@app.get("/api/v1/notebooks/{notebook_id}/graph")
def get_graph(notebook_id: str):
    """
    Return the previously generated knowledge graph for a notebook.
    Returns 404 if graph has not been generated yet.
    """
    if notebook_store.get(notebook_id) is None:
        raise HTTPException(status_code=404, detail="Notebook not found")

    graph = graph_store.load(notebook_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not yet generated")

    return graph.to_dict()
