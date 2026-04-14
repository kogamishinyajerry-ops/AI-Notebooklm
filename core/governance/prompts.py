QA_SYSTEM_PROMPT = """你是一个专业的企业知识问答助手（COMAC NotebookLM）。
你的任务是根据提供的参考资料回答问题。

【强制约束】
1. 你必须严格并且仅仅根据提供的<Context>片段进行回答。
2. 你的回答必须在所有的陈述中附带引用来源，格式必须为XML标签形式： <citation src="文件名" page="页码">引用的摘要词句</citation>。
3. 如果参考资料中找不到答案，请直接回答“对不起，当前知识库中没有足够的信息来回答这个问题。”，严禁凭空捏造。
4. 任何时候都不得输出不带 citation 的断言。

【参考资料】
{context_blocks}
"""

def build_context_block(chunks: list[dict]) -> str:
    """Formats retrieved chunks into a prompt-friendly string."""
    blocks = []
    for i, chunk in enumerate(chunks):
        meta = chunk.get("metadata", {})
        src = meta.get("source", "unknown_source")
        page = meta.get("page", "unknown_page")
        text = chunk.get("text", "")
        # Add internal chunk index for easy cross-referencing by the gateway
        blocks.append(f"<Context chunk_index='{i}' src='{src}' page='{page}'>\n{text}\n</Context>")
    return "\n".join(blocks)
