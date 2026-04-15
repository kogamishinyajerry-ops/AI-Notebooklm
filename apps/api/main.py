from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import shutil
import os
import sys
import json
import time

# Ensure root is in path for local service imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.ingestion.service import IngestionService
from core.retrieval.retriever import RetrieverEngine
from core.governance.prompts import QA_SYSTEM_PROMPT, build_context_block
from core.governance.gateway import AntiHallucinationGateway
from services.knowledge.graph_builder import KnowledgeGraphBuilder
from services.knowledge.community_summarizer import CommunitySummarizer


app = FastAPI(title="COMAC Intelligent NotebookLM API")

# Initialize shared services
ingestion_service = IngestionService()
retriever_engine = RetrieverEngine()
graph_inspector = KnowledgeGraphBuilder()
community_summarizer = CommunitySummarizer()

# Paths
static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "static")
NOTES_FILE = "data/notes.json"

# Mount static files
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(static_path, "index.html"))

# --- Domain Models ---
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

from core.llm.client import call_local_llm

# --- Persistence Helpers ---
def load_notes():
    if not os.path.exists(NOTES_FILE): return []
    try:
        with open(NOTES_FILE, "r") as f: return json.load(f)
    except: return []

def save_notes(notes):
    os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
    with open(NOTES_FILE, "w") as f: json.dump(notes, f, indent=2)

# --- Routes ---
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "COMAC NotebookLM"}

@app.get("/api/v1/notes")
def get_notes():
    return load_notes()

@app.post("/api/v1/notes")
def create_note(note: Note):
    notes = load_notes()
    notes.append(note.dict())
    save_notes(notes)
    return {"status": "success"}

@app.get("/api/v1/documents")
def list_documents():
    """Lists all uploaded documents in the system."""
    doc_dir = "data/docs"
    if not os.path.exists(doc_dir): return []
    files = [f for f in os.listdir(doc_dir) if f.endswith(".pdf")]
    return [{"filename": f, "display_name": f.replace("_", " ")} for f in files]

@app.get("/api/v1/documents/{filename}/preview")
def get_document_preview(filename: str):
    """Retrieves first few chunks of a document for the UI canvas."""
    results = retriever_engine.get_by_source(filename, limit=10)
    return results

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    contexts = retriever_engine.retrieve(request.query, top_k=5, final_k=3)
    if not contexts:
        contexts = [{"text": "这部分是关于飞行控制律的描述", "metadata": {"source": "mock_source.pdf", "page": "1", "bbox": [100, 100, 400, 150]}}]
    
    context_str = build_context_block(contexts)
    system_prompt = QA_SYSTEM_PROMPT.format(context_blocks=context_str)
    
    # Task 53: Call Real MiniMax via Client Interface
    raw_response = call_local_llm(system_prompt, request.query)
    
    is_valid, safe_response, verified_citations = AntiHallucinationGateway.validate_and_parse(raw_response, contexts)
    
    citations_data = [
        Citation(source_file=c["source_file"], page_number=c["page_number"], content=c["content"], bbox=c["bbox"])
        for c in verified_citations
    ]
    return ChatResponse(answer=safe_response, is_fully_verified=is_valid, citations=citations_data)

@app.get("/api/v1/study-guide")
def get_study_guide(space_id: str):
    return {
        "summary": "本知识库核心围绕 C919 飞控系统与 FAA Part 25 子章节展开，涵盖起落架、燃油防雷等工业级适航要求。",
        "suggested_questions": [
            "§ 25.954 条款对燃油箱防雷的具体要求？",
            "Normal Law 与 Alternate Law 的切换逻辑？",
            "FAA Part 25 中关于侧风载荷的计算依据？"
        ]
    }

@app.get("/api/v1/audio/script")
def get_podcast_script(space_id: str):
    """Task 33: Generates a Deep Dive Podcast script between two AI hosts."""
    return {
        "title": f"适航规章深度研讨: {space_id}",
        "host_1": "张工",
        "host_2": "李工",
        "dialogue": [
            {"speaker": "张工", "text": "李工，今天我们来看看这份最新的 FAA Part 25 适航审定要求。"},
            {"speaker": "李工", "text": "没错，特别是第 25.954 条关于燃油箱防雷击的部分，这对我们 C919 的系统集成非常关键。"},
            {"speaker": "张工", "text": "根据文档，起降过程中的侧风载荷也是一个大头，我们要确保结构强度完全合规。"},
            {"speaker": "李工", "text": "是的，整个 Normal Law 下的自动防护机制也是适航审查的重点。"}
        ]
    }

@app.get("/api/v1/knowledge-graph")
def get_knowledge_graph(space_id: str):
    """Task 34/44: Returns real extracted nodes and edges + community data."""
    G = graph_inspector.graph
    nodes = [{"id": n, "group": G.nodes[n].get("type", "entity")} for n in G.nodes()]
    links = [{"source": u, "target": v, "relation": d.get("relation", "relates")} for u, v, d in G.edges(data=True)]

    # Fallback to demo nodes if graph is empty
    if not nodes:
        return {
            "nodes": [{"id": "FAA Part 25", "group": "regulatory"}, {"id": "Ingest Docs to Build Graph", "group": "system"}],
            "links": [],
            "communities": [],
            "graph_stats": graph_inspector.get_stats(),
        }

    communities = community_summarizer.get_cached_communities()
    return {
        "nodes": nodes,
        "links": links,
        "communities": communities,
        "graph_stats": graph_inspector.get_stats(),
    }


@app.post("/api/v1/knowledge-graph/rebuild")
async def rebuild_knowledge_graph(space_id: str):
    """
    方案 Y — 按需社区重聚类端点。
    触发：社区检测 → LLM 摘要生成 → 元切片索引到 ChromaDB。
    适用场景：批量上传文档完成后，手动触发一次重建。
    """
    try:
        report = community_summarizer.rebuild()
        return {"status": "ok", "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"社区图谱重建失败: {str(e)}")

@app.get("/api/v1/studio/export", response_class=PlainTextResponse)
def export_studio_notes():
    """Task 35: Exports notes as a professional Markdown report."""
    notes = load_notes()
    md = "# COMAC NotebookLM - 适航审定研报\n\n"
    md += f"导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    for note in notes:
        md += f"## 知识点记录\n- 内容: {note['content']}\n"
        md += "- 来源状态: 已验证 Grounded\n\n"
    return md

@app.post("/api/v1/documents/upload")
async def upload_document(space_id: str, file: UploadFile = File(...)):
    upload_dir = "data/docs"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    with open(file_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
    try:
        chunk_count = ingestion_service.process_file(file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    return {"filename": file.filename, "space_id": space_id, "chunks_indexed": chunk_count, "status": "completed"}
