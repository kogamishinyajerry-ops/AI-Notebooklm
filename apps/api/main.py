from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

app = FastAPI(title="COMAC Intelligent NotebookLM API")

# Initialize shared services
ingestion_service = IngestionService()
retriever_engine = RetrieverEngine()
notebook_store = NotebookStore()
source_registry = SourceRegistry()


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
    space_id: str
    history: Optional[List[dict]] = None

class ChatResponse(BaseModel):
    answer: str
    is_fully_verified: bool
    citations: List[Citation]

class NotebookCreateRequest(BaseModel):
    name: str

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

def invoke_local_llm(system_prompt: str, user_query: str) -> str:
    """Invokes local vLLM (Qwen-2.5/GLM-4) via OpenAI-compatible API."""
    vllm_url = os.getenv("VLLM_URL", "http://localhost:8000/v1").rstrip("/")
    model_name = os.getenv("LOCAL_LLM_MODEL", "qwen-2.5")
    try:
        resp = requests.post(
            f"{vllm_url}/chat/completions",
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ]
            },
            timeout=5
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        # Mock LLM generation logic if vLLM is offline
        return "根据检索到的数据，<citation src='mock_source.pdf' page='1'>这部分是关于飞行控制律的描述</citation>。另外，还有一个幻觉：<citation src='non_existent.pdf' page='99'>错误的参数配置</citation>。"

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Core Q&A endpoint. 
    Triggers RAG retrieval, LLM Prompting, and Gateway strict parsing.
    """
    # 1. Retrieve
    contexts = retriever_engine.retrieve(request.query, top_k=5, final_k=3)
    
    if not contexts:
        contexts = [{"text": "这部分是关于飞行控制律的描述", "metadata": {"source": "mock_source.pdf", "page": "1", "bbox": [100, 100, 400, 150]}}]
        
    # 2. Build Prompt
    context_str = build_context_block(contexts)
    system_prompt = QA_SYSTEM_PROMPT.format(context_blocks=context_str)
    
    # 3. Generate (LLM)
    raw_response = invoke_local_llm(system_prompt, request.query)
    
    # 4. Anti-Hallucination Gate
    is_valid, safe_response, verified_citations = AntiHallucinationGateway.validate_and_parse(raw_response, contexts)
    
    citations_data = [
        Citation(
            source_file=c["source_file"],
            page_number=c["page_number"],
            content=c["content"],
            bbox=c["bbox"]
        ) for c in verified_citations
    ]
    
    return ChatResponse(
        answer=safe_response,
        is_fully_verified=is_valid,
        citations=citations_data
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
