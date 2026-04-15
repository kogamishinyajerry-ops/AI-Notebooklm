from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import shutil
import os
import sys
import requests

# Ensure root is in path for local service imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.ingestion.service import IngestionService
from services.ingestion.filenames import safe_upload_path
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

app = FastAPI(title="COMAC Intelligent NotebookLM API")

# Initialize shared services
ingestion_service = IngestionService()
retriever_engine = RetrieverEngine()


@app.on_event("startup")
def recover_ingestion_transactions():
    for space_id in iter_space_ids():
        recover_incomplete_transactions(
            space_id,
            vector_store=ingestion_service.vector_store,
            registry=getattr(ingestion_service, "parameter_registry", None),
        )
        cleanup_committed_transactions(space_id)

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

# Routes
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "COMAC NotebookLM"}

@app.get("/api/v1/health")
def api_health_check():
    return {
        "status": "ok",
        "service": "COMAC NotebookLM",
        "transactions": summarize_transaction_health(),
    }

@app.post("/api/v1/spaces")
def create_space(name: str):
    """Creates a new knowledge space (collection in vector db)."""
    return {"space_id": "mock-id-123", "name": name}

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

@app.post("/api/v1/documents/upload")
async def upload_document(space_id: str, file: UploadFile = File(...)):
    """Uploads and triggers ingestion for a document."""
    upload_dir = "data/docs"
    os.makedirs(upload_dir, exist_ok=True)
    try:
        file_path = safe_upload_path(upload_dir, file.filename, file.content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    transaction = IngestTransaction(space_id=space_id)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        transaction.record_file(file_path)

        chunk_count = ingestion_service.process_file(
            str(file_path),
            space_id=space_id,
            transaction=transaction,
        )
    except Exception as e:
        if transaction.status == "in_progress":
            transaction.rollback(
                vector_store=ingestion_service.vector_store,
                registry=getattr(ingestion_service, "parameter_registry", None),
            )
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    
    return {
        "filename": file_path.name,
        "space_id": space_id,
        "chunks_indexed": chunk_count,
        "status": "completed"
    }
