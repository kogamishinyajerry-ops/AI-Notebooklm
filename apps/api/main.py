from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import shutil
import os
import sys
import requests
import json

# Ensure root is in path for local service imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.ingestion.service import IngestionService
from core.retrieval.retriever import RetrieverEngine
from core.governance.prompts import QA_SYSTEM_PROMPT, build_context_block
from core.governance.gateway import AntiHallucinationGateway
from core.storage.space_resolver import get_space_docs_dir, get_space_notes_file, normalize_space_id

app = FastAPI(title="COMAC Intelligent NotebookLM API")

_ingestion_services: Dict[str, IngestionService] = {}
_retriever_engines: Dict[str, RetrieverEngine] = {}

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


class Note(BaseModel):
    id: str
    content: str
    source_refs: List[Dict[str, Any]]
    created_at: float


def get_ingestion_service(space_id: str) -> IngestionService:
    key = normalize_space_id(space_id)
    if key not in _ingestion_services:
        _ingestion_services[key] = IngestionService(space_id=key)
    return _ingestion_services[key]


def get_retriever_engine(space_id: str) -> RetrieverEngine:
    key = normalize_space_id(space_id)
    if key not in _retriever_engines:
        _retriever_engines[key] = RetrieverEngine(space_id=key)
    return _retriever_engines[key]

# Routes
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "COMAC NotebookLM"}


@app.get("/api/v1/notes")
def get_notes(space_id: str):
    return load_notes(space_id)


@app.post("/api/v1/notes")
def create_note(note: Note, space_id: str):
    notes = load_notes(space_id)
    notes.append(note.model_dump())
    save_notes(space_id, notes)
    return {"status": "success"}


@app.get("/api/v1/documents")
def list_documents(space_id: str):
    doc_dir = get_space_docs_dir(space_id)
    if not doc_dir.exists():
        return []
    files = sorted(
        file.name
        for file in doc_dir.iterdir()
        if file.is_file() and file.suffix.lower() == ".pdf"
    )
    return [{"filename": name, "display_name": name.replace("_", " ")} for name in files]


@app.get("/api/v1/documents/{filename}/preview")
def get_document_preview(filename: str, space_id: str):
    safe_filename = sanitize_pdf_filename(filename)
    doc_path = get_space_docs_dir(space_id) / safe_filename
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail="Document not found in this space")
    return get_retriever_engine(space_id).get_by_source(safe_filename, limit=10)

@app.post("/api/v1/spaces")
def create_space(name: str):
    """Creates a new knowledge space (collection in vector db)."""
    return {"space_id": "mock-id-123", "name": name}


def sanitize_pdf_filename(filename: str) -> str:
    normalized = (filename or "").replace("\\", "/")
    safe_name = os.path.basename(normalized).strip()
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")
    return safe_name


def load_notes(space_id: str) -> List[Dict[str, Any]]:
    notes_file = get_space_notes_file(space_id)
    if not notes_file.exists():
        return []
    try:
        with notes_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return []


def save_notes(space_id: str, notes: List[Dict[str, Any]]) -> None:
    notes_file = get_space_notes_file(space_id, for_write=True)
    with notes_file.open("w", encoding="utf-8") as handle:
        json.dump(notes, handle, ensure_ascii=False, indent=2)

def invoke_local_llm(system_prompt: str, user_query: str) -> str:
    """Invokes local vLLM (Qwen-2.5/GLM-4) via OpenAI-compatible API."""
    try:
        resp = requests.post(
            "http://localhost:8000/v1/chat/completions",
            json={
                "model": "qwen-2.5", 
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
    contexts = get_retriever_engine(request.space_id).retrieve(request.query, top_k=5, final_k=3)
    
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

@app.post("/api/v1/documents/upload")
async def upload_document(space_id: str, file: UploadFile = File(...)):
    """Uploads and triggers ingestion for a document."""
    safe_filename = sanitize_pdf_filename(file.filename)
    upload_dir = get_space_docs_dir(space_id, for_write=True)
    file_path = upload_dir / safe_filename
    
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        chunk_count = get_ingestion_service(space_id).process_file(str(file_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    
    return {
        "filename": safe_filename, 
        "space_id": space_id,
        "chunks_indexed": chunk_count,
        "status": "completed"
    }
