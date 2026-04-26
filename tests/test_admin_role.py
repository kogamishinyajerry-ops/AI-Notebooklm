"""V4.2-T3 tests: admin role resolution and AuthPrincipal extension.

Step 1 (this file, cases T1-T4): AuthPrincipal backward compat, env parsing,
empty env fallback, malformed env handling.

Later steps will append T5-T10 (require_admin dependency) here and
test_admin_api.py cases (route-level).
"""

from __future__ import annotations

import logging

import pytest

from core.governance.admin import (
    ADMIN_PRINCIPALS_ENV,
    get_admin_principal_ids,
    resolve_admin,
)
from core.security.auth import AuthPrincipal


# ---------------------------------------------------------------------------
# T1: AuthPrincipal backward compatibility
# ---------------------------------------------------------------------------


def test_auth_principal_backward_compat():
    """T1: 只传 principal_id 构造时 is_admin 默认为 False（不影响 T1/T2 已有代码路径）。"""
    p = AuthPrincipal(principal_id="alice")
    assert p.principal_id == "alice"
    assert p.is_admin is False


def test_auth_principal_with_admin_flag_true():
    """T1b: 显式 is_admin=True 构造。"""
    p = AuthPrincipal(principal_id="root", is_admin=True)
    assert p.principal_id == "root"
    assert p.is_admin is True


def test_auth_principal_frozen_dataclass():
    """T1c: AuthPrincipal 仍是 frozen dataclass，不可变（防止运行时被误改提权）。"""
    p = AuthPrincipal(principal_id="alice")
    with pytest.raises((AttributeError, TypeError)):
        p.is_admin = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# T2: resolve_admin parses env allowlist
# ---------------------------------------------------------------------------


def test_resolve_admin_parses_multiple_principals(monkeypatch):
    """T2: 逗号分隔多个 principal 全部被识别为 admin。"""
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice,bob,charlie")
    assert resolve_admin("alice") is True
    assert resolve_admin("bob") is True
    assert resolve_admin("charlie") is True
    assert resolve_admin("dave") is False


def test_resolve_admin_strips_surrounding_whitespace(monkeypatch):
    """T2b: 分隔符周围的空格被 strip，值本身保留。"""
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "  alice ,  bob  , charlie  ")
    assert resolve_admin("alice") is True
    assert resolve_admin("bob") is True
    assert resolve_admin("charlie") is True


def test_get_admin_principal_ids_returns_set(monkeypatch):
    """T2c: 低层 helper 返回 set，供路由层缓存或批量 lookup。"""
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice,bob")
    ids = get_admin_principal_ids()
    assert isinstance(ids, set)
    assert ids == {"alice", "bob"}


def test_get_admin_principal_ids_deduplicates(monkeypatch):
    """T2d: 重复 principal 只算一次。"""
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice,alice,bob,alice")
    assert get_admin_principal_ids() == {"alice", "bob"}


# ---------------------------------------------------------------------------
# T3: empty / unset env => no admins
# ---------------------------------------------------------------------------


def test_resolve_admin_empty_env(monkeypatch):
    """T3: 空字符串 env → 所有 principal is_admin=False。"""
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "")
    assert resolve_admin("alice") is False
    assert resolve_admin("anyone") is False
    assert get_admin_principal_ids() == set()


def test_resolve_admin_unset_env(monkeypatch):
    """T3b: 未设置 env → 所有 principal is_admin=False。"""
    monkeypatch.delenv(ADMIN_PRINCIPALS_ENV, raising=False)
    assert resolve_admin("alice") is False
    assert get_admin_principal_ids() == set()


def test_resolve_admin_empty_principal_id(monkeypatch):
    """T3c: principal_id 为空字符串/None-like → 永远 False（防御空 key 被配为 admin）。"""
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice")
    assert resolve_admin("") is False


def test_resolve_admin_whitespace_only_env(monkeypatch):
    """T3d: env 只含空白字符 → 视同空。"""
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "   \t  ")
    assert get_admin_principal_ids() == set()
    assert resolve_admin("alice") is False


# ---------------------------------------------------------------------------
# T4: malformed env => warn + skip, never crash
# ---------------------------------------------------------------------------


def test_resolve_admin_skips_whitespace_inside_entries(monkeypatch, caplog):
    """T4: entry 内部含空格被跳过并 warn；不影响合法项。"""
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice,bob bob,charlie")
    with caplog.at_level(logging.WARNING, logger="comac.governance.admin"):
        ids = get_admin_principal_ids()
    assert "alice" in ids
    assert "charlie" in ids
    assert "bob bob" not in ids
    assert any(
        "whitespace" in rec.message.lower() or "invalid" in rec.message.lower()
        for rec in caplog.records
    ), f"expected warn for malformed entry; got {[r.message for r in caplog.records]}"


def test_resolve_admin_tolerates_trailing_commas(monkeypatch):
    """T4b: 尾部/中间空项被容忍，不报错。"""
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice,,bob,")
    ids = get_admin_principal_ids()
    assert ids == {"alice", "bob"}


def test_resolve_admin_tolerates_only_commas(monkeypatch):
    """T4c: env 全是分隔符 → 视同空。"""
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, ",,,,")
    assert get_admin_principal_ids() == set()


def test_resolve_admin_does_not_cache_across_env_changes(monkeypatch):
    """T4d: env 在测试之间变化时不串味（无全局缓存副作用）。"""
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice")
    assert resolve_admin("alice") is True
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "bob")
    assert resolve_admin("alice") is False
    assert resolve_admin("bob") is True


# ---------------------------------------------------------------------------
# T5-T7: require_admin FastAPI dependency (Step 2)
# ---------------------------------------------------------------------------


from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core.governance.admin import require_admin  # noqa: E402
from core.security.auth import get_current_principal  # noqa: E402


@pytest.fixture
def admin_app():
    """Minimal FastAPI app exposing one admin-only endpoint for dep testing."""
    app = FastAPI()

    @app.get("/admin-only")
    def admin_only(principal: AuthPrincipal = Depends(require_admin)):  # type: ignore[assignment]
        return {
            "principal_id": principal.principal_id,
            "is_admin": principal.is_admin,
        }

    # Also expose a non-admin endpoint using just get_current_principal,
    # to test is_admin enrichment independently of require_admin.
    @app.get("/who-am-i")
    def who_am_i(request: Request):
        p = get_current_principal(request)
        if p is None:
            return {"auth": "disabled"}
        return {"principal_id": p.principal_id, "is_admin": p.is_admin}

    return app


def test_require_admin_grants_admin_principal(admin_app, monkeypatch):
    """T5: admin principal 通过 require_admin，返回 is_admin=True。"""
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice,bob:key-bob")
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice")
    client = TestClient(admin_app)
    r = client.get("/admin-only", headers={"x-api-key": "key-alice"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"principal_id": "alice", "is_admin": True}


def test_get_current_principal_enriches_admin_flag(admin_app, monkeypatch):
    """T5b: get_current_principal 独立也会根据 env 填 is_admin。"""
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice,bob:key-bob")
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice")
    client = TestClient(admin_app)
    r1 = client.get("/who-am-i", headers={"x-api-key": "key-alice"})
    assert r1.json() == {"principal_id": "alice", "is_admin": True}
    r2 = client.get("/who-am-i", headers={"x-api-key": "key-bob"})
    assert r2.json() == {"principal_id": "bob", "is_admin": False}


def test_require_admin_forbids_non_admin(admin_app, monkeypatch):
    """T6: 认证成功但非 admin → 403。"""
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice,bob:key-bob")
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice")
    client = TestClient(admin_app)
    r = client.get("/admin-only", headers={"x-api-key": "key-bob"})
    assert r.status_code == 403
    assert "admin" in r.json()["detail"].lower()


def test_require_admin_rejects_missing_key(admin_app, monkeypatch):
    """T7a: 无 API key → 401。"""
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice")
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice")
    client = TestClient(admin_app)
    r = client.get("/admin-only")
    assert r.status_code == 401


def test_require_admin_rejects_invalid_key(admin_app, monkeypatch):
    """T7b: 非法 key → 401。"""
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice")
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice")
    client = TestClient(admin_app)
    r = client.get("/admin-only", headers={"x-api-key": "bogus"})
    assert r.status_code == 401


def test_require_admin_auth_disabled_returns_503(admin_app, monkeypatch):
    """T7c: 未开启 auth（NOTEBOOKLM_API_KEYS 未设）→ 503（admin 无意义）。"""
    monkeypatch.delenv("NOTEBOOKLM_API_KEYS", raising=False)
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice")
    client = TestClient(admin_app)
    r = client.get("/admin-only", headers={"x-api-key": "whatever"})
    assert r.status_code == 503
    assert "NOTEBOOKLM_API_KEYS" in r.json()["detail"]


def test_require_admin_allowlist_unset_returns_503(admin_app, monkeypatch):
    """T7d: admin 白名单未设 → 503（防止无法挽救的锁定）。"""
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice")
    monkeypatch.delenv(ADMIN_PRINCIPALS_ENV, raising=False)
    client = TestClient(admin_app)
    r = client.get("/admin-only", headers={"x-api-key": "key-alice"})
    assert r.status_code == 503
    assert "NOTEBOOKLM_ADMIN_PRINCIPALS" in r.json()["detail"]


def test_require_admin_allowlist_blank_returns_503(admin_app, monkeypatch):
    """T7e: admin env 为空白字符串 → 等价于未设。"""
    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice")
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "   ")
    client = TestClient(admin_app)
    r = client.get("/admin-only", headers={"x-api-key": "key-alice"})
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# W-V43-15 (PR54-1): admin path predicate single-source.
# ---------------------------------------------------------------------------


from unittest.mock import MagicMock  # noqa: E402

from core.governance.admin import (  # noqa: E402
    ADMIN_PATH_PREFIX,
    is_admin_path,
)


def _request_with_path(path: str) -> Request:
    req = MagicMock(spec=Request)
    req.url = MagicMock()
    req.url.path = path
    return req


def test_is_admin_path_matches_admin_prefix():
    assert is_admin_path(_request_with_path(f"{ADMIN_PATH_PREFIX}status")) is True
    assert is_admin_path(_request_with_path(f"{ADMIN_PATH_PREFIX}rate-limits/stats")) is True


def test_is_admin_path_rejects_user_facing_routes():
    """Defense-in-depth: chat/notebook routes must never satisfy the predicate."""
    assert is_admin_path(_request_with_path("/api/v1/chat")) is False
    assert is_admin_path(_request_with_path("/api/v1/notebooks/abc/sources")) is False
    # A path that *contains* but does not start with the admin prefix must
    # NOT be treated as admin (e.g. user-controlled identifiers).
    assert is_admin_path(_request_with_path("/api/v1/chat/api/v1/admin/")) is False


def test_require_admin_marks_bypass_via_path_predicate(monkeypatch):
    """PR54-1 invariant: require_admin must delegate the bypass decision to
    is_admin_path(request) rather than hard-coding True. We verify the call
    by patching mark_admin_request (the contextvar mutation itself cannot be
    asserted through TestClient because FastAPI runs sync deps in a
    threadpool that does not propagate context mutations to the async
    handler — see tests/test_rate_limit.py for the async-middleware
    pattern that does propagate)."""
    from unittest.mock import patch

    from core.governance import admin as admin_module
    from core.security.auth import AuthPrincipal as RealAuthPrincipal

    monkeypatch.setenv("NOTEBOOKLM_API_KEYS", "alice:key-alice")
    monkeypatch.setenv(ADMIN_PRINCIPALS_ENV, "alice")

    fake_principal = RealAuthPrincipal(principal_id="alice", is_admin=True)

    def call_with_path(path: str) -> bool:
        req = MagicMock(spec=Request)
        req.url = MagicMock()
        req.url.path = path
        req.app = MagicMock()
        req.app.state = MagicMock()
        req.app.state.audit_logger = None
        req.method = "GET"
        req.query_params = {}
        with patch(
            "core.security.auth.get_current_principal",
            return_value=fake_principal,
        ), patch(
            "core.governance.rate_limit.mark_admin_request"
        ) as mock_mark:
            admin_module.require_admin(req)
            assert mock_mark.call_count == 1
            return mock_mark.call_args.args[0]

    # Admin path → bypass enabled.
    assert call_with_path(f"{ADMIN_PATH_PREFIX}status") is True
    # Non-admin path with admin principal (mis-wiring or future reuse) →
    # bypass MUST stay False because the path predicate is the SSOT.
    assert call_with_path("/api/v1/chat") is False
