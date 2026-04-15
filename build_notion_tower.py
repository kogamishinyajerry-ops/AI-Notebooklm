import os
import json
import time
import requests

API_KEY = os.getenv("NOTION_API_KEY")
PARENT_PAGE_ID = os.getenv("NOTION_PARENT_PAGE_ID", "342c6894-2bed-80d0-be2f-d9d85ff9e2cd")

if not API_KEY:
    raise SystemExit("Set NOTION_API_KEY before running build_notion_tower.py")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

def create_select(options):
    return {"select": {"options": [{"name": o} for o in options]}}

def create_multi_select(options):
    return {"multi_select": {"options": [{"name": o} for o in options]}}

def create_db(title, props):
    data = {
        "parent": {"type": "page_id", "page_id": PARENT_PAGE_ID},
        "title": [{"type": "text", "text": {"content": title}}],
        "is_inline": True,
        "properties": props
    }
    resp = requests.post("https://api.notion.com/v1/databases", headers=HEADERS, json=data)
    if resp.status_code != 200:
        print(f"Error creating {title}: {resp.text}")
        return None
    res_id = resp.json()["id"]
    print(f"Created DB '{title}' ({res_id})")
    time.sleep(0.5)
    return res_id

print("1. Creating Title and Context...")
page_content = {
    "children": [
        {
            "object": "block",
            "type": "heading_1",
            "heading_1": {"rich_text": [{"type": "text", "text": {"content": "⚓️ Antigravity 工作流控制塔"}}]}
        },
        {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": "本架构由 AI-Harness 控制塔 v1 演进而成，专为适配 Antigravity / Claude Code / Codex 多模型开发工作流而设。\n\n本页面为 Truth Source（真相源），提供从需求输入 (Specs/Constraints) 到代码执行 (Tasks) 到评估验收 (Reviews) 的自动化治理闭环。"}}],
                "icon": {"emoji": "\u2699\ufe0f"}
            }
        },
        {
            "object": "block",
            "type": "divider",
            "divider": {}
        }
    ]
}
requests.patch(f"https://api.notion.com/v1/blocks/{PARENT_PAGE_ID}/children", headers=HEADERS, json=page_content)


print("2. Creating 7 Core Databases...")
# Projects
prj_props = {
    "Project Name": {"title": {}},
    "Domain": create_select(['AI-CFD', 'Web', 'Infrastructure', 'Data Pipeline', 'Knowledge Base']),
    "Project Status": create_select(['Planned', 'Active', 'ReviewHold', 'Blocked', 'Complete', 'Archived']),
    "Active Spec Version": {"rich_text": {}},
    "Active Constraint Version": {"rich_text": {}},
    "Current Phase": {"rich_text": {}},
    "Routing Policy": create_select(['High Risk', 'Medium Risk', 'Low Risk', 'Antigravity Full']),
    "Repo URL": {"url": {}},
    "Dashboard Link": {"url": {}},
    "Owner": {"people": {}},
    "Chief Reviewer": {"people": {}}
}
prj_id = create_db("🗃 项目总表 (Projects)", prj_props)

# Specs
spec_props = {
    "Title": {"title": {}},
    "Scope Type": create_select(['Requirements', 'Architecture', 'Business Rules', 'API Contract']),
    "Status": create_select(['Draft', 'Active', 'Deprecated']),
    "Version": {"rich_text": {}},
    "Effective Date": {"date": {}},
    "Risk Notes": {"rich_text": {}},
    "Change Summary": {"rich_text": {}}
}
spec_id = create_db("🗃 需求与架构说明 (Specs)", spec_props)

# Constraints
con_props = {
    "Constraint Name": {"title": {}},
    "Constraint Type": create_select(['Architecture', 'Directory', 'Interface', 'Dependency', 'Testing', 'Security', 'State Machine']),
    "Severity": create_select(['Critical', 'High', 'Medium', 'Low']),
    "Applies To": create_multi_select(['All Phases', 'Execution', 'Review', 'Writeback']),
    "Enabled": {"checkbox": {}},
    "Version": {"rich_text": {}},
    "Validation Rule": {"rich_text": {}},
    "Blocking Rule": {"rich_text": {}}
}
con_id = create_db("🗃 执行约束与边界 (Constraints)", con_props)

# Phases
phs_props = {
    "Phase Name": {"title": {}},
    "Status": create_select(['Draft', 'Ready for Execution', 'Executing', 'Ready for Review', 'Under Review', 'Completed']),
    "Sequence": {"number": {}},
    "Review Priority": create_select(['P0', 'P1', 'P2', 'P3']),
    "Review Decision": create_select(['Pass', 'Conditional Pass', 'Blocked', 'Pending', 'Approved']),
    "Assigned Executor": create_select(['Codex', 'Claude Code', 'Gemini 3.1', 'Human']),
    "Assigned Reviewer": create_select(['Opus 4.6', 'Gemini 3.1 Pro']),
    "Input Constraint Version": {"rich_text": {}},
    "Input Spec Version": {"rich_text": {}},
    "Start Time": {"date": {}},
    "End Time": {"date": {}},
    "Next Phase Pointer": {"rich_text": {}},
    "Artifact Index": {"url": {}}
}
phs_id = create_db("🗃 阶段控制 (Phases)", phs_props)

# Tasks
tsk_props = {
    "Task Name": {"title": {}},
    "Priority": create_select(['P0', 'P1', 'P2', 'P3']),
    "Task Type": create_select(['Implementation', 'Fix', 'Refactor', 'Test', 'Documentation', 'Review Prep']),
    "Task Status": create_select(['Queued', 'Running', 'Succeeded', 'Failed', 'Retry Pending', 'Escalated']),
    "Executor Model": create_select(['Codex', 'Claude Code', 'Opus 4.6', 'Gemini 3.1 Pro']),
    "Retry Count": {"number": {}},
    "Failure Reason": {"rich_text": {}},
    "Last Run Summary": {"rich_text": {}},
    "PR Link": {"url": {}},
    "Artifact Link": {"url": {}},
    "Git Branch": {"rich_text": {}}
}
tsk_id = create_db("🗃 任务原子网 (Tasks)", tsk_props)

# Reviews
rev_props = {
    "Review Title": {"title": {}},
    "Review Status": create_select(['Requested', 'In Progress', 'Completed']),
    "Review Type": create_select(['Phase Gate', 'Architecture', 'Harness Compliance', 'Risk Assessment', 'Project Acceptance Review']),
    "Decision": create_select(['Pass', 'Conditional Pass', 'Blocked']),
    "Reviewer Model": create_select(['Opus 4.6', 'Gemini 3.1 Pro']),
    "Blocking Issues": {"rich_text": {}},
    "Required Fixes": {"rich_text": {}},
    "Conditional Pass Items": {"rich_text": {}},
    "Suggested Next Phase": {"rich_text": {}},
    "Reviewed At": {"date": {}},
    "Review Artifact Link": {"url": {}}
}
rev_id = create_db("🗃 纪检核查处 (Reviews)", rev_props)

# Artifacts
art_props = {
    "Artifact Name": {"title": {}},
    "Artifact Type": create_select(['Test Report', 'Build Log', 'Review Pack', 'Diff / Patch', 'Benchmark', 'Handoff Bundle']),
    "Generated By": create_select(['Codex', 'Claude Code', 'Opus 4.6', 'CI / Runner', 'Human']),
    "Retention Policy": create_select(['Permanent', '90 Days', '30 Days', 'Ephemeral']),
    "Provenance": {"rich_text": {}},
    "Storage URL": {"url": {}},
    "Summary": {"rich_text": {}}
}
art_id = create_db("🗃 交付产物库 (Artifacts)", art_props)

print("3. Connecting Relations...")
def create_relation(db_id, prop_name, target_db_id):
    data = {"properties": {prop_name: {"relation": {"database_id": target_db_id}}}}
    requests.patch(f"https://api.notion.com/v1/databases/{db_id}", headers=HEADERS, json=data)

if prj_id:
    if phs_id: create_relation(prj_id, "Phases", phs_id)
    if spec_id: create_relation(prj_id, "Specs", spec_id)
    if con_id: create_relation(prj_id, "Constraints", con_id)
    if tsk_id: create_relation(prj_id, "Tasks", tsk_id)
if phs_id:
    if prj_id: create_relation(phs_id, "Linked Project", prj_id)
    if tsk_id: create_relation(phs_id, "Tasks", tsk_id)
    if rev_id: create_relation(phs_id, "Reviews", rev_id)
if spec_id and prj_id: create_relation(spec_id, "Linked Project", prj_id)
if con_id and prj_id: create_relation(con_id, "Linked Project", prj_id)
if tsk_id:
    if prj_id: create_relation(tsk_id, "Linked Project", prj_id)
    if phs_id: create_relation(tsk_id, "Linked Phase", phs_id)
if rev_id and phs_id: create_relation(rev_id, "Linked Phase", phs_id)
print("Relations connected successfully!")
