from pathlib import Path
import re


DATA_DIR = Path("data")
SPACES_DIR = DATA_DIR / "spaces"
LEGACY_DOCS_DIR = DATA_DIR / "docs"
LEGACY_NOTES_FILE = DATA_DIR / "notes.json"


def normalize_space_id(space_id: str) -> str:
    raw = (space_id or "default").strip()
    raw = raw.replace("\\", "-").replace("/", "-")
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", raw)
    safe = safe.strip(".-")
    return safe or "default"


def get_space_root(space_id: str, *, ensure_exists: bool = False) -> Path:
    root = SPACES_DIR / normalize_space_id(space_id)
    if ensure_exists:
        root.mkdir(parents=True, exist_ok=True)
    return root


def get_space_docs_dir(space_id: str, *, for_write: bool = False) -> Path:
    docs_dir = get_space_root(space_id, ensure_exists=for_write) / "docs"
    if for_write:
        docs_dir.mkdir(parents=True, exist_ok=True)
        return docs_dir

    if docs_dir.exists():
        return docs_dir

    if normalize_space_id(space_id) == "default" and LEGACY_DOCS_DIR.exists():
        return LEGACY_DOCS_DIR

    return docs_dir


def get_space_notes_file(space_id: str, *, for_write: bool = False) -> Path:
    notes_file = get_space_root(space_id, ensure_exists=for_write) / "notes.json"
    if for_write:
        notes_file.parent.mkdir(parents=True, exist_ok=True)
        return notes_file

    if notes_file.exists():
        return notes_file

    if normalize_space_id(space_id) == "default" and LEGACY_NOTES_FILE.exists():
        return LEGACY_NOTES_FILE

    return notes_file
