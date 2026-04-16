from __future__ import annotations

from scripts.build_review_pack import build_review_pack


def _snapshot():
    return {
        "page": {"url": "https://example.com/notion"},
        "databases": [
            {
                "title": "🗃 项目总表 (Projects)",
                "rows": [
                    {
                        "title": "COMAC 智能 NotebookLM",
                        "properties": {
                            "Current Phase": "V3.2 review-ready",
                        },
                    }
                ],
            },
            {
                "title": "🗃 阶段控制 (Phases)",
                "rows": [
                    {
                        "title": "S-17: Notebook & Source Data Model",
                        "properties": {
                            "Status": "Ready for Review",
                            "Review Decision": "Pending",
                            "Next Phase Pointer": "S-18",
                            "Artifact Index": "https://example.com/pr/29",
                        },
                    },
                    {
                        "title": "S-18: Source-Scoped Retrieval & Ingestion Closure",
                        "properties": {
                            "Status": "Ready for Review",
                            "Review Decision": "Pending",
                            "Next Phase Pointer": "S-19",
                            "Artifact Index": "https://example.com/artifact/s18",
                        },
                    },
                ],
            },
            {
                "title": "🗃 纪检核查处 (Reviews)",
                "rows": [
                    {
                        "title": "S-17 Gate Review — Notebook & Source Data Model",
                        "properties": {
                            "Review Status": "Requested",
                            "Reviewer Model": "Opus 4.6",
                            "Review Artifact Link": "https://example.com/pr/29",
                            "Blocking Issues": "Pending formal gate.",
                        },
                    }
                ],
            },
            {
                "title": "🗃 交付产物库 (Artifacts)",
                "rows": [
                    {
                        "title": "Artifact S-18: Source-Scoped Retrieval Closure",
                        "properties": {
                            "Artifact Type": "Review Pack",
                            "Storage URL": "https://example.com/artifact/s18",
                            "Summary": "S-18 local alignment.",
                        },
                    },
                    {
                        "title": "Artifact V3.2: Local Verification Alignment (175 passed)",
                        "properties": {
                            "Artifact Type": "Test Report",
                            "Storage URL": "https://example.com/artifact/v32",
                            "Summary": "175 passed.",
                        },
                    },
                ],
            },
        ],
    }


def test_build_review_pack_includes_phase_review_and_artifact_sections():
    markdown = build_review_pack(_snapshot(), ("S-17", "S-18"), "pytest => 175 passed")

    assert "# V3.2 Review Pack" in markdown
    assert "## Phase Matrix" in markdown
    assert "## Review Queue" in markdown
    assert "## Artifacts" in markdown
    assert "S-17: Notebook & Source Data Model" in markdown
    assert "S-17 Gate Review — Notebook & Source Data Model" in markdown
    assert "Artifact S-18: Source-Scoped Retrieval Closure" in markdown


def test_build_review_pack_carries_verification_summary():
    markdown = build_review_pack(_snapshot(), ("S-17", "S-18"), "python3 -m pytest -q => 175 passed")

    assert "python3 -m pytest -q => 175 passed" in markdown
    assert "All V3.2 phases from S-17 through S-23" in markdown
