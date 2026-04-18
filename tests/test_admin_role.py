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
