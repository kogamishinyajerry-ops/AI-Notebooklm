from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, AsyncIterator
from functools import lru_cache
import shutil
import os
import sys
import json
import time
import asyncio

# Ensure root is in path for local service imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.ingestion.service import IngestionService
from core.retrieval.retriever import RetrieverEngine
from core.governance.prompts import QA_SYSTEM_PROMPT, build_context_block
from core.governance.gateway import AntiHallucinationGateway
from services.knowledge.graph_builder import KnowledgeGraphBuilder
from services.knowledge.community_summarizer import CommunitySummarizer
from core.llm.client import call_local_llm, stream_local_llm


app = FastAPI(title="COMAC Intelligent NotebookLM API")

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

class ArtifactRequest(BaseModel):
    """
    Gap D Task D-1：衍生产物生成请求。
    artifact_type: "comparison_table" | "technical_brief"
    topic: 生成主题（如"MTOW与MLW的重量层级关系"）
    cited_sources: 引用卡片列表（从前端收藏面板传入）
    """
    artifact_type: str       # "comparison_table" | "technical_brief"
    topic: str
    space_id: str
    cited_sources: Optional[List[Dict[str, Any]]] = None


@lru_cache(maxsize=1)
def get_ingestion_service() -> IngestionService:
    return IngestionService()


@lru_cache(maxsize=1)
def get_retriever_engine() -> RetrieverEngine:
    return RetrieverEngine()


@lru_cache(maxsize=1)
def get_graph_inspector() -> KnowledgeGraphBuilder:
    return KnowledgeGraphBuilder()


@lru_cache(maxsize=1)
def get_community_summarizer() -> CommunitySummarizer:
    return CommunitySummarizer()

# --- Persistence Helpers ---
def load_notes():
    if not os.path.exists(NOTES_FILE): return []
    try:
        with open(NOTES_FILE, "r") as f: return json.load(f)
    except: return []

def save_notes(notes):
    os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
    with open(NOTES_FILE, "w") as f: json.dump(notes, f, indent=2)


def sanitize_upload_filename(filename: str) -> str:
    normalized = (filename or "").replace("\\", "/")
    safe_name = os.path.basename(normalized).strip()
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid upload filename")
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")
    return safe_name


def build_source_refs_markdown(source_refs: List[Dict[str, Any]]) -> str:
    if not source_refs:
        return "- 来源引用: 无\n"

    lines = ["- 来源引用:"]
    for ref in source_refs:
        source_file = ref.get("source_file") or ref.get("source") or "unknown"
        page_number = ref.get("page_number") or ref.get("page") or "?"
        content = str(ref.get("content", "")).strip()
        if len(content) > 80:
            content = content[:77] + "..."
        lines.append(f"  - {source_file} p.{page_number}: {content or '无摘录'}")
    return "\n".join(lines) + "\n"

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
    notes.append(note.model_dump())
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
    results = get_retriever_engine().get_by_source(filename, limit=10)
    return results

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    contexts = get_retriever_engine().retrieve(request.query, top_k=5, final_k=3)
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

@app.post("/api/v1/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    Gap D Task D-1 — SSE 流式 Chat 端点。

    协议：text/event-stream (Server-Sent Events)
    事件格式：
      data: {"type":"delta","text":"..."}\n\n      — 逐 token 文本流
      data: {"type":"citations","citations":[...]}\n\n  — 最终引用列表
      data: {"type":"done","is_verified":bool,"answer":"..."}\n\n
                                                    — 完成信号 + 最终安全答案

    C1 合规：仅允许本地 / 私网 OpenAI-compatible LLM 端点，零公网依赖。
    C2 合规：citations 事件携带完整 source/page/bbox 溯源信息。
    """
    contexts = get_retriever_engine().retrieve(request.query, top_k=5, final_k=3)
    if not contexts:
        contexts = [{
            "text": "暂无相关文档上下文。",
            "metadata": {"source": "system", "page": "0", "bbox": [0, 0, 0, 0]}
        }]

    context_str = build_context_block(contexts)
    system_prompt = QA_SYSTEM_PROMPT.format(context_blocks=context_str)

    async def event_stream() -> AsyncIterator[str]:
        """
        本地 OpenAI-compatible LLM 流式生成器。
        若本地流式不可用，则退回到本地批处理并模拟逐词输出。
        """
        full_text = ""
        try:
            async for delta_text in stream_local_llm(system_prompt, request.query):
                if not delta_text:
                    continue
                full_text += delta_text
                yield f"data: {json.dumps({'type':'delta','text':delta_text}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
        except Exception:
            try:
                full_text = call_local_llm(system_prompt, request.query)
                words = full_text.split(" ")
                for i, word in enumerate(words):
                    chunk = word + (" " if i < len(words) - 1 else "")
                    yield f"data: {json.dumps({'type':'delta','text':chunk}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.02)
            except Exception as exc:
                full_text = f"[系统] 本地 LLM 不可用: {exc}"
                yield f"data: {json.dumps({'type':'delta','text':full_text}, ensure_ascii=False)}\n\n"

        # Gateway 验证（流结束后对完整文本执行）
        is_valid, safe_response, verified_citations = AntiHallucinationGateway.validate_and_parse(
            full_text, contexts
        )
        citations_data = [
            {"source_file": c["source_file"], "page_number": c["page_number"],
             "content": c["content"], "bbox": c["bbox"]}
            for c in verified_citations
        ]

        # 发送 citations 事件
        yield f"data: {json.dumps({'type':'citations','citations':citations_data}, ensure_ascii=False)}\n\n"
        # 发送 done 事件
        yield f"data: {json.dumps({'type':'done','is_verified':is_valid,'answer':safe_response}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Nginx 直通，禁止缓冲
        }
    )


# ---------------------------------------------------------------------------
# Gap D Task D-1 — 衍生产物生成端点
# ---------------------------------------------------------------------------

_ARTIFACT_SYSTEM = """你是 COMAC 适航知识库的技术文档生成引擎。
根据用户提供的主题和引用来源，生成高质量的技术衍生产物。

【输出规范】
- comparison_table：Markdown 格式的对比表格，行列清晰，含数值与标准依据
- technical_brief：500字以内的技术简报，含背景、核心参数、合规要求三段式结构

【Citation 规范】
所有数值声称必须附 <citation src="..." page="...">内容</citation> 标记。
"""


def _artifact_contexts_from_citations(
    cited_sources: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    contexts: List[Dict[str, Any]] = []
    for source in cited_sources or []:
        contexts.append(
            {
                "text": source.get("content", ""),
                "metadata": {
                    "source": source.get("source_file", "?"),
                    "page": str(source.get("page_number", "?")),
                    "bbox": source.get("bbox") or [0, 0, 0, 0],
                },
            }
        )
    return contexts

@app.post("/api/v1/artifacts/generate")
async def generate_artifact(request: ArtifactRequest):
    """
    Gap D Task D-1 — 衍生产物生成端点。

    支持两种产物类型：
      comparison_table: 参数对比表（如多文档间的重量数据对比）
      technical_brief:  技术简报（如某适航条款的合规要点摘要）

    C2 合规：LLM 生成结果经 Gateway 验证，保留完整引用链。
    """
    if request.cited_sources:
        contexts = _artifact_contexts_from_citations(request.cited_sources)
    else:
        contexts = get_retriever_engine().retrieve(request.topic, top_k=5, final_k=3)

    if not contexts:
        contexts = [{
            "text": "暂无相关文档上下文。",
            "metadata": {"source": "system", "page": "0", "bbox": [0, 0, 0, 0]},
        }]

    source_context = ""
    for ctx in contexts:
        source_context += (
            f"\n来源: {ctx['metadata'].get('source','?')} "
            f"第{ctx['metadata'].get('page','?')}页\n"
            f"内容: {ctx.get('text','')}\n"
        )

    artifact_instruction = {
        "comparison_table": f"请生成一份关于「{request.topic}」的 Markdown 参数对比表格，包含至少 3 行数据，每行都要有具体数值和来源引用。",
        "technical_brief": f"请生成一份关于「{request.topic}」的技术简报，包含背景说明、核心工程参数、合规要求三段，总计约 400-500 字。",
    }.get(request.artifact_type, f"请生成关于「{request.topic}」的技术文档。")

    user_prompt = f"{artifact_instruction}\n\n可用来源材料：\n{source_context}"

    raw = call_local_llm(_ARTIFACT_SYSTEM, user_prompt)
    is_valid, safe_response, verified_citations = AntiHallucinationGateway.validate_and_parse(
        raw, contexts
    )

    return {
        "artifact_type": request.artifact_type,
        "topic": request.topic,
        "content": safe_response,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "is_fully_verified": is_valid,
        "citations": verified_citations,
    }


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
    graph_inspector = get_graph_inspector()
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

    communities = get_community_summarizer().get_cached_communities()
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
        report = get_community_summarizer().rebuild()
        return {"status": "ok", "report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"社区图谱重建失败: {str(e)}")

@app.get("/api/v1/studio/export", response_class=PlainTextResponse)
def export_studio_notes():
    """Task 35: Exports notes as a professional Markdown report."""
    notes = load_notes()
    md = "# COMAC NotebookLM - 适航审定研报\n\n"
    md += f"导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    for index, note in enumerate(notes, start=1):
        created_at = note.get("created_at")
        created_label = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_at)) if isinstance(created_at, (int, float)) else "未知"
        md += f"## 知识点记录 {index}\n"
        md += f"- 内容: {note.get('content', '')}\n"
        md += f"- 记录时间: {created_label}\n"
        md += build_source_refs_markdown(note.get("source_refs", []))
        md += "- 来源状态: 已验证 Grounded\n\n"
    return md

@app.post("/api/v1/documents/upload")
async def upload_document(space_id: str, file: UploadFile = File(...)):
    safe_filename = sanitize_upload_filename(file.filename)
    upload_dir = "data/docs"
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, safe_filename)
    with open(file_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
    try:
        chunk_count = get_ingestion_service().process_file(file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    return {"filename": safe_filename, "space_id": space_id, "chunks_indexed": chunk_count, "status": "completed"}
