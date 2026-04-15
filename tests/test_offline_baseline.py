from pathlib import Path

from core.retrieval.vector_store import build_chroma_settings


def test_chroma_settings_disable_telemetry():
    settings = build_chroma_settings("data/vector_db")

    assert settings.anonymized_telemetry is False
    assert settings.allow_reset is False


def test_frontend_bundle_has_no_public_cdn():
    html = Path("apps/web/static/index.html").read_text(encoding="utf-8")

    assert "cdn.jsdelivr.net" not in html
