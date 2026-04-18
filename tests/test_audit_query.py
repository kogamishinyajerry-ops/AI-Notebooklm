"""V4.2-T3 Step 3: AuditStore.query_events — cursor-paginated read API.

Additive extension of AuditStore (append-only contract preserved). The admin
dashboard needs to list recent audit events with filters without loading the
whole table. Design:

- order: ts_utc DESC, event_id DESC (stable tiebreaker within same ts)
- cursor: opaque base64(JSON{"ts": ..., "id": ...}) — NOT a row offset
- limit: default 50, max 200 (clamped)
- filters: event, principal_id, outcome, from_ts, to_ts (all optional, AND)
- returns QueryResult(items: list[AuditRecord], next_cursor: str|None)
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from core.governance.audit_store import AuditRecord, AuditStore


def _rec(
    event_id: str,
    ts_utc: str,
    *,
    event: str = "notebook.create",
    outcome: str = "success",
    principal_id: str = "alice",
) -> AuditRecord:
    return AuditRecord(
        event_id=event_id,
        ts_utc=ts_utc,
        event=event,
        outcome=outcome,
        actor_type="user",
        principal_id=principal_id,
        request_id=f"req-{event_id}",
        remote_addr="127.0.0.1",
        resource_type="notebook",
        resource_id=f"nb-{event_id}",
        parent_resource_id="",
        http_status=200,
        error_code="",
        payload_json="{}",
    )


@pytest.fixture
def store(tmp_path: Path) -> AuditStore:
    return AuditStore(db_path=tmp_path / "audit.db")


def _seed(store: AuditStore, n: int, *, principal: str = "alice", event: str = "notebook.create") -> None:
    for i in range(n):
        # ts_utc deliberately monotonically increasing per index — last-inserted is newest.
        ts = f"2026-04-18T10:00:{i:02d}Z"
        store.append(_rec(f"e{i:03d}", ts, event=event, principal_id=principal))


# ---------------------------------------------------------------------------
# Q1: basic DESC ordering + default limit
# ---------------------------------------------------------------------------


def test_query_events_returns_desc_by_ts(store):
    _seed(store, 5)
    result = store.query_events()
    ids = [r.event_id for r in result.items]
    assert ids == ["e004", "e003", "e002", "e001", "e000"]


def test_query_events_default_limit_is_50(store):
    _seed(store, 75)
    result = store.query_events()
    assert len(result.items) == 50
    assert result.next_cursor is not None


def test_query_events_respects_explicit_limit(store):
    _seed(store, 30)
    result = store.query_events(limit=10)
    assert len(result.items) == 10
    assert result.next_cursor is not None


def test_query_events_empty_db_returns_empty(store):
    result = store.query_events()
    assert result.items == []
    assert result.next_cursor is None


def test_query_events_limit_clamped_to_200(store):
    _seed(store, 10)
    # oversized limit must not raise; clamped silently to 200
    result = store.query_events(limit=5000)
    assert len(result.items) == 10
    assert result.next_cursor is None


def test_query_events_rejects_nonpositive_limit(store):
    _seed(store, 3)
    with pytest.raises(ValueError):
        store.query_events(limit=0)
    with pytest.raises(ValueError):
        store.query_events(limit=-1)


# ---------------------------------------------------------------------------
# Q2: cursor-based pagination
# ---------------------------------------------------------------------------


def test_query_events_cursor_walks_full_set(store):
    _seed(store, 12)
    page1 = store.query_events(limit=5)
    assert [r.event_id for r in page1.items] == ["e011", "e010", "e009", "e008", "e007"]
    assert page1.next_cursor is not None

    page2 = store.query_events(limit=5, cursor=page1.next_cursor)
    assert [r.event_id for r in page2.items] == ["e006", "e005", "e004", "e003", "e002"]
    assert page2.next_cursor is not None

    page3 = store.query_events(limit=5, cursor=page2.next_cursor)
    assert [r.event_id for r in page3.items] == ["e001", "e000"]
    assert page3.next_cursor is None


def test_query_events_cursor_no_overlap_no_gap(store):
    _seed(store, 20)
    seen = []
    cursor = None
    for _ in range(10):
        page = store.query_events(limit=3, cursor=cursor)
        seen.extend(r.event_id for r in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert len(seen) == 20
    assert len(set(seen)) == 20  # no duplicates across pages


def test_query_events_cursor_stable_when_same_ts(store):
    # Two events with identical ts_utc — cursor must break tie by event_id DESC.
    ts = "2026-04-18T10:00:00Z"
    store.append(_rec("eA", ts))
    store.append(_rec("eB", ts))
    store.append(_rec("eC", ts))

    page1 = store.query_events(limit=2)
    ids_p1 = [r.event_id for r in page1.items]
    assert ids_p1 == ["eC", "eB"]

    page2 = store.query_events(limit=2, cursor=page1.next_cursor)
    ids_p2 = [r.event_id for r in page2.items]
    assert ids_p2 == ["eA"]
    assert page2.next_cursor is None


def test_query_events_malformed_cursor_raises(store):
    _seed(store, 3)
    with pytest.raises(ValueError):
        store.query_events(cursor="not-base64!!")
    with pytest.raises(ValueError):
        store.query_events(cursor=base64.urlsafe_b64encode(b"not json").decode())
    with pytest.raises(ValueError):
        store.query_events(
            cursor=base64.urlsafe_b64encode(json.dumps({"wrong": "shape"}).encode()).decode()
        )


# ---------------------------------------------------------------------------
# Q3: filters
# ---------------------------------------------------------------------------


def test_query_events_filter_by_event(store):
    store.append(_rec("e1", "2026-04-18T10:00:00Z", event="notebook.create"))
    store.append(_rec("e2", "2026-04-18T10:00:01Z", event="source.upload"))
    store.append(_rec("e3", "2026-04-18T10:00:02Z", event="notebook.create"))

    result = store.query_events(event="notebook.create")
    assert [r.event_id for r in result.items] == ["e3", "e1"]


def test_query_events_filter_by_principal(store):
    store.append(_rec("e1", "2026-04-18T10:00:00Z", principal_id="alice"))
    store.append(_rec("e2", "2026-04-18T10:00:01Z", principal_id="bob"))
    store.append(_rec("e3", "2026-04-18T10:00:02Z", principal_id="alice"))

    result = store.query_events(principal_id="alice")
    assert [r.event_id for r in result.items] == ["e3", "e1"]


def test_query_events_filter_by_outcome(store):
    store.append(_rec("e1", "2026-04-18T10:00:00Z", outcome="success"))
    store.append(_rec("e2", "2026-04-18T10:00:01Z", outcome="failure"))
    store.append(_rec("e3", "2026-04-18T10:00:02Z", outcome="failure"))

    result = store.query_events(outcome="failure")
    assert [r.event_id for r in result.items] == ["e3", "e2"]


def test_query_events_filter_by_time_range(store):
    store.append(_rec("e1", "2026-04-18T09:59:59Z"))
    store.append(_rec("e2", "2026-04-18T10:00:30Z"))
    store.append(_rec("e3", "2026-04-18T10:01:00Z"))
    store.append(_rec("e4", "2026-04-18T10:05:00Z"))

    result = store.query_events(
        from_ts="2026-04-18T10:00:00Z",
        to_ts="2026-04-18T10:02:00Z",
    )
    assert [r.event_id for r in result.items] == ["e3", "e2"]


def test_query_events_combined_filters(store):
    store.append(_rec("e1", "2026-04-18T10:00:00Z", principal_id="alice", event="notebook.create"))
    store.append(_rec("e2", "2026-04-18T10:00:01Z", principal_id="alice", event="source.upload"))
    store.append(_rec("e3", "2026-04-18T10:00:02Z", principal_id="bob", event="notebook.create"))

    result = store.query_events(principal_id="alice", event="notebook.create")
    assert [r.event_id for r in result.items] == ["e1"]


def test_query_events_filters_with_pagination(store):
    for i in range(10):
        store.append(_rec(f"a{i:02d}", f"2026-04-18T10:00:{i:02d}Z", principal_id="alice"))
        store.append(_rec(f"b{i:02d}", f"2026-04-18T10:00:{i:02d}Z", principal_id="bob"))

    page1 = store.query_events(principal_id="alice", limit=4)
    assert [r.event_id for r in page1.items] == ["a09", "a08", "a07", "a06"]
    page2 = store.query_events(principal_id="alice", limit=4, cursor=page1.next_cursor)
    assert [r.event_id for r in page2.items] == ["a05", "a04", "a03", "a02"]
    page3 = store.query_events(principal_id="alice", limit=4, cursor=page2.next_cursor)
    assert [r.event_id for r in page3.items] == ["a01", "a00"]
    assert page3.next_cursor is None


# ---------------------------------------------------------------------------
# Q4: append-only contract preserved
# ---------------------------------------------------------------------------


def test_query_does_not_mutate_table(store):
    _seed(store, 5)
    for _ in range(3):
        store.query_events(limit=2)
    # After many queries, append still works and total count is intact.
    ids_before = [r.event_id for r in store.query_events(limit=100).items]
    assert sorted(ids_before) == [f"e00{i}" for i in range(5)]
    store.append(_rec("e005", "2026-04-18T10:00:05Z"))
    ids_after = [r.event_id for r in store.query_events(limit=100).items]
    assert sorted(ids_after) == [f"e00{i}" for i in range(6)]
