import pytest

from services.ingestion.filenames import safe_upload_filename, safe_upload_path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("manual.pdf", "manual.pdf"),
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
