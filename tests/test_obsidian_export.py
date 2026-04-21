from __future__ import annotations

import json
from pathlib import Path

from core.integrations.obsidian_export import (
    ObsidianVault,
    export_note_to_obsidian,
    export_studio_output_to_obsidian,
    get_obsidian_vault,
)
from core.models.note import Note
from core.models.notebook import Notebook
from core.models.studio_output import StudioOutput


class TestObsidianVaultDiscovery:
    def test_prefers_open_vault(self, tmp_path):
        open_vault = tmp_path / "open-vault"
        older_vault = tmp_path / "older-vault"
        open_vault.mkdir()
        older_vault.mkdir()
        config_path = tmp_path / "obsidian.json"
        config_path.write_text(
            json.dumps(
                {
                    "vaults": {
                        "older": {"path": str(older_vault), "ts": 10, "open": False},
                        "open": {"path": str(open_vault), "ts": 1, "open": True},
                    }
                }
            ),
            encoding="utf-8",
        )

        vault = get_obsidian_vault(config_path=config_path)

        assert vault is not None
        assert vault.name == "open-vault"
        assert vault.path == open_vault


class TestObsidianExport:
    def test_export_note_writes_markdown_with_frontmatter(self, tmp_path):
        vault_root = tmp_path / "vault"
        vault_root.mkdir()
        vault = ObsidianVault(name="vault", path=vault_root)
        notebook = Notebook(
            id="nb-1",
            name="适航知识库 / COMAC",
            created_at="2026-04-21T09:00:00Z",
            updated_at="2026-04-21T09:00:00Z",
        )
        note = Note(
            id="note-12345678",
            notebook_id="nb-1",
            title="发动机结冰边界分析",
            content="这是导出的笔记内容。",
            citations=[
                {
                    "source_file": "icing.pdf",
                    "page_number": 7,
                    "content": "关键结冰边界描述",
                    "bbox": [1, 2, 3, 4],
                }
            ],
            created_at="2026-04-21T10:00:00Z",
            updated_at="2026-04-21T10:05:00Z",
        )

        result = export_note_to_obsidian(vault=vault, notebook=notebook, note=note)

        exported_path = Path(result.file_path)
        assert exported_path.exists()
        text = exported_path.read_text(encoding="utf-8")
        assert 'record_type: "note"' in text
        assert 'notebook_name: "适航知识库 / COMAC"' in text
        assert "这是导出的笔记内容。" in text
        assert "icing.pdf p.7" in text
        assert result.relative_path.startswith("COMAC Intelligent NotebookLM/")
        assert "obsidian://open?vault=vault&file=" in result.obsidian_url

    def test_export_studio_writes_into_studio_folder(self, tmp_path):
        vault_root = tmp_path / "vault"
        vault_root.mkdir()
        vault = ObsidianVault(name="vault", path=vault_root)
        notebook = Notebook(
            id="nb-1",
            name="Flight Deck Notes",
            created_at="2026-04-21T09:00:00Z",
            updated_at="2026-04-21T09:00:00Z",
        )
        output = StudioOutput(
            id="studio-abcdef12",
            notebook_id="nb-1",
            output_type="summary",
            title="执行摘要 · 10:00",
            content="这是 Studio 导出的内容。",
            citations=[],
            created_at="2026-04-21T10:00:00Z",
        )

        result = export_studio_output_to_obsidian(
            vault=vault,
            notebook=notebook,
            output=output,
        )

        exported_path = Path(result.file_path)
        assert exported_path.exists()
        assert "/Studio/" in result.relative_path
        text = exported_path.read_text(encoding="utf-8")
        assert 'record_type: "studio_output"' in text
        assert 'output_type: "summary"' in text
        assert "这是 Studio 导出的内容。" in text
