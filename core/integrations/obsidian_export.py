from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional
from urllib.parse import quote


OBSIDIAN_CONFIG_PATH = (
    Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
)
EXPORT_ROOT_DIRNAME = "COMAC Intelligent NotebookLM"


@dataclass(frozen=True)
class ObsidianVault:
    name: str
    path: Path


@dataclass(frozen=True)
class ObsidianExportResult:
    vault_name: str
    vault_path: str
    relative_path: str
    file_path: str
    obsidian_url: str

    def to_dict(self) -> dict:
        return {
            "vault_name": self.vault_name,
            "vault_path": self.vault_path,
            "relative_path": self.relative_path,
            "file_path": self.file_path,
            "obsidian_url": self.obsidian_url,
        }


def get_obsidian_vault(config_path: Optional[Path] = None) -> Optional[ObsidianVault]:
    config_file = Path(config_path or OBSIDIAN_CONFIG_PATH)
    if not config_file.exists():
        return None

    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    raw_vaults = data.get("vaults")
    if not isinstance(raw_vaults, dict):
        return None

    candidates = []
    for payload in raw_vaults.values():
        if not isinstance(payload, dict):
            continue
        raw_path = payload.get("path")
        if not raw_path:
            continue
        vault_path = Path(raw_path).expanduser()
        if not vault_path.exists() or not vault_path.is_dir():
            continue
        candidates.append(
            (
                bool(payload.get("open")),
                int(payload.get("ts") or 0),
                vault_path,
            )
        )

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    vault_path = candidates[0][2]
    return ObsidianVault(name=vault_path.name, path=vault_path)


def export_note_to_obsidian(
    *,
    vault: ObsidianVault,
    notebook: Any,
    note: Any,
) -> ObsidianExportResult:
    return _export_record(
        vault=vault,
        notebook_id=notebook.id,
        notebook_name=notebook.name,
        record_type="note",
        record_id=note.id,
        title=note.title,
        content=note.content,
        created_at=note.created_at,
        updated_at=getattr(note, "updated_at", note.created_at),
        citations=getattr(note, "citations", []),
        section_dir="Notes",
    )


def export_studio_output_to_obsidian(
    *,
    vault: ObsidianVault,
    notebook: Any,
    output: Any,
) -> ObsidianExportResult:
    return _export_record(
        vault=vault,
        notebook_id=notebook.id,
        notebook_name=notebook.name,
        record_type="studio_output",
        record_id=output.id,
        title=output.title,
        content=output.content,
        created_at=output.created_at,
        updated_at=output.created_at,
        citations=getattr(output, "citations", []),
        section_dir="Studio",
        output_type=getattr(output, "output_type", None),
    )


def _export_record(
    *,
    vault: ObsidianVault,
    notebook_id: str,
    notebook_name: str,
    record_type: str,
    record_id: str,
    title: str,
    content: str,
    created_at: str,
    updated_at: Optional[str],
    citations: Iterable[dict],
    section_dir: str,
    output_type: Optional[str] = None,
) -> ObsidianExportResult:
    safe_notebook = _sanitize_segment(notebook_name)
    safe_title = _sanitize_segment(title)
    timestamp = _timestamp_slug(created_at)
    relative_path = Path(
        EXPORT_ROOT_DIRNAME,
        safe_notebook,
        section_dir,
        f"{timestamp}-{safe_title}-{record_id[:8]}.md",
    )
    target = vault.path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    markdown = _render_markdown(
        notebook_id=notebook_id,
        notebook_name=notebook_name,
        record_type=record_type,
        record_id=record_id,
        title=title,
        content=content,
        created_at=created_at,
        updated_at=updated_at,
        citations=list(citations),
        output_type=output_type,
    )
    target.write_text(markdown, encoding="utf-8")

    rel_posix = relative_path.as_posix()
    obsidian_url = (
        f"obsidian://open?vault={quote(vault.name)}&file={quote(rel_posix, safe='/')}"
    )
    return ObsidianExportResult(
        vault_name=vault.name,
        vault_path=str(vault.path),
        relative_path=rel_posix,
        file_path=str(target),
        obsidian_url=obsidian_url,
    )


def _render_markdown(
    *,
    notebook_id: str,
    notebook_name: str,
    record_type: str,
    record_id: str,
    title: str,
    content: str,
    created_at: str,
    updated_at: Optional[str],
    citations: List[dict],
    output_type: Optional[str],
) -> str:
    lines = [
        "---",
        'app: "COMAC Intelligent NotebookLM"',
        f"record_type: {_yaml_string(record_type)}",
        f"record_id: {_yaml_string(record_id)}",
        f"notebook_id: {_yaml_string(notebook_id)}",
        f"notebook_name: {_yaml_string(notebook_name)}",
        f"title: {_yaml_string(title)}",
        f"created_at: {_yaml_string(created_at)}",
    ]
    if updated_at:
        lines.append(f"updated_at: {_yaml_string(updated_at)}")
    if output_type:
        lines.append(f"output_type: {_yaml_string(output_type)}")
    lines.extend(_render_citations_frontmatter(citations))
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(content.strip())
    lines.append("")
    lines.append("## Metadata")
    lines.append("")
    lines.append(f"- Notebook: {notebook_name}")
    lines.append(f"- Record type: {record_type}")
    lines.append(f"- Record id: `{record_id}`")
    lines.append(f"- Created at: `{created_at}`")
    if updated_at:
        lines.append(f"- Updated at: `{updated_at}`")
    if output_type:
        lines.append(f"- Output type: `{output_type}`")
    lines.append("")
    lines.append("## Citations")
    lines.append("")
    if citations:
        for index, citation in enumerate(citations, start=1):
            source_file = citation.get("source_file", "unknown")
            page_number = citation.get("page_number", "?")
            lines.append(f"{index}. {source_file} p.{page_number}")
            excerpt = str(citation.get("content", "")).strip()
            if excerpt:
                for excerpt_line in excerpt.splitlines():
                    lines.append(f"   > {excerpt_line}")
    else:
        lines.append("No citations attached.")
    lines.append("")
    return "\n".join(lines)


def _render_citations_frontmatter(citations: List[dict]) -> List[str]:
    if not citations:
        return ["citations: []"]

    lines = ["citations:"]
    for citation in citations:
        lines.append(f"  - source_file: {_yaml_string(str(citation.get('source_file', '')))}")
        lines.append(f"    page_number: {int(citation.get('page_number', 0) or 0)}")
        content = str(citation.get("content", ""))
        lines.append(f"    content: {_yaml_string(content)}")
        bbox = citation.get("bbox")
        if bbox is None:
            lines.append("    bbox: null")
        else:
            lines.append(f"    bbox: {json.dumps(bbox, ensure_ascii=False)}")
    return lines


def _yaml_string(value: str) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def _sanitize_segment(value: str) -> str:
    sanitized = re.sub(r"[\\/:*?\"<>|]+", "-", (value or "").strip())
    sanitized = re.sub(r"\s+", " ", sanitized).strip(" .")
    return sanitized or "untitled"


def _timestamp_slug(value: str) -> str:
    normalized = (value or "").strip().replace(":", "-")
    normalized = normalized.replace("+", "-")
    return normalized or "unknown-time"
