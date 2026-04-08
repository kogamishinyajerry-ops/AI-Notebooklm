#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import notion_control_hub as hub


@dataclass
class CockpitContext:
    repo_root: Path
    today: str
    timestamp: str
    current_phase: str
    current_phase_name: str
    current_plan: str
    resume_command: str
    automation_state: str
    next_human_gate: str
    blockers: str
    project_state: str
    next_action: str


def run_json(cmd: list[str], cwd: Path) -> dict[str, Any]:
    output = subprocess.check_output(cmd, cwd=cwd, text=True)
    return json.loads(output)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_bullets(section_name: str, text: str) -> list[str]:
    pattern = re.compile(rf"^###\s+{re.escape(section_name)}\n(.*?)(?=^###\s+|\Z)", re.M | re.S)
    match = pattern.search(text)
    if not match:
        return []
    return [line[2:].strip() for line in match.group(1).splitlines() if line.startswith("- ")]


def build_context(repo_root: Path) -> CockpitContext:
    roadmap = run_json(
        ["node", str(Path.home() / ".codex/get-shit-done/bin/gsd-tools.cjs"), "roadmap", "analyze"],
        repo_root,
    )
    state_text = read_text(repo_root / ".planning/STATE.md")
    issues_text = read_text(repo_root / ".planning/ISSUES.md")
    project_text = read_text(repo_root / ".planning/PROJECT.md")

    current_phase = roadmap.get("current_phase") or "13"
    phases = {phase["number"]: phase for phase in roadmap.get("phases", [])}
    current_phase_name = phases.get(current_phase, {}).get("name", "Checklist Completion Request Package")

    current_plan_match = re.search(r"^Plan:\s*([^\n]+)$", state_text, re.M)
    current_plan = current_plan_match.group(1).strip() if current_plan_match else "01 of 01 in current phase"

    next_action_match = re.search(r"^Status:\s*([^\n]+)$", state_text, re.M)
    status = next_action_match.group(1).strip() if next_action_match else "Ready to execute"

    blocker_bullets = extract_bullets("Blockers/Concerns", state_text)
    if not blocker_bullets:
        blocker_bullets = []
        for line in issues_text.splitlines():
            if line.startswith("- **"):
                blocker_bullets.append(line[2:].strip())
    blockers = "; ".join(blocker_bullets[:3])

    requirements_active = []
    active_match = re.search(r"^### Active\n(.*?)(?=^###\s+|\Z)", project_text, re.M | re.S)
    if active_match:
        requirements_active = [line[6:].strip() for line in active_match.group(1).splitlines() if line.startswith("- [ ] ")]
    next_action = requirements_active[2] if len(requirements_active) >= 3 else "Execute Phase 13 plan 13-01"

    return CockpitContext(
        repo_root=repo_root,
        today=datetime.now().date().isoformat(),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        current_phase=current_phase,
        current_phase_name=current_phase_name,
        current_plan=current_plan,
        resume_command=f"$gsd-execute-phase {current_phase}",
        automation_state="Autopilot Ready",
        next_human_gate="Phase 14 - user-triggered Opus 4.6 review of the checklist request package",
        blockers=blockers,
        project_state=status,
        next_action=next_action,
    )


def query_rows(client: hub.NotionClient, data_source_id: str) -> list[dict[str, Any]]:
    data = client._request("POST", f"/v1/data_sources/{data_source_id}/query", {})
    return data.get("results", [])


def row_title(row: dict[str, Any]) -> str:
    props = row.get("properties", {})
    title_prop = next(
        (value for value in props.values() if isinstance(value, dict) and value.get("type") == "title"),
        None,
    )
    return "".join(piece.get("plain_text", "") for piece in (title_prop or {}).get("title", []))


def rows_by_title(client: hub.NotionClient, data_source_id: str) -> dict[str, dict[str, Any]]:
    return {row_title(row): row for row in query_rows(client, data_source_id)}


def upsert_row(
    client: hub.NotionClient,
    data_source_id: str,
    title: str,
    properties: dict[str, Any],
    *,
    children: list[dict[str, Any]] | None = None,
    icon_emoji: str | None = None,
) -> dict[str, Any]:
    existing = rows_by_title(client, data_source_id).get(title)
    if existing:
        client.update_page(existing["id"], properties)
        return existing
    return client.create_data_source_page(data_source_id, properties, children=children, icon_emoji=icon_emoji)


def sync_row_set(
    client: hub.NotionClient,
    data_source_id: str,
    rows: list[tuple[str, dict[str, Any]]],
) -> None:
    existing = rows_by_title(client, data_source_id)
    for title, properties in rows:
        match = existing.get(title)
        if match:
            client.update_page(match["id"], properties)
            continue
        created = client.create_data_source_page(data_source_id, properties)
        existing[title] = created


def cockpit_projects_schema() -> dict[str, Any]:
    schema = hub.projects_schema()
    schema.update(
        {
            "Automation State": hub.select_schema(
                [
                    ("Autopilot Ready", "green"),
                    ("Paused for Opus 4.6", "yellow"),
                    ("Blocked", "red"),
                    ("Manual Authority", "gray"),
                ]
            ),
            "Current GSD Phase": {"rich_text": {}},
            "Resume Command": {"rich_text": {}},
            "Next Human Gate": {"rich_text": {}},
            "Known Blockers": {"rich_text": {}},
            "Review Model": hub.select_schema([("Opus 4.6", "purple"), ("Manual Freeze Authority", "gray")]),
        }
    )
    return schema


def cockpit_work_items_schema() -> dict[str, Any]:
    schema = hub.work_items_schema()
    schema.update(
        {
            "Run Command": {"rich_text": {}},
            "Stop Condition": {"rich_text": {}},
            "Review Gate": {"rich_text": {}},
            "Local Path": {"rich_text": {}},
        }
    )
    return schema


def cockpit_session_briefs_schema() -> dict[str, Any]:
    schema = hub.session_briefs_schema()
    schema.update(
        {
            "Resume Command": {"rich_text": {}},
            "Pause Rule": {"rich_text": {}},
            "Review Trigger": {"rich_text": {}},
        }
    )
    return schema


def gsd_phases_schema() -> dict[str, Any]:
    return {
        "GSD Phase": {"title": {}},
        "Sequence": {"number": {"format": "number"}},
        "State": hub.select_schema(
            [
                ("Complete", "green"),
                ("Ready", "blue"),
                ("Awaiting Review", "yellow"),
                ("Future", "gray"),
                ("Manual Only", "red"),
            ]
        ),
        "Execution Mode": hub.select_schema(
            [
                ("Automated", "blue"),
                ("Manual Review", "purple"),
                ("Manual Authority", "red"),
            ]
        ),
        "Goal": {"rich_text": {}},
        "Depends On": {"rich_text": {}},
        "Run Command": {"rich_text": {}},
        "Stop Condition": {"rich_text": {}},
        "Last Synced": {"date": {}},
    }


def gsd_plans_schema() -> dict[str, Any]:
    return {
        "Plan ID": {"title": {}},
        "Phase": {"rich_text": {}},
        "State": hub.select_schema(
            [
                ("Done", "green"),
                ("Ready", "blue"),
                ("Future", "gray"),
                ("Blocked", "red"),
            ]
        ),
        "Local Path": {"rich_text": {}},
        "Run Command": {"rich_text": {}},
        "Objective": {"rich_text": {}},
        "Review Gate After": {"rich_text": {}},
        "Last Synced": {"date": {}},
    }


def review_gates_schema() -> dict[str, Any]:
    return {
        "Gate Name": {"title": {}},
        "Phase": {"rich_text": {}},
        "State": hub.select_schema(
            [
                ("Pending Trigger", "yellow"),
                ("Waiting Result", "blue"),
                ("Passed", "green"),
                ("Blocked", "red"),
                ("Future", "gray"),
            ]
        ),
        "Review Model": hub.select_schema([("Opus 4.6", "purple"), ("Manual Freeze Authority", "red")]),
        "Trigger Condition": {"rich_text": {}},
        "Input Artifact": {"rich_text": {}},
        "Resume On Pass": {"rich_text": {}},
        "Resume On Block": {"rich_text": {}},
        "Last Synced": {"date": {}},
    }


def automation_runs_schema() -> dict[str, Any]:
    return {
        "Run Name": {"title": {}},
        "Run Type": hub.select_schema(
            [
                ("Bootstrap", "green"),
                ("Sync", "blue"),
                ("Execution", "yellow"),
                ("Review", "purple"),
            ]
        ),
        "State": hub.select_schema([("Success", "green"), ("Failed", "red"), ("In Progress", "blue")]),
        "Command": {"rich_text": {}},
        "Summary": {"rich_text": {}},
        "Started On": {"date": {}},
    }


def phase_rows(context: CockpitContext) -> list[tuple[str, dict[str, Any]]]:
    entries = [
        (
            "12 - GSD + Notion Cockpit Bootstrap",
            12,
            "Complete",
            "Automated",
            "Bootstrap local GSD state and upgrade Notion into a cockpit.",
            "Historical accepted work only.",
            "Completed in this session.",
            "None.",
        ),
        (
            "13 - Checklist Completion Request Package",
            13,
            "Ready",
            "Automated",
            "Draft the current non-executable checklist completion request package and review input.",
            "Phase 12",
            "$gsd-execute-phase 13",
            "Stop when the request package and review input are complete, then wait for Opus 4.6.",
        ),
        (
            "14 - Opus Review - Checklist Request",
            14,
            "Awaiting Review",
            "Manual Review",
            "Pause for a user-triggered Opus 4.6 review of the checklist request package.",
            "Phase 13",
            "User triggers Opus 4.6; Codex ingests result afterward.",
            "Do not advance into Phase 15 until review result is captured.",
        ),
        (
            "15 - Docs-Only Checklist Completion Action",
            15,
            "Future",
            "Automated",
            "Execute the bounded docs-only checklist completion action after review pass.",
            "Phase 14",
            "$gsd-plan-phase 15 or execute the approved docs-only action plan",
            "Stop before the next Opus 4.6 review gate.",
        ),
        (
            "16 - Opus Review - Checklist Action",
            16,
            "Future",
            "Manual Review",
            "Pause for user-triggered Opus 4.6 review of the docs-only checklist action.",
            "Phase 15",
            "User triggers Opus 4.6; Codex ingests result afterward.",
            "Do not advance into Phase 17 until review result is captured.",
        ),
        (
            "17 - Final Freeze Signoff Request Package",
            17,
            "Future",
            "Automated",
            "Draft the later final freeze-signoff request package.",
            "Phase 16",
            "$gsd-plan-phase 17",
            "Stop before Opus 4.6 review of the freeze-signoff request.",
        ),
        (
            "18 - Opus Review - Freeze Signoff Request",
            18,
            "Future",
            "Manual Review",
            "Pause for user-triggered Opus 4.6 review of the freeze-signoff request package.",
            "Phase 17",
            "User triggers Opus 4.6; Codex ingests result afterward.",
            "Do not advance into Phase 19 until review result is captured.",
        ),
        (
            "19 - Manual Freeze Authority Handoff",
            19,
            "Future",
            "Manual Authority",
            "Hand off the final package to the later manual freeze authority.",
            "Phase 18",
            "Manual-only terminal boundary.",
            "Automation ends at this handoff boundary.",
        ),
    ]

    rows: list[tuple[str, dict[str, Any]]] = []
    for title, sequence, state, mode, goal, depends_on, run_command, stop_condition in entries:
        rows.append(
            (
                title,
                hub.compact_props(
                    {
                        "GSD Phase": hub.title_property(title),
                        "Sequence": hub.number_property(sequence),
                        "State": hub.select_property(state),
                        "Execution Mode": hub.select_property(mode),
                        "Goal": hub.rich_text_property(goal),
                        "Depends On": hub.rich_text_property(depends_on),
                        "Run Command": hub.rich_text_property(run_command),
                        "Stop Condition": hub.rich_text_property(stop_condition),
                        "Last Synced": hub.date_property(context.today),
                    }
                ),
            )
        )
    return rows


def plan_rows(context: CockpitContext) -> list[tuple[str, dict[str, Any]]]:
    entries = [
        (
            "12-01",
            "12",
            "Done",
            ".planning/phases/12-gsd-notion-cockpit-bootstrap/12-01-PLAN.md",
            "Historical - already completed",
            "Bootstrap local GSD planning and upgrade Notion cockpit.",
            "None",
        ),
        (
            "13-01",
            "13",
            "Ready",
            ".planning/phases/13-checklist-completion-request/13-01-PLAN.md",
            "$gsd-execute-phase 13",
            "Draft the checklist completion request package and review input.",
            "RG-14 Checklist Request Review",
        ),
        (
            "15-01",
            "15",
            "Future",
            "TBD",
            "$gsd-plan-phase 15",
            "Execute docs-only checklist completion after review pass.",
            "RG-16 Checklist Action Review",
        ),
        (
            "17-01",
            "17",
            "Future",
            "TBD",
            "$gsd-plan-phase 17",
            "Draft the final freeze signoff request package.",
            "RG-18 Freeze Signoff Request Review",
        ),
    ]
    rows: list[tuple[str, dict[str, Any]]] = []
    for title, phase, state, local_path, command, objective, gate_after in entries:
        rows.append(
            (
                title,
                hub.compact_props(
                    {
                        "Plan ID": hub.title_property(title),
                        "Phase": hub.rich_text_property(phase),
                        "State": hub.select_property(state),
                        "Local Path": hub.rich_text_property(local_path),
                        "Run Command": hub.rich_text_property(command),
                        "Objective": hub.rich_text_property(objective),
                        "Review Gate After": hub.rich_text_property(gate_after),
                        "Last Synced": hub.date_property(context.today),
                    }
                ),
            )
        )
    return rows


def review_gate_rows(context: CockpitContext) -> list[tuple[str, dict[str, Any]]]:
    entries = [
        (
            "RG-14 Checklist Request Review",
            "14",
            "Pending Trigger",
            "Opus 4.6",
            "Phase 13 request package and review input are complete.",
            "docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST.md; docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST_REVIEW_INPUT.md",
            "Advance to Phase 15 docs-only checklist completion action.",
            "Create a bounded fix plan before retrying review.",
        ),
        (
            "RG-16 Checklist Action Review",
            "16",
            "Future",
            "Opus 4.6",
            "Phase 15 docs-only checklist action is complete.",
            "Phase 15 outputs and refreshed readiness evidence.",
            "Advance to Phase 17 final freeze-signoff request package.",
            "Create a bounded fix plan before retrying review.",
        ),
        (
            "RG-18 Freeze Signoff Request Review",
            "18",
            "Future",
            "Opus 4.6",
            "Phase 17 freeze-signoff request package is complete.",
            "Phase 17 request package and supporting evidence.",
            "Advance to Phase 19 manual freeze-authority handoff.",
            "Create a bounded fix plan before retrying review.",
        ),
        (
            "RG-19 Manual Freeze Authority",
            "19",
            "Future",
            "Manual Freeze Authority",
            "All prior review gates have passed and the final handoff bundle is ready.",
            "Final handoff bundle only.",
            "Terminal manual boundary.",
            "Automation stops permanently at this boundary.",
        ),
    ]
    rows: list[tuple[str, dict[str, Any]]] = []
    for title, phase, state, model, trigger, artifact, on_pass, on_block in entries:
        rows.append(
            (
                title,
                hub.compact_props(
                    {
                        "Gate Name": hub.title_property(title),
                        "Phase": hub.rich_text_property(phase),
                        "State": hub.select_property(state),
                        "Review Model": hub.select_property(model),
                        "Trigger Condition": hub.rich_text_property(trigger),
                        "Input Artifact": hub.rich_text_property(artifact),
                        "Resume On Pass": hub.rich_text_property(on_pass),
                        "Resume On Block": hub.rich_text_property(on_block),
                        "Last Synced": hub.date_property(context.today),
                    }
                ),
            )
        )
    return rows


def playbook_blocks(context: CockpitContext) -> list[dict[str, Any]]:
    return [
        hub.callout_block("This page defines the autopilot loop: Codex runs until it hits an explicit manual review gate.", "🚦"),
        hub.heading_block(2, "Autopilot Loop"),
        hub.numbered_block("Read `.planning/STATE.md`, the Project row, the active work item, and the GSD Phases table."),
        hub.numbered_block(f"If the current phase is automated, resume with `{context.resume_command}`."),
        hub.numbered_block("When the current plan reaches an Opus 4.6 gate, stop immediately and wait for the user to trigger review."),
        hub.numbered_block("Ingest the review result, sync Notion, and continue to the next automated phase only after the gate is cleared."),
        hub.divider_block(),
        hub.heading_block(2, "Current Resume Point"),
        hub.paragraph_block(f"Current phase: {context.current_phase} - {context.current_phase_name}"),
        hub.paragraph_block(f"Resume command: {context.resume_command}"),
        hub.paragraph_block(f"Next human gate: {context.next_human_gate}"),
        hub.divider_block(),
        hub.heading_block(2, "Stop Conditions"),
        hub.bulleted_block("Pause at every Opus 4.6 review gate."),
        hub.bulleted_block("Pause at the later manual freeze-authority handoff."),
        hub.bulleted_block("Do not cross into freeze-complete or Phase 8 from automation."),
    ]


def status_payload(context: CockpitContext) -> dict[str, Any]:
    return {
        "current_phase": context.current_phase,
        "current_phase_name": context.current_phase_name,
        "current_plan": context.current_plan,
        "resume_command": context.resume_command,
        "automation_state": context.automation_state,
        "next_human_gate": context.next_human_gate,
        "project_state": context.project_state,
        "next_action": context.next_action,
        "should_pause_for_manual_review": False,
    }


def ensure_supporting_page(client: hub.NotionClient, root_page_id: str, title: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    child_pages, _ = hub.child_title_maps(client, root_page_id)
    existing_id = child_pages.get(title)
    if existing_id:
        return {"id": existing_id, "url": f"https://www.notion.so/{existing_id.replace('-', '')}"}
    return client.create_page({"type": "page_id", "page_id": root_page_id}, title, icon_emoji="🚦", children=blocks)


def sync() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    notion_state_path = repo_root / ".planning/notion_hub.json"
    if not notion_state_path.exists():
        raise SystemExit("No .planning/notion_hub.json found. Bootstrap the Notion hub first.")

    client = hub.NotionClient(hub.os.environ["NOTION_API_KEY"])
    context = build_context(repo_root)
    notion_state = hub.refresh_state_from_notion(
        client,
        repo_root,
        json.loads(notion_state_path.read_text(encoding="utf-8")),
    )

    project_ds = notion_state["databases"]["projects"]["data_source_id"]
    work_items_ds = notion_state["databases"]["work_items"]["data_source_id"]
    session_briefs_ds = notion_state["databases"]["session_briefs"]["data_source_id"]

    hub.sync_schema(client, project_ds, cockpit_projects_schema())
    hub.sync_schema(client, work_items_ds, cockpit_work_items_schema())
    hub.sync_schema(client, session_briefs_ds, cockpit_session_briefs_schema())

    root_page_id = notion_state["root_page_id"]
    _, child_databases = hub.child_title_maps(client, root_page_id)

    extra_specs = {
        "gsd_phases": ("GSD Phases", gsd_phases_schema()),
        "gsd_plans": ("GSD Plans", gsd_plans_schema()),
        "review_gates": ("Review Gates", review_gates_schema()),
        "automation_runs": ("Automation Runs", automation_runs_schema()),
    }

    gsd_databases: dict[str, Any] = {}
    for key, (title, schema) in extra_specs.items():
        gsd_databases[key] = hub.create_child_database(
            client,
            root_page_id,
            title,
            schema,
            existing_database_id=child_databases.get(title),
        )

    playbook = ensure_supporting_page(client, root_page_id, "GSD Autopilot Playbook", playbook_blocks(context))

    project_page_id = notion_state["records"]["project"]["page_id"]
    active_work_item_id = notion_state["records"]["active_work_item"]["page_id"]
    brief_page_id = notion_state["records"]["current_operator_brief"]["page_id"]

    client.update_page(
        project_page_id,
        hub.compact_props(
            {
                "Project State": hub.select_property("Active"),
                "Next Action": hub.rich_text_property("Execute Phase 13 plan 13-01, then pause for Opus 4.6 review."),
                "Automation State": hub.select_property(context.automation_state),
                "Current GSD Phase": hub.rich_text_property(f"Phase {context.current_phase} / 13-01"),
                "Resume Command": hub.rich_text_property(context.resume_command),
                "Next Human Gate": hub.rich_text_property(context.next_human_gate),
                "Known Blockers": hub.rich_text_property(context.blockers),
                "Review Model": hub.select_property("Opus 4.6"),
                "Last Synced": hub.date_property(context.today),
            }
        ),
    )

    client.update_page(
        active_work_item_id,
        hub.compact_props(
            {
                "State": hub.select_property("Active"),
                "Run Command": hub.rich_text_property(context.resume_command),
                "Stop Condition": hub.rich_text_property(
                    "Stop after request package + review input are ready; wait for user-triggered Opus 4.6 review."
                ),
                "Review Gate": hub.rich_text_property("RG-14 Checklist Request Review"),
                "Local Path": hub.rich_text_property(".planning/phases/13-checklist-completion-request/13-01-PLAN.md"),
                "Last Updated": hub.date_property(context.today),
            }
        ),
    )

    client.update_page(
        brief_page_id,
        hub.compact_props(
            {
                "Goal": hub.rich_text_property("Run the current automated phase until the next explicit Opus 4.6 review gate."),
                "Next Action": hub.rich_text_property("Execute Phase 13 plan 13-01."),
                "Resume Command": hub.rich_text_property(context.resume_command),
                "Pause Rule": hub.rich_text_property("Pause immediately at Phase 14 / Opus 4.6 review gate."),
                "Review Trigger": hub.rich_text_property("User manually triggers Opus 4.6 when Phase 13 outputs are ready."),
                "Last Refreshed": hub.date_property(context.today),
            }
        ),
    )

    sync_row_set(client, gsd_databases["gsd_phases"]["data_source_id"], phase_rows(context))
    sync_row_set(client, gsd_databases["gsd_plans"]["data_source_id"], plan_rows(context))
    sync_row_set(client, gsd_databases["review_gates"]["data_source_id"], review_gate_rows(context))
    sync_row_set(
        client,
        gsd_databases["automation_runs"]["data_source_id"],
        [
            (
                "Current Automation Snapshot",
                hub.compact_props(
                    {
                        "Run Name": hub.title_property("Current Automation Snapshot"),
                        "Run Type": hub.select_property("Sync"),
                        "State": hub.select_property("Success"),
                        "Command": hub.rich_text_property("python scripts/gsd_cockpit.py sync"),
                        "Summary": hub.rich_text_property(
                            "Synchronized GSD phases, plans, review gates, and current resume point into the Notion cockpit."
                        ),
                        "Started On": hub.date_property(context.today),
                    }
                ),
            )
        ],
    )

    notion_state.setdefault("gsd", {})
    notion_state["gsd"]["databases"] = gsd_databases
    notion_state.setdefault("supporting_pages", {})
    notion_state["supporting_pages"]["gsd_playbook"] = {"page_id": playbook["id"], "url": playbook.get("url")}
    notion_state["last_synced"] = context.today
    notion_state_path.write_text(json.dumps(notion_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "root_page_url": notion_state["root_page_url"],
                "gsd_playbook_url": playbook.get("url"),
                "current_phase": context.current_phase,
                "resume_command": context.resume_command,
            },
            ensure_ascii=False,
        )
    )


def status() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    context = build_context(repo_root)
    print(json.dumps(status_payload(context), ensure_ascii=False))


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"sync", "status"}:
        raise SystemExit("Usage: python scripts/gsd_cockpit.py [sync|status]")
    if sys.argv[1] == "sync":
        sync()
        return
    status()


if __name__ == "__main__":
    main()
