from __future__ import annotations

from pathlib import Path, PurePath, PureWindowsPath


PDF_CONTENT_TYPE = "application/pdf"
PDF_MAGIC = b"%PDF"
PDF_SUFFIX = ".pdf"


def safe_upload_filename(filename: str | None) -> str:
    """Return a basename-only upload filename or raise ValueError."""
    if not filename:
        raise ValueError("Upload filename is required")

    name = PurePath(PureWindowsPath(filename).name).name.strip()
    if name in {"", ".", ".."}:
        raise ValueError("Upload filename is invalid")
    return name


def validate_pdf_upload(filename: str | None, content_type: str | None) -> str:
    name = safe_upload_filename(filename)
    if Path(name).suffix.lower() != PDF_SUFFIX:
        raise ValueError("Only PDF uploads are supported")
    if (content_type or "").split(";")[0].strip().lower() != PDF_CONTENT_TYPE:
        raise ValueError("Upload content type must be application/pdf")
    return name


def validate_pdf_magic(file_obj) -> None:
    """Validate that a seekable file-like object starts with a PDF signature."""
    try:
        original_position = file_obj.tell()
        file_obj.seek(0)
        header = file_obj.read(len(PDF_MAGIC))
        file_obj.seek(original_position)
    except Exception as exc:
        raise ValueError("Upload file stream must be readable and seekable") from exc

    if header != PDF_MAGIC:
        raise ValueError("Upload file content must start with a PDF signature")


def safe_upload_path(upload_dir: str | Path, filename: str | None, content_type: str | None = None) -> Path:
    if content_type is None:
        name = safe_upload_filename(filename)
    else:
        name = validate_pdf_upload(filename, content_type)
    return Path(upload_dir) / name
