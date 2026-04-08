# Notion Control Hub

This repo now includes a bootstrap script for creating a dedicated Notion control hub for `AI ControlLogicMaster` without touching the existing `AI-Harness` Notion projects.

## Why This Exists

The goal is to stop rebuilding long session prompts by hand.

Instead of copying a full prompt every time, the new flow is:

1. Open the Notion hub.
2. Read `Projects` -> the single active project row.
3. Read `Session Briefs` -> `Current Operator Brief`.
4. Read `Work Items` -> the single `Active` item.
5. Use the repo as the code and evidence truth source.

That turns the session starter into one sentence:

```text
请把 Notion 中的 AI ControlLogicMaster 控制中枢当作流程控制面。先读取 Projects 表中的唯一项目行、Session Briefs 里的 Current Operator Brief、Work Items 里的唯一 Active 项，再结合仓库真相源开始工作。
```

## Architecture

This hub borrows the same high-level split used by the `AI-Harness` control-tower projects:

- Notion = control plane
- Repo = code truth plane
- Review reports / state files = evidence plane

The hub creates these child databases:

- `Projects`
- `Phases`
- `Work Items`
- `Context Packs`
- `Reviews & Decisions`
- `Session Briefs`
- `Artifact Index`

After the GSD cockpit upgrade, the hub also gains:

- `GSD Phases`
- `GSD Plans`
- `Review Gates`
- `Automation Runs`

It also creates one helper page:

- `How To Use This Hub`

## Commands

Bootstrap the hub once:

```bash
python scripts/notion_control_hub.py bootstrap
```

Refresh the active project row, active work item, and current operator brief later:

```bash
python scripts/notion_control_hub.py sync
```

Upgrade and sync the GSD cockpit layer:

```bash
python scripts/gsd_cockpit.py sync
```

Get the current machine-readable autopilot status:

```bash
python scripts/gsd_cockpit.py status
```

If your Notion integration cannot create a workspace-level page directly, you can create one blank parent page manually in Notion and pass it in:

```bash
python scripts/notion_control_hub.py bootstrap --parent-page-id <page-id>
```

## Local State

The bootstrap script stores created Notion ids in:

```text
.planning/notion_hub.json
```

That file is used by `sync` so the repo can refresh the active brief without recreating the whole structure.

The sync layer now treats that file as a cache, not the source of truth. Before writing anything, it re-discovers the root page, child databases, and key rows from Notion itself. That means moving the hub to a different parent page will not normally break the cockpit as long as the new location is still shared with the same Notion integration.

## Current Seeding Logic

The initial hub is seeded from the current repo state, especially:

- `README.md`
- `docs/MILESTONE_BOARD.md`
- `docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_CHECKLIST_COMPLETION_REQUEST_INPUT.md`
- `docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_GOVERNANCE_PLAN.md`
- `docs/POST_PHASE7_FINAL_FREEZE_SIGNOFF_GOVERNANCE_PLANNING_REVIEW_REPORT.md`

That means the Notion hub starts with the real current milestone, current bounded work item, must-read docs, and hard prohibitions already filled in.

After the GSD cockpit upgrade, the hub also mirrors:

- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/phases/*`
- explicit Opus 4.6 review gates

## Autopilot Boundary

This cockpit is designed to let Codex run the repo as far as the current GSD plan permits, then stop hard at explicit review boundaries.

- Automated: local GSD context refresh, phase/plan tracking, Notion sync, and bounded execution inside the current approved phase
- Manual: each Opus 4.6 review trigger and the final freeze-authority handoff
- Never automatic: declaring freeze-complete, writing final freeze authority output, or silently crossing a blocked review gate
