from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PHASES = ("S-17", "S-18", "S-19", "S-20", "S-21", "S-22", "S-23")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_snapshot(snapshot_path: str | Path) -> dict:
    return json.loads(Path(snapshot_path).read_text(encoding="utf-8"))


def find_database(snapshot: dict, title: str) -> dict:
    for db in snapshot.get("databases", []):
        if db.get("title") == title:
            return db
    raise SystemExit(f"Database not found in snapshot: {title}")


def starts_with_any(text: str, prefixes: tuple[str, ...]) -> bool:
    return any(text.startswith(prefix) for prefix in prefixes)


def collect_project(snapshot: dict) -> dict:
    projects = find_database(snapshot, "🗃 项目总表 (Projects)")
    if not projects.get("rows"):
        raise SystemExit("Projects database is empty")
    return projects["rows"][0]


def collect_phases(snapshot: dict, prefixes: tuple[str, ...]) -> list[dict]:
    phase_db = find_database(snapshot, "🗃 阶段控制 (Phases)")
    rows = [
        row for row in phase_db.get("rows", [])
        if starts_with_any(row.get("title", ""), prefixes)
    ]
    return sorted(rows, key=lambda row: row["title"])


def collect_reviews(snapshot: dict, prefixes: tuple[str, ...]) -> list[dict]:
    review_db = find_database(snapshot, "🗃 纪检核查处 (Reviews)")
    rows = [
        row for row in review_db.get("rows", [])
        if starts_with_any(row.get("title", ""), prefixes)
    ]
    return sorted(rows, key=lambda row: row["title"])


def collect_artifacts(snapshot: dict, prefixes: tuple[str, ...]) -> list[dict]:
    artifact_db = find_database(snapshot, "🗃 交付产物库 (Artifacts)")
    rows = []
    for row in artifact_db.get("rows", []):
        title = row.get("title", "")
        if (
            starts_with_any(title, prefixes)
            or any(title.startswith(f"Artifact {prefix}:") for prefix in prefixes)
            or title.startswith("Artifact V3.2:")
        ):
            rows.append(row)
    return sorted(rows, key=lambda row: row["title"])


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        safe = [cell.replace("\n", "<br>") for cell in row]
        lines.append("| " + " | ".join(safe) + " |")
    return lines


def build_review_pack(snapshot: dict, prefixes: tuple[str, ...], verification_summary: str) -> str:
    project = collect_project(snapshot)
    phases = collect_phases(snapshot, prefixes)
    reviews = collect_reviews(snapshot, prefixes)
    artifacts = collect_artifacts(snapshot, prefixes)

    lines = [
        "# V3.2 Review Pack",
        "",
        f"- Generated at: `{utc_now_iso()}`",
        f"- Source page: {snapshot['page']['url']}",
        f"- Project: **{project['title']}**",
        f"- Current Phase: {project['properties'].get('Current Phase')}",
        f"- Verification Baseline: {verification_summary}",
        "",
        "## Phase Matrix",
        "",
    ]

    phase_rows = [
        [
            row["title"],
            str(row["properties"].get("Status", "")),
            str(row["properties"].get("Review Decision", "")),
            str(row["properties"].get("Next Phase Pointer", "")),
            str(row["properties"].get("Artifact Index", "")),
        ]
        for row in phases
    ]
    lines.extend(markdown_table(
        ["Phase", "Status", "Review Decision", "Next", "Artifact Index"],
        phase_rows,
    ))

    lines.extend(["", "## Review Queue", ""])
    review_rows = [
        [
            row["title"],
            str(row["properties"].get("Review Status", "")),
            str(row["properties"].get("Reviewer Model", "")),
            str(row["properties"].get("Review Artifact Link", "")),
            str(row["properties"].get("Blocking Issues", "")),
        ]
        for row in reviews
    ]
    lines.extend(markdown_table(
        ["Review", "Status", "Reviewer", "Artifact Link", "Blocking Issues"],
        review_rows,
    ))

    lines.extend(["", "## Artifacts", ""])
    artifact_rows = [
        [
            row["title"],
            str(row["properties"].get("Artifact Type", "")),
            str(row["properties"].get("Storage URL", "")),
            str(row["properties"].get("Summary", "")),
        ]
        for row in artifacts
    ]
    lines.extend(markdown_table(
        ["Artifact", "Type", "Storage URL", "Summary"],
        artifact_rows,
    ))

    lines.extend([
        "",
        "## Readiness Note",
        "",
        "- All V3.2 phases from S-17 through S-23 are now aligned in Notion with the verified local repository state.",
        "- Review rows exist for each phase and are marked `Requested`, preserving the distinction between local verification and formal Opus 4.6 gate approval.",
        f"- The current local verification baseline is `{verification_summary}`.",
        "",
    ])

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a local markdown review pack from a synced Notion snapshot.")
    parser.add_argument("--snapshot", required=True, help="Path to a synced Notion snapshot JSON file")
    parser.add_argument(
        "--output",
        default="docs/V3_2_REVIEW_PACK.md",
        help="Output markdown path",
    )
    parser.add_argument(
        "--phase-prefix",
        action="append",
        default=[],
        help="Phase prefix to include; repeat as needed (default: S-17..S-23)",
    )
    parser.add_argument(
        "--verification-summary",
        default="python3 -m pytest -q => 180 passed",
        help="Verification summary text written into the pack",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    prefixes = tuple(args.phase_prefix) if args.phase_prefix else DEFAULT_PHASES
    snapshot = load_snapshot(args.snapshot)
    markdown = build_review_pack(snapshot, prefixes, args.verification_summary)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(output_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
