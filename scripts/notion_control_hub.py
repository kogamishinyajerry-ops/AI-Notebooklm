#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib import error, request


NOTION_VERSION = "2025-09-03"
ROOT_TITLE = "AI ControlLogicMaster 控制中枢"
STATE_FILE = Path(".planning/notion_hub.json")


class NotionError(RuntimeError):
    pass


def chunk_text(text: str, size: int = 1800) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= size:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, size)
        if split_at == -1:
            split_at = remaining.rfind(" ", 0, size)
        if split_at == -1:
            split_at = size
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return [chunk for chunk in chunks if chunk]


def rich_text(text: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": {"content": chunk},
        }
        for chunk in chunk_text(text)
    ]


def title_property(text: str) -> dict[str, Any]:
    return {"title": rich_text(text)}


def rich_text_property(text: str) -> dict[str, Any]:
    return {"rich_text": rich_text(text)}


def select_property(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    return {"select": {"name": text}}


def date_property(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    return {"date": {"start": text}}


def number_property(value: int | float | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"number": value}


def compact_props(props: dict[str, dict[str, Any] | None]) -> dict[str, dict[str, Any]]:
    return {key: value for key, value in props.items() if value is not None}


def paragraph_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": rich_text(text)},
    }


def heading_block(level: int, text: str) -> dict[str, Any]:
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": rich_text(text)},
    }


def bulleted_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich_text(text)},
    }


def numbered_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": rich_text(text)},
    }


def callout_block(text: str, emoji: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": rich_text(text),
            "icon": {"type": "emoji", "emoji": emoji},
            "color": "gray_background",
        },
    }


def code_block(text: str, language: str = "plain text") -> dict[str, Any]:
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": rich_text(text),
            "language": language,
        },
    }


def divider_block() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


class NotionClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(
            f"https://api.notion.com{path}",
            method=method,
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Notion-Version": NOTION_VERSION,
            },
        )
        try:
            with request.urlopen(req) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"raw": body}
            message = parsed.get("message") or parsed.get("raw") or str(exc)
            raise NotionError(f"{method} {path} failed ({exc.code}): {message}") from exc

    def create_page(
        self,
        parent: dict[str, Any],
        title: str,
        *,
        icon_emoji: str | None = None,
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "parent": parent,
            "properties": {"title": title_property(title)},
        }
        if children:
            payload["children"] = children
        if icon_emoji:
            payload["icon"] = {"type": "emoji", "emoji": icon_emoji}
        return self._request("POST", "/v1/pages", payload)

    def create_data_source_page(
        self,
        data_source_id: str,
        properties: dict[str, Any],
        *,
        icon_emoji: str | None = None,
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "parent": {"type": "data_source_id", "data_source_id": data_source_id},
            "properties": properties,
        }
        if children:
            payload["children"] = children
        if icon_emoji:
            payload["icon"] = {"type": "emoji", "emoji": icon_emoji}
        return self._request("POST", "/v1/pages", payload)

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        payload = {"properties": properties}
        return self._request("PATCH", f"/v1/pages/{page_id}", payload)

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/pages/{page_id}")

    def append_children(self, block_id: str, children: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request("PATCH", f"/v1/blocks/{block_id}/children", {"children": children})

    def search(self, query: str | None = None, page_size: int = 100) -> dict[str, Any]:
        payload: dict[str, Any] = {"page_size": page_size}
        if query:
            payload["query"] = query
        return self._request("POST", "/v1/search", payload)

    def list_block_children(self, block_id: str) -> list[dict[str, Any]]:
        data = self._request("GET", f"/v1/blocks/{block_id}/children?page_size=100")
        return data.get("results", [])

    def retrieve_database(self, database_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/databases/{database_id}")

    def create_database(
        self,
        parent: dict[str, Any],
        title: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "parent": parent,
            "title": rich_text(title),
            "initial_data_source": {"properties": properties},
        }
        return self._request("POST", "/v1/databases", payload)

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/data_sources/{data_source_id}")

    def update_data_source(self, data_source_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/v1/data_sources/{data_source_id}", {"properties": properties})

    def query_data_source(self, data_source_id: str, payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        data = self._request("POST", f"/v1/data_sources/{data_source_id}/query", payload or {})
        return data.get("results", [])


@dataclass
class BootstrapContext:
    project_name: str
    system_codename: str
    repo_path: str
    current_milestone: str
    current_phase: str
    project_state: str
    next_action: str
    must_read: str
    do_not_do: str
    active_work_item: str
    work_item_goal: str
    work_item_expected_output: str
    snapshot_summary: list[str]
    today: str


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\n(.*?)(?=^##\s+|\Z)", re.M | re.S)
    match = pattern.search(text)
    if not match:
        raise RuntimeError(f"Missing section: {heading}")
    return match.group(1).strip()


def extract_bullets(section: str) -> list[str]:
    return [line[2:].strip() for line in section.splitlines() if line.startswith("- ")]


def extract_first_nonempty_paragraph(section: str) -> str:
    for block in section.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("- ") or block.startswith("```") or block.startswith("|"):
            continue
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if lines:
            return " ".join(lines)
    return ""


def strip_repo_prefix(path: str, repo_root: Path) -> str:
    repo_text = str(repo_root)
    if path.startswith(repo_text + "/"):
        return path[len(repo_text) + 1 :]
    return path


def extract_markdown_paths(section: str, repo_root: Path, limit: int | None = None) -> list[str]:
    paths = [strip_repo_prefix(match, repo_root) for match in re.findall(r"\]\(([^)]+)\)", section)]
    if limit is not None:
        paths = paths[:limit]
    return paths


def build_context(repo_root: Path) -> BootstrapContext:
    board = read_file(repo_root / "docs/MILESTONE_BOARD.md")
    request_input = read_file(repo_root / "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST_INPUT.md")

    task_section = extract_section(request_input, "5. Task")
    prohibitions_section = extract_section(request_input, "7. Absolute Prohibitions")
    required_reads_section = extract_section(request_input, "4. Required First Reads")
    headline_section = extract_section(board, "Current Headline")
    next_section = extract_section(board, "Next Three Milestones")

    next_action = extract_first_nonempty_paragraph(task_section)
    must_read_paths = extract_markdown_paths(required_reads_section, repo_root, limit=6)
    must_read = "; ".join(must_read_paths)
    prohibitions = extract_bullets(prohibitions_section)
    do_not_do = "; ".join(prohibitions)

    snapshot_summary = [
        "Formal baseline populated and post-validated.",
        "Current reflected manual state is accepted_for_review.",
        "freeze-readiness still fails only because docs/checklist remain incomplete.",
        "Final freeze signoff has not started and freeze-complete is not declared.",
        extract_first_nonempty_paragraph(headline_section),
        extract_first_nonempty_paragraph(next_section),
    ]

    return BootstrapContext(
        project_name="AI ControlLogicMaster",
        system_codename="AeroProp Logic Harness (APLH)",
        repo_path=str(repo_root),
        current_milestone="Final Freeze Signoff Checklist Completion Request Package",
        current_phase="APLH-PostPhase7-Final-Freeze-Signoff-Checklist-Completion-Request-Package",
        project_state="Active",
        next_action=next_action,
        must_read=must_read,
        do_not_do=do_not_do,
        active_work_item="Draft final freeze signoff checklist completion request package",
        work_item_goal=next_action,
        work_item_expected_output=(
            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST.md; "
            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST_REVIEW_INPUT.md"
        ),
        snapshot_summary=snapshot_summary,
        today=date.today().isoformat(),
    )


def select_schema(options: list[tuple[str, str]]) -> dict[str, Any]:
    return {"select": {"options": [{"name": name, "color": color} for name, color in options]}}


def database_data_source_id(created: dict[str, Any]) -> str:
    data_sources = created.get("data_sources") or []
    if data_sources:
        return data_sources[0]["id"]
    if "initial_data_source" in created and created["initial_data_source"]:
        return created["initial_data_source"]["id"]
    raise NotionError("Create database response did not include a data source id.")


def search_page_by_title(client: NotionClient, title: str, parent_page_id: str | None) -> dict[str, Any] | None:
    results = client.search(query=title, page_size=50).get("results", [])
    for item in results:
        if item.get("object") != "page":
            continue
        props = item.get("properties", {})
        title_prop = props.get("title") or next(
            (value for value in props.values() if isinstance(value, dict) and value.get("type") == "title"),
            None,
        )
        page_title = "".join(piece.get("plain_text", "") for piece in (title_prop or {}).get("title", []))
        if page_title != title:
            continue
        parent = item.get("parent", {})
        if not parent_page_id:
            return item
        if parent_page_id and parent.get("type") == "page_id" and parent.get("page_id") == parent_page_id:
            return item
    return None


def child_title_maps(client: NotionClient, page_id: str) -> tuple[dict[str, str], dict[str, str]]:
    child_pages: dict[str, str] = {}
    child_databases: dict[str, str] = {}
    for block in client.list_block_children(page_id):
        btype = block.get("type")
        payload = block.get(btype, {}) if isinstance(block.get(btype), dict) else {}
        if btype == "child_page":
            child_pages[payload.get("title", "")] = block["id"]
        elif btype == "child_database":
            child_databases[payload.get("title", "")] = block["id"]
    return child_pages, child_databases


def resolve_data_source_id(client: NotionClient, title: str, database_id: str) -> str:
    try:
        database = client.retrieve_database(database_id)
        for data_source in database.get("data_sources") or []:
            if data_source.get("name") == title:
                return data_source["id"]
        data_sources = database.get("data_sources") or []
        if len(data_sources) == 1:
            return data_sources[0]["id"]
    except NotionError:
        pass

    results = client.search(query=title, page_size=50).get("results", [])
    for item in results:
        if item.get("object") != "data_source":
            continue
        ds_title = "".join(piece.get("plain_text", "") for piece in item.get("title", []))
        parent = item.get("parent", {})
        if ds_title == title and parent.get("type") == "database_id" and parent.get("database_id") == database_id:
            return item["id"]
    raise NotionError(f"Could not resolve data source id for database {database_id} ({title}).")


def sync_schema(client: NotionClient, data_source_id: str, schema: dict[str, Any]) -> None:
    current = client.retrieve_data_source(data_source_id)
    current_properties = current.get("properties", {})
    current_title_name = next(
        (name for name, meta in current_properties.items() if meta.get("type") == "title"),
        None,
    )
    desired_title_name = next((name for name, meta in schema.items() if "title" in meta), None)

    updates: dict[str, Any] = {}
    if current_title_name and desired_title_name and current_title_name != desired_title_name:
        updates[current_title_name] = {"name": desired_title_name}

    for name, definition in schema.items():
        if "title" in definition:
            continue
        updates[name] = definition

    if updates:
        client.update_data_source(data_source_id, updates)


def row_title(row: dict[str, Any]) -> str:
    props = row.get("properties", {})
    title_prop = next(
        (value for value in props.values() if isinstance(value, dict) and value.get("type") == "title"),
        None,
    )
    return "".join(piece.get("plain_text", "") for piece in (title_prop or {}).get("title", []))


def rows_by_title(client: NotionClient, data_source_id: str) -> dict[str, dict[str, Any]]:
    return {row_title(row): row for row in client.query_data_source(data_source_id)}


def base_database_specs() -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        "projects": ("Projects", projects_schema()),
        "phases": ("Phases", phases_schema()),
        "work_items": ("Work Items", work_items_schema()),
        "context_packs": ("Context Packs", context_packs_schema()),
        "reviews": ("Reviews & Decisions", reviews_schema()),
        "session_briefs": ("Session Briefs", session_briefs_schema()),
        "artifact_index": ("Artifact Index", artifact_index_schema()),
    }


def root_page_url(page_id: str) -> str:
    return f"https://www.notion.so/{page_id.replace('-', '')}"


def recover_root_page(client: NotionClient, state: dict[str, Any]) -> dict[str, Any]:
    cached_root_page_id = state.get("root_page_id")
    if cached_root_page_id:
        try:
            client.list_block_children(cached_root_page_id)
            return {"id": cached_root_page_id, "url": state.get("root_page_url") or root_page_url(cached_root_page_id)}
        except NotionError:
            pass

    parent_page_id = state.get("root_meta", {}).get("parent_page_id")
    page = search_page_by_title(client, ROOT_TITLE, parent_page_id) or search_page_by_title(client, ROOT_TITLE, None)
    if not page:
        raise NotionError(
            "Could not rediscover the Notion control hub root page. If you moved it, make sure the new parent is still shared with the integration."
        )
    return {"id": page["id"], "url": page.get("url") or root_page_url(page["id"])}


def refresh_state_from_notion(client: NotionClient, repo_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    context = build_context(repo_root)
    root_page = recover_root_page(client, state)
    state["root_page_id"] = root_page["id"]
    state["root_page_url"] = root_page["url"]

    child_pages, child_databases = child_title_maps(client, root_page["id"])

    supporting_pages = state.setdefault("supporting_pages", {})
    if "How To Use This Hub" in child_pages:
        page_id = child_pages["How To Use This Hub"]
        supporting_pages["how_to_use"] = {"page_id": page_id, "url": root_page_url(page_id)}

    databases = state.setdefault("databases", {})
    for key, (title, _) in base_database_specs().items():
        database_id = child_databases.get(title) or databases.get(key, {}).get("database_id")
        if not database_id:
            raise NotionError(f"Could not find required child database '{title}' under the control hub root page.")
        databases[key] = {
            "title": title,
            "database_id": database_id,
            "database_url": root_page_url(database_id),
            "data_source_id": resolve_data_source_id(client, title, database_id),
        }

    records = state.setdefault("records", {})
    record_specs = {
        "project": ("projects", context.project_name),
        "active_work_item": ("work_items", context.active_work_item),
        "current_operator_brief": ("session_briefs", "Current Operator Brief"),
    }
    for key, (database_key, title) in record_specs.items():
        row = rows_by_title(client, databases[database_key]["data_source_id"]).get(title)
        if row:
            records[key] = {"page_id": row["id"], "url": row.get("url") or root_page_url(row["id"])}

    gsd_titles = {
        "gsd_phases": "GSD Phases",
        "gsd_plans": "GSD Plans",
        "review_gates": "Review Gates",
        "automation_runs": "Automation Runs",
    }
    if any(title in child_databases for title in gsd_titles.values()):
        state.setdefault("gsd", {})
        gsd_databases = state["gsd"].setdefault("databases", {})
        for key, title in gsd_titles.items():
            database_id = child_databases.get(title)
            if not database_id:
                continue
            gsd_databases[key] = {
                "title": title,
                "database_id": database_id,
                "database_url": root_page_url(database_id),
                "data_source_id": resolve_data_source_id(client, title, database_id),
            }

    if "GSD Autopilot Playbook" in child_pages:
        page_id = child_pages["GSD Autopilot Playbook"]
        supporting_pages["gsd_playbook"] = {"page_id": page_id, "url": root_page_url(page_id)}

    return state


def root_page_blocks(context: BootstrapContext) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        callout_block(
            "这个页面借鉴 AI-Harness 控制塔思路，把 Notion 固定为流程控制面，把仓库继续当作代码与证据真相源。",
            "🧭",
        ),
        heading_block(2, "Start Here"),
        numbered_block("先看 Session Briefs 里的 Current Operator Brief，确认当前阶段、下一步和禁止事项。"),
        numbered_block("再看 Work Items 里唯一 Active 项，只围绕当前交付物执行。"),
        numbered_block("需要补背景时，再进入 Context Packs 和 Artifact Index，不再手工复制长提示词。"),
        divider_block(),
        heading_block(2, "Current Snapshot"),
    ]
    for item in context.snapshot_summary:
        blocks.append(bulleted_block(item))
    blocks.extend(
        [
            divider_block(),
            heading_block(2, "Boundary"),
            bulleted_block("Notion 负责 Control Plane、进度面板、当前 brief 与证据索引。"),
            bulleted_block("仓库负责代码、文档、审查报告和所有可验证产物。"),
            bulleted_block("不把源码副本和大日志长期塞进 Notion，只保留入口、摘要和索引。"),
        ]
    )
    return blocks


def how_to_use_blocks(context: BootstrapContext) -> list[dict[str, Any]]:
    prompt = (
        "请把 Notion 中的 AI ControlLogicMaster 控制中枢当作流程控制面。先读取 Projects 表中的唯一项目行、"
        "Session Briefs 里的 Current Operator Brief、Work Items 里的唯一 Active 项，再结合仓库真相源开始工作。"
    )
    return [
        callout_block("这页的目标是把新会话的启动提示压缩成一句话。", "📌"),
        heading_block(2, "One-Line Starter"),
        code_block(prompt),
        heading_block(2, "Session Flow"),
        numbered_block("读 Projects 里的当前项目状态，确认当前 milestone 与 next action。"),
        numbered_block("读 Session Briefs 里的 Current Operator Brief，获取必读文件和禁止事项。"),
        numbered_block("读 Work Items 里唯一 Active 项，只做这一项，不扩散。"),
        numbered_block("需要更多上下文时，再跳到 Context Packs 或 Artifact Index。"),
        numbered_block("结束时回写 Work Items、Session Briefs 与 Reviews & Decisions。"),
        divider_block(),
        heading_block(2, "Current Default"),
        paragraph_block(f"当前默认目标：{context.next_action}"),
        paragraph_block(f"当前默认阶段：{context.current_phase}"),
    ]


def session_brief_blocks(context: BootstrapContext) -> list[dict[str, Any]]:
    return [
        callout_block("这个 brief 是默认会话入口，未来优先更新它，而不是重新写长 prompt。", "🧠"),
        heading_block(2, "Operating Contract"),
        bulleted_block("Notion 是 control plane，repo 是 code truth。"),
        bulleted_block("只处理当前 active work item，不跨边界扩展。"),
        bulleted_block("任何 freeze_gate_status.yaml 写入、freeze-complete 声明或 Phase 8 开始都不在当前边界内。"),
        divider_block(),
        heading_block(2, "Current Goal"),
        paragraph_block(context.work_item_goal),
        heading_block(2, "Expected Output"),
        paragraph_block(context.work_item_expected_output),
    ]


def work_item_blocks(context: BootstrapContext) -> list[dict[str, Any]]:
    return [
        callout_block("这项任务是当前唯一执行入口。", "⚙️"),
        heading_block(2, "Deliverable"),
        paragraph_block(context.work_item_expected_output),
        heading_block(2, "Non-Goals"),
    ] + [bulleted_block(item) for item in context.do_not_do.split("; ")]


def projects_schema() -> dict[str, Any]:
    return {
        "Project Name": {"title": {}},
        "System Codename": {"rich_text": {}},
        "Repo Path": {"rich_text": {}},
        "Current Milestone": {"rich_text": {}},
        "Current Phase": {"rich_text": {}},
        "Project State": select_schema(
            [
                ("Planned", "gray"),
                ("Active", "blue"),
                ("Review Blocked", "red"),
                ("Accepted", "green"),
                ("Paused", "yellow"),
            ]
        ),
        "Next Action": {"rich_text": {}},
        "Primary Brief": {"rich_text": {}},
        "Last Synced": {"date": {}},
    }


def phases_schema() -> dict[str, Any]:
    return {
        "Phase Name": {"title": {}},
        "Sequence": {"number": {"format": "number"}},
        "State": select_schema(
            [
                ("Accepted", "green"),
                ("Active", "blue"),
                ("Next", "yellow"),
                ("Blocked", "red"),
                ("Not Started", "gray"),
            ]
        ),
        "Outcome Summary": {"rich_text": {}},
        "Key Evidence": {"rich_text": {}},
        "Entry Docs": {"rich_text": {}},
        "Exit Signal": {"rich_text": {}},
        "Last Updated": {"date": {}},
    }


def work_items_schema() -> dict[str, Any]:
    return {
        "Work Item": {"title": {}},
        "State": select_schema(
            [
                ("Active", "blue"),
                ("Next", "yellow"),
                ("Review", "purple"),
                ("Done", "green"),
                ("Blocked", "red"),
            ]
        ),
        "Priority": select_schema(
            [("P0", "red"), ("P1", "orange"), ("P2", "yellow"), ("P3", "gray")]
        ),
        "Kind": select_schema(
            [
                ("Request Package", "blue"),
                ("Review", "purple"),
                ("Action", "green"),
                ("Planning", "yellow"),
                ("Docs", "gray"),
            ]
        ),
        "Current Owner": {"rich_text": {}},
        "Goal": {"rich_text": {}},
        "Must Read": {"rich_text": {}},
        "Non Goals": {"rich_text": {}},
        "Expected Output": {"rich_text": {}},
        "Last Updated": {"date": {}},
    }


def context_packs_schema() -> dict[str, Any]:
    return {
        "Pack Name": {"title": {}},
        "Pack Type": select_schema(
            [
                ("Charter", "blue"),
                ("Board", "purple"),
                ("Current Input", "red"),
                ("Plan", "yellow"),
                ("Review Evidence", "green"),
                ("Architecture", "gray"),
                ("Boundary", "orange"),
                ("Index", "pink"),
            ]
        ),
        "State": select_schema([("Active", "blue"), ("Reference", "green"), ("Historical", "gray")]),
        "Source Path": {"rich_text": {}},
        "Why It Matters": {"rich_text": {}},
        "Snapshot Date": {"date": {}},
    }


def reviews_schema() -> dict[str, Any]:
    return {
        "Review Title": {"title": {}},
        "Decision": select_schema(
            [
                ("Accepted", "green"),
                ("Conditional Pass", "yellow"),
                ("Blocked", "red"),
                ("Needs Fix", "orange"),
            ]
        ),
        "Review Type": select_schema(
            [
                ("Planning", "yellow"),
                ("Request Package", "blue"),
                ("Implementation", "gray"),
                ("Governance", "purple"),
            ]
        ),
        "Related Step": {"rich_text": {}},
        "Source Path": {"rich_text": {}},
        "Required Fixes": {"rich_text": {}},
        "Reviewed At": {"date": {}},
    }


def session_briefs_schema() -> dict[str, Any]:
    return {
        "Brief Name": {"title": {}},
        "Brief Type": select_schema(
            [
                ("Operator Brief", "blue"),
                ("Review Brief", "purple"),
                ("Execution Brief", "green"),
                ("Template", "gray"),
            ]
        ),
        "State": select_schema([("Active", "blue"), ("Template", "gray"), ("Archived", "yellow")]),
        "Goal": {"rich_text": {}},
        "Current Phase": {"rich_text": {}},
        "Next Action": {"rich_text": {}},
        "Must Read": {"rich_text": {}},
        "Do Not Do": {"rich_text": {}},
        "Last Refreshed": {"date": {}},
    }


def artifact_index_schema() -> dict[str, Any]:
    return {
        "Artifact Name": {"title": {}},
        "Artifact Type": select_schema(
            [
                ("README", "blue"),
                ("Board", "purple"),
                ("Input", "red"),
                ("Plan", "yellow"),
                ("Review", "green"),
                ("State File", "gray"),
                ("Code Service", "orange"),
            ]
        ),
        "State": select_schema([("Canonical", "green"), ("Current", "blue"), ("Historical", "gray")]),
        "Local Path": {"rich_text": {}},
        "Why It Matters": {"rich_text": {}},
        "Last Checked": {"date": {}},
    }


def phase_rows(context: BootstrapContext) -> list[dict[str, Any]]:
    rows = [
        (1, "Phase 0 / 1", "Accepted", "Governance, schemas, and knowledge structure accepted.", "README.md", "Core boundaries and models accepted."),
        (2, "Phase 2A / 2B / 2C", "Accepted", "Modeling, validation, and demo execution accepted.", "README.md", "Modeling and validation layers accepted."),
        (3, "Phase 3-1 / 3-2 / 3-3 / 3-4", "Accepted", "Demo strengthening, replay, evaluator boundary, and handoff quality accepted.", "README.md", "Demo-scale operation and audit path accepted."),
        (4, "Phase 4 / 5", "Accepted", "Formal readiness checks and promotion path accepted.", "README.md", "Promotion machinery accepted."),
        (5, "Phase 6", "Accepted", "Freeze-review preparation governance accepted.", "docs/PHASE6_ARCHITECTURE_PLAN.md; docs/PHASE6_FIX_REVIEW_REPORT.md", "State classification and manual-intake boundary accepted."),
        (6, "Phase 7", "Accepted", "Controlled formal population path accepted.", "docs/PHASE7_FORMAL_POPULATION_PLAN.md; docs/PHASE7_REVIEW_REPORT.md", "Formal baseline population mechanism accepted."),
        (7, "Corrected Controlled Population", "Accepted", "Corrected 50-file formal baseline populated and independently reviewed.", "docs/POST_PHASE7_CORRECTED_INVENTORY_CONTROLLED_POPULATION_REVIEW_REPORT.md", "Formal truth contains the corrected inventory."),
        (8, "Freeze-Review Intake Governance Planning", "Accepted", "Smallest correct next governance package decided.", "docs/POST_PHASE7_FREEZE_REVIEW_INTAKE_GOVERNANCE_PLANNING_REVIEW_REPORT.md", "Independent planning review accepted request-package route."),
        (9, "Manual Review Intake Request Package", "Accepted", "Reviewer-facing evidence packet accepted.", "docs/POST_PHASE7_MANUAL_REVIEW_INTAKE_REQUEST_REVIEW_REPORT.md", "Request package independently accepted."),
        (10, "Manual Review Intake Action", "Accepted", "accepted_for_review state acknowledged and independently accepted.", "docs/POST_PHASE7_MANUAL_REVIEW_INTAKE_ACTION_REVIEW_REPORT.md", "Manual review queue acknowledgement accepted."),
        (11, "Final Freeze Signoff Governance Planning", "Accepted", "Checklist-completion request package selected as next bounded step.", "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_GOVERNANCE_PLANNING_REVIEW_REPORT.md", "Planning accepted without entering freeze signoff."),
        (12, "Final Freeze Signoff Checklist Completion Request Package", "Active", "Current bounded package to implement.", "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST_INPUT.md", "Non-executable request packet ready for independent review."),
        (13, "Final Freeze Signoff", "Not Started", "Manual freeze authority may decide later.", "artifacts/.aplh/freeze_gate_status.yaml", "freeze-complete declared by later manual authority."),
    ]
    pages: list[dict[str, Any]] = []
    for sequence, name, state, summary, entry_docs, exit_signal in rows:
        pages.append(
            {
                "title": name,
                "properties": compact_props(
                    {
                        "Phase Name": title_property(name),
                        "Sequence": number_property(sequence),
                        "State": select_property(state),
                        "Outcome Summary": rich_text_property(summary),
                        "Key Evidence": rich_text_property(entry_docs),
                        "Entry Docs": rich_text_property(entry_docs),
                        "Exit Signal": rich_text_property(exit_signal),
                        "Last Updated": date_property(context.today),
                    }
                ),
            }
        )
    return pages


def context_pack_rows(context: BootstrapContext) -> list[dict[str, Any]]:
    entries = [
        ("Repository README", "Charter", "Active", "README.md", "Top-level current status, next step, and repository routing."),
        ("Milestone Board", "Board", "Active", "docs/MILESTONE_BOARD.md", "Fast human-readable dashboard for current milestone and blockers."),
        (
            "Current Request Input",
            "Current Input",
            "Active",
            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST_INPUT.md",
            "Canonical bounded input for the current request-package session.",
        ),
        (
            "Freeze Signoff Governance Plan",
            "Plan",
            "Reference",
            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_GOVERNANCE_PLAN.md",
            "Explains why the checklist-completion request package is the smallest correct next step.",
        ),
        (
            "Freeze Signoff Governance Planning Review",
            "Review Evidence",
            "Reference",
            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_GOVERNANCE_PLANNING_REVIEW_REPORT.md",
            "Independent acceptance record that preserves the freeze boundary.",
        ),
        (
            "Manual Review Intake Action Review",
            "Review Evidence",
            "Reference",
            "docs/POST_PHASE7_MANUAL_REVIEW_INTAKE_ACTION_REVIEW_REPORT.md",
            "Shows accepted_for_review is already stable and accepted.",
        ),
        ("Architecture Overview", "Architecture", "Reference", "docs/ARCHITECTURE_OVERVIEW.md", "System structure and component boundaries."),
        ("Assumptions And Boundaries", "Boundary", "Reference", "docs/ASSUMPTIONS_AND_BOUNDARIES.md", "Guardrails and explicit scope boundaries."),
        ("Docs Index", "Index", "Reference", "docs/README.md", "Entry point for the docs tree."),
    ]
    return [
        {
            "title": name,
            "properties": compact_props(
                {
                    "Pack Name": title_property(name),
                    "Pack Type": select_property(pack_type),
                    "State": select_property(state),
                    "Source Path": rich_text_property(path),
                    "Why It Matters": rich_text_property(reason),
                    "Snapshot Date": date_property(context.today),
                }
            ),
        }
        for name, pack_type, state, path, reason in entries
    ]


def review_rows(context: BootstrapContext) -> list[dict[str, Any]]:
    entries = [
        (
            "Manual Review Intake Action Review",
            "Accepted",
            "Governance",
            "Post-Phase7 Manual Review Intake Action",
            "docs/POST_PHASE7_MANUAL_REVIEW_INTAKE_ACTION_REVIEW_REPORT.md",
            "No blocking findings.",
        ),
        (
            "Manual Review Intake Request Review",
            "Accepted",
            "Request Package",
            "Post-Phase7 Manual Review Intake Request Package",
            "docs/POST_PHASE7_MANUAL_REVIEW_INTAKE_REQUEST_REVIEW_REPORT.md",
            "No open required fixes.",
        ),
        (
            "Freeze-Review Intake Governance Planning Review",
            "Accepted",
            "Planning",
            "Freeze-Review Intake Governance Planning",
            "docs/POST_PHASE7_FREEZE_REVIEW_INTAKE_GOVERNANCE_PLANNING_REVIEW_REPORT.md",
            "No open required fixes.",
        ),
        (
            "Final Freeze Signoff Governance Planning Review",
            "Accepted",
            "Planning",
            "Final Freeze Signoff Governance Planning",
            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_GOVERNANCE_PLANNING_REVIEW_REPORT.md",
            "No blocking findings.",
        ),
    ]
    return [
        {
            "title": name,
            "properties": compact_props(
                {
                    "Review Title": title_property(name),
                    "Decision": select_property(decision),
                    "Review Type": select_property(review_type),
                    "Related Step": rich_text_property(step),
                    "Source Path": rich_text_property(path),
                    "Required Fixes": rich_text_property(fixes),
                    "Reviewed At": date_property("2026-04-08"),
                }
            ),
        }
        for name, decision, review_type, step, path, fixes in entries
    ]


def artifact_rows(context: BootstrapContext) -> list[dict[str, Any]]:
    entries = [
        ("Repository README", "README", "Canonical", "README.md", "Top-level routing and current next step."),
        ("Milestone Board", "Board", "Current", "docs/MILESTONE_BOARD.md", "Fast overview of current status and blockers."),
        (
            "Checklist Completion Request Input",
            "Input",
            "Current",
            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST_INPUT.md",
            "Current bounded input for the active package.",
        ),
        (
            "Freeze Signoff Governance Plan",
            "Plan",
            "Canonical",
            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_GOVERNANCE_PLAN.md",
            "Authoritative plan for the current boundary.",
        ),
        (
            "Freeze Signoff Governance Planning Review Report",
            "Review",
            "Canonical",
            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_GOVERNANCE_PLANNING_REVIEW_REPORT.md",
            "Planning acceptance record.",
        ),
        (
            "Acceptance Audit Log",
            "State File",
            "Current",
            "artifacts/.aplh/acceptance_audit_log.yaml",
            "Contains the accepted_for_review manual intake record.",
        ),
        (
            "Freeze Readiness Report",
            "State File",
            "Current",
            "artifacts/.aplh/freeze_readiness_report.yaml",
            "Shows accepted_for_review and that docs remain incomplete.",
        ),
        (
            "Freeze Gate Status",
            "State File",
            "Current",
            "artifacts/.aplh/freeze_gate_status.yaml",
            "Manual-only final freeze surface that must remain unchanged now.",
        ),
        (
            "Freeze Review Preparer Service",
            "Code Service",
            "Canonical",
            "aero_prop_logic_harness/services/freeze_review_preparer.py",
            "Core code that supports freeze review preparation flow.",
        ),
    ]
    return [
        {
            "title": name,
            "properties": compact_props(
                {
                    "Artifact Name": title_property(name),
                    "Artifact Type": select_property(kind),
                    "State": select_property(state),
                    "Local Path": rich_text_property(path),
                    "Why It Matters": rich_text_property(why),
                    "Last Checked": date_property(context.today),
                }
            ),
        }
        for name, kind, state, path, why in entries
    ]


def ensure_state_dir(repo_root: Path) -> None:
    (repo_root / STATE_FILE.parent).mkdir(parents=True, exist_ok=True)


def write_state(repo_root: Path, data: dict[str, Any]) -> None:
    ensure_state_dir(repo_root)
    (repo_root / STATE_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_state(repo_root: Path) -> dict[str, Any]:
    return json.loads((repo_root / STATE_FILE).read_text(encoding="utf-8"))


def build_workspace_root(
    client: NotionClient,
    context: BootstrapContext,
    parent_page_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if parent_page_id:
        existing = search_page_by_title(client, ROOT_TITLE, parent_page_id)
        if existing:
            return {"mode": "child-page", "parent_page_id": parent_page_id, "reused": True}, existing
        root_page = client.create_page(
            {"type": "page_id", "page_id": parent_page_id},
            ROOT_TITLE,
            icon_emoji="🧭",
            children=root_page_blocks(context),
        )
        return {"mode": "child-page", "parent_page_id": parent_page_id}, root_page

    try:
        root_page = client.create_page(
            {"type": "workspace", "workspace": True},
            ROOT_TITLE,
            icon_emoji="🧭",
            children=root_page_blocks(context),
        )
        return {"mode": "workspace-page"}, root_page
    except NotionError:
        container_db = client.create_database(
            {"type": "workspace", "workspace": True},
            "AI ControlLogicMaster 中枢入口",
            {
                "Hub": {"title": {}},
                "Kind": select_schema([("Control Hub", "blue"), ("Archive", "gray")]),
            },
        )
        container_data_source_id = database_data_source_id(container_db)
        root_page = client.create_data_source_page(
            container_data_source_id,
            {
                "Hub": title_property(ROOT_TITLE),
                "Kind": select_property("Control Hub"),
            },
            icon_emoji="🧭",
            children=root_page_blocks(context),
        )
        return {
            "mode": "workspace-database",
            "container_database_id": container_db["id"],
            "container_database_url": container_db.get("url"),
            "container_data_source_id": container_data_source_id,
        }, root_page


def create_child_database(
    client: NotionClient,
    parent_page_id: str,
    title: str,
    schema: dict[str, Any],
    existing_database_id: str | None = None,
) -> dict[str, Any]:
    if existing_database_id:
        result = {
            "title": title,
            "database_id": existing_database_id,
            "database_url": f"https://www.notion.so/{existing_database_id.replace('-', '')}",
            "data_source_id": resolve_data_source_id(client, title, existing_database_id),
        }
        sync_schema(client, result["data_source_id"], schema)
        return result
    created = client.create_database({"type": "page_id", "page_id": parent_page_id}, title, schema)
    result = {
        "title": title,
        "database_id": created["id"],
        "database_url": created.get("url"),
        "data_source_id": database_data_source_id(created),
    }
    sync_schema(client, result["data_source_id"], schema)
    return result


def create_rows(
    client: NotionClient,
    data_source_id: str,
    rows: list[dict[str, Any]],
    *,
    icon_emoji: str | None = None,
) -> list[dict[str, Any]]:
    created_rows: list[dict[str, Any]] = []
    for row in rows:
        created_rows.append(
            client.create_data_source_page(
                data_source_id,
                row["properties"],
                icon_emoji=icon_emoji,
                children=row.get("children"),
            )
        )
    return created_rows


def bootstrap(repo_root: Path, parent_page_id: str | None = None) -> None:
    token = os.environ.get("NOTION_API_KEY")
    if not token:
        raise SystemExit("NOTION_API_KEY is not set.")

    state_path = repo_root / STATE_FILE
    if state_path.exists():
        raise SystemExit(f"{STATE_FILE} already exists. Run sync or remove it before bootstrapping again.")

    client = NotionClient(token)
    context = build_context(repo_root)
    root_meta, root_page = build_workspace_root(client, context, parent_page_id)
    root_page_id = root_page["id"]
    child_pages, child_databases = child_title_maps(client, root_page_id)

    if "How To Use This Hub" in child_pages:
        how_to_use_page = {"id": child_pages["How To Use This Hub"], "url": f"https://www.notion.so/{child_pages['How To Use This Hub'].replace('-', '')}"}
    else:
        how_to_use_page = client.create_page(
            {"type": "page_id", "page_id": root_page_id},
            "How To Use This Hub",
            icon_emoji="📘",
            children=how_to_use_blocks(context),
        )

    databases: dict[str, Any] = {}
    for key, (title, schema) in base_database_specs().items():
        databases[key] = create_child_database(
            client,
            root_page_id,
            title,
            schema,
            existing_database_id=child_databases.get(title),
        )

    project_row = client.create_data_source_page(
        databases["projects"]["data_source_id"],
        compact_props(
            {
                "Project Name": title_property(context.project_name),
                "System Codename": rich_text_property(context.system_codename),
                "Repo Path": rich_text_property(context.repo_path),
                "Current Milestone": rich_text_property(context.current_milestone),
                "Current Phase": rich_text_property(context.current_phase),
                "Project State": select_property(context.project_state),
                "Next Action": rich_text_property(context.next_action),
                "Primary Brief": rich_text_property("Session Briefs / Current Operator Brief"),
                "Last Synced": date_property(context.today),
            }
        ),
        icon_emoji="🗂️",
    )

    active_work_item = client.create_data_source_page(
        databases["work_items"]["data_source_id"],
        compact_props(
            {
                "Work Item": title_property(context.active_work_item),
                "State": select_property("Active"),
                "Priority": select_property("P0"),
                "Kind": select_property("Request Package"),
                "Current Owner": rich_text_property("Codex"),
                "Goal": rich_text_property(context.work_item_goal),
                "Must Read": rich_text_property(context.must_read),
                "Non Goals": rich_text_property(context.do_not_do),
                "Expected Output": rich_text_property(context.work_item_expected_output),
                "Last Updated": date_property(context.today),
            }
        ),
        icon_emoji="⚙️",
        children=work_item_blocks(context),
    )

    create_rows(
        client,
        databases["work_items"]["data_source_id"],
        [
            {
                "properties": compact_props(
                    {
                        "Work Item": title_property("Independent review of checklist completion request package"),
                        "State": select_property("Next"),
                        "Priority": select_property("P1"),
                        "Kind": select_property("Review"),
                        "Current Owner": rich_text_property("Independent reviewer"),
                        "Goal": rich_text_property("Review the non-executable request packet before any docs-only action."),
                        "Must Read": rich_text_property(
                            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST.md; "
                            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST_REVIEW_INPUT.md"
                        ),
                        "Non Goals": rich_text_property(
                            "Do not write freeze_gate_status.yaml; do not declare freeze-complete."
                        ),
                        "Expected Output": rich_text_property(
                            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST_REVIEW_REPORT.md"
                        ),
                        "Last Updated": date_property(context.today),
                    }
                )
            },
            {
                "properties": compact_props(
                    {
                        "Work Item": title_property("Docs-only checklist completion action"),
                        "State": select_property("Next"),
                        "Priority": select_property("P1"),
                        "Kind": select_property("Action"),
                        "Current Owner": rich_text_property("Later authorized actor"),
                        "Goal": rich_text_property("Close remaining checklist/doc evidence gap without entering freeze signoff."),
                        "Must Read": rich_text_property(
                            "Future reviewed checklist completion package and current freeze readiness evidence."
                        ),
                        "Non Goals": rich_text_property(
                            "No freeze signoff; no freeze-complete; no Phase 8."
                        ),
                        "Expected Output": rich_text_property("Docs/checklist evidence updated and independently reviewed."),
                        "Last Updated": date_property(context.today),
                    }
                )
            },
        ],
    )

    session_brief = client.create_data_source_page(
        databases["session_briefs"]["data_source_id"],
        compact_props(
            {
                "Brief Name": title_property("Current Operator Brief"),
                "Brief Type": select_property("Operator Brief"),
                "State": select_property("Active"),
                "Goal": rich_text_property(context.work_item_goal),
                "Current Phase": rich_text_property(context.current_phase),
                "Next Action": rich_text_property(context.next_action),
                "Must Read": rich_text_property(context.must_read),
                "Do Not Do": rich_text_property(context.do_not_do),
                "Last Refreshed": date_property(context.today),
            }
        ),
        icon_emoji="🧠",
        children=session_brief_blocks(context),
    )

    create_rows(
        client,
        databases["session_briefs"]["data_source_id"],
        [
            {
                "properties": compact_props(
                    {
                        "Brief Name": title_property("Review Session Template"),
                        "Brief Type": select_property("Template"),
                        "State": select_property("Template"),
                        "Goal": rich_text_property("Read the current package, identify blockers first, and preserve boundaries."),
                        "Current Phase": rich_text_property("Use the current active package"),
                        "Next Action": rich_text_property("Publish review findings and decision."),
                        "Must Read": rich_text_property("Current package, review input, README, milestone board."),
                        "Do Not Do": rich_text_property("Do not expand scope or perform implementation work unless explicitly requested."),
                        "Last Refreshed": date_property(context.today),
                    }
                )
            }
        ],
    )

    create_rows(client, databases["phases"]["data_source_id"], phase_rows(context))
    create_rows(client, databases["context_packs"]["data_source_id"], context_pack_rows(context))
    create_rows(client, databases["reviews"]["data_source_id"], review_rows(context))
    create_rows(client, databases["artifact_index"]["data_source_id"], artifact_rows(context))

    state = {
        "repo_root": str(repo_root),
        "root_page_id": root_page_id,
        "root_page_url": root_page.get("url"),
        "supporting_pages": {
            "how_to_use": {"page_id": how_to_use_page["id"], "url": how_to_use_page.get("url")}
        },
        "records": {
            "project": {"page_id": project_row["id"], "url": project_row.get("url")},
            "active_work_item": {"page_id": active_work_item["id"], "url": active_work_item.get("url")},
            "current_operator_brief": {"page_id": session_brief["id"], "url": session_brief.get("url")},
        },
        "databases": databases,
        "root_meta": root_meta,
        "last_synced": context.today,
    }
    write_state(repo_root, state)

    print(json.dumps(state, ensure_ascii=False, indent=2))


def sync(repo_root: Path) -> None:
    token = os.environ.get("NOTION_API_KEY")
    if not token:
        raise SystemExit("NOTION_API_KEY is not set.")

    client = NotionClient(token)
    state = refresh_state_from_notion(client, repo_root, read_state(repo_root))
    context = build_context(repo_root)

    project_id = state["records"]["project"]["page_id"]
    work_item_id = state["records"]["active_work_item"]["page_id"]
    brief_id = state["records"]["current_operator_brief"]["page_id"]

    client.update_page(
        project_id,
        compact_props(
            {
                "Current Milestone": rich_text_property(context.current_milestone),
                "Current Phase": rich_text_property(context.current_phase),
                "Project State": select_property(context.project_state),
                "Next Action": rich_text_property(context.next_action),
                "Last Synced": date_property(context.today),
            }
        ),
    )

    client.update_page(
        work_item_id,
        compact_props(
            {
                "State": select_property("Active"),
                "Goal": rich_text_property(context.work_item_goal),
                "Must Read": rich_text_property(context.must_read),
                "Non Goals": rich_text_property(context.do_not_do),
                "Expected Output": rich_text_property(context.work_item_expected_output),
                "Last Updated": date_property(context.today),
            }
        ),
    )

    client.update_page(
        brief_id,
        compact_props(
            {
                "Goal": rich_text_property(context.work_item_goal),
                "Current Phase": rich_text_property(context.current_phase),
                "Next Action": rich_text_property(context.next_action),
                "Must Read": rich_text_property(context.must_read),
                "Do Not Do": rich_text_property(context.do_not_do),
                "Last Refreshed": date_property(context.today),
            }
        ),
    )

    state["last_synced"] = context.today
    write_state(repo_root, state)
    print(json.dumps({"status": "ok", "last_synced": context.today, "root_page_url": state["root_page_url"]}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap and sync the Notion control hub for AI ControlLogicMaster.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Create the Notion control hub and seed initial records.")
    bootstrap_parser.add_argument(
        "--parent-page-id",
        help="Optional existing Notion page id to place the hub under if workspace-level creation is blocked.",
    )

    subparsers.add_parser("sync", help="Refresh the active project row, current brief, and active work item.")

    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    if args.command == "bootstrap":
        bootstrap(repo_root, args.parent_page_id)
    elif args.command == "sync":
        sync(repo_root)
    else:
        raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    try:
        main()
    except NotionError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
