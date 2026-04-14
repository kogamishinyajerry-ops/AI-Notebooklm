from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="COMAC Intelligent NotebookLM API")

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
    # Constraint C2: Mandatory citations field for traceability
    citations: List[Citation]

# Routes
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "COMAC NotebookLM"}

@app.post("/api/v1/spaces")
def create_space(name: str):
    """Creates a new knowledge space (collection in vector db)."""
    return {"space_id": "mock-id-123", "name": name}

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Core Q&A endpoint. 
    In actual implementation, this triggers the RAG pipeline.
    Response must include XML-compatible citation placeholders in 'answer' 
    and detailed metadata in 'citations'.
    """
    # Mock response illustrating C2 compliance
    mock_answer = "根据资料 <citation src='doc1.pdf' page='5'>...</citation>，企业核心机密等级为..."
    return ChatResponse(
        answer=mock_answer,
        citations=[
            Citation(
                source_file="doc1.pdf",
                page_number=5,
                content="企业核心机密等级为...",
                bbox=[100, 200, 300, 400]
            )
        ]
    )

@app.post("/api/v1/documents/upload")
async def upload_document(space_id: str, file: UploadFile = File(...)):
    """Uploads and triggers ingestion for a document."""
    return {"filename": file.filename, "status": "processing"}
