import pytest
from io import BytesIO

from services.ingestion.filenames import (
    safe_upload_filename,
    safe_upload_path,
    validate_pdf_magic,
    validate_pdf_upload,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("manual.pdf", "manual.pdf"),
        (" manual.pdf ", "manual.pdf"),
        ("../manual.pdf", "manual.pdf"),
        ("nested/path/manual.pdf", "manual.pdf"),
        (r"..\windows\manual.pdf", "manual.pdf"),
    ],
)
def test_safe_upload_filename_returns_basename(raw, expected):
    assert safe_upload_filename(raw) == expected


@pytest.mark.parametrize("raw", ["", None, ".", ".."])
def test_safe_upload_filename_rejects_invalid_names(raw):
    with pytest.raises(ValueError):
        safe_upload_filename(raw)


def test_safe_upload_path_stays_under_upload_dir(tmp_path):
    path = safe_upload_path(tmp_path, "../manual.pdf")

    assert path == tmp_path / "manual.pdf"


@pytest.mark.parametrize(
    ("raw", "content_type", "expected"),
    [
        ("manual.pdf", "application/pdf", "manual.pdf"),
        ("manual.PDF", "application/pdf; charset=binary", "manual.PDF"),
        ("../manual.pdf", "application/pdf", "manual.pdf"),
    ],
)
def test_validate_pdf_upload_accepts_pdf_basename(raw, content_type, expected):
    assert validate_pdf_upload(raw, content_type) == expected


@pytest.mark.parametrize(
    ("raw", "content_type"),
    [
        ("manual.txt", "application/pdf"),
        ("manual.pdf", "text/plain"),
        ("manual.pdf", None),
    ],
)
def test_validate_pdf_upload_rejects_non_pdf_inputs(raw, content_type):
    with pytest.raises(ValueError):
        validate_pdf_upload(raw, content_type)


def test_safe_upload_path_validates_pdf_when_content_type_is_provided(tmp_path):
    path = safe_upload_path(tmp_path, "../manual.pdf", "application/pdf")

    assert path == tmp_path / "manual.pdf"


def test_validate_pdf_magic_accepts_pdf_and_restores_position():
    file_obj = BytesIO(b"%PDF-1.7\ncontent")
    file_obj.seek(5)

    validate_pdf_magic(file_obj)

    assert file_obj.tell() == 5


@pytest.mark.parametrize("payload", [b"", b"not-pdf", b" %PDF"])
def test_validate_pdf_magic_rejects_non_pdf_content(payload):
    with pytest.raises(ValueError):
        validate_pdf_magic(BytesIO(payload))
