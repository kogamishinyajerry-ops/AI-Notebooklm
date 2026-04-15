from __future__ import annotations

from pathlib import Path, PurePath, PureWindowsPath


def safe_upload_filename(filename: str | None) -> str:
    """Return a basename-only upload filename or raise ValueError."""
    if not filename:
        raise ValueError("Upload filename is required")

    name = PurePath(PureWindowsPath(filename).name).name
    if name in {"", ".", ".."}:
        raise ValueError("Upload filename is invalid")
    return name


def safe_upload_path(upload_dir: str | Path, filename: str | None) -> Path:
    return Path(upload_dir) / safe_upload_filename(filename)
