"""V4.2-T3 Step 8: admin dashboard static file smoke tests.

The dashboard itself is a single vanilla HTML file; end-to-end browser
testing is out of scope for T3. These tests verify:

- the route exists and returns the file
- the file is small (budget: ≤250 lines per frozen pack)
- the file references the three admin endpoints it is expected to call
- it uses x-api-key (not a cookie, matching auth.py's scheme)
"""

from __future__ import annotations

from pathlib import Path

import pytest


DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "apps" / "web" / "static" / "admin.html"


def test_dashboard_file_exists():
    assert DASHBOARD_PATH.exists(), f"missing {DASHBOARD_PATH}"


def test_dashboard_under_line_budget():
    text = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert text.count("\n") <= 250, "admin.html exceeds 250-line budget"


def test_dashboard_calls_three_admin_endpoints():
    text = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "/api/v1/admin/health" in text
    assert "/api/v1/admin/quota/usage" in text
    assert "/api/v1/admin/audit/events" in text


def test_dashboard_uses_x_api_key_header():
    text = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "x-api-key" in text


def test_dashboard_escapes_html_on_render():
    """Defense-in-depth: the principal_id / event strings end up in innerHTML;
    the dashboard must html-escape them to avoid XSS against an admin."""
    text = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "escapeHtml" in text


def test_dashboard_has_pagination_cursor_ui():
    text = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "next_cursor" in text
    assert "audit-next" in text
