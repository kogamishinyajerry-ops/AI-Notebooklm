# V4.2-T3 冻结实施包 — Admin Role & Dashboard

**Status**: DRAFT — awaiting project owner cold-read
**Author**: Claude Code 20x MAX (self-planned, per V4.2-T3 handoff)
**Date**: 2026-04-18
**Prereq**: PR #41 (V4.2-T5 FK enforcement) merged to main
**Branch**: `feat/v4-2-t3-admin-dashboard` (not yet created)
**Base**: `main` @ <post-#41-merge>

---

## 1. Goal（一句话）

引入 admin role 概念，提供只读 dashboard API（audit/quota 查询）+ 最小 vanilla HTML 面板，并让 admin bypass quota（rate-limit + daily upload + notebook cap）。解除 T1 的 `test_admin_role_bypass_quota` skipif。

## 2. Frozen Decisions

| # | 决策 | 理由 |
|---|------|------|
| FD-1 | Admin 识别来源：**env allowlist 优先**（`NOTEBOOKLM_ADMIN_PRINCIPALS="id1,id2"`）；不引入 header claim / JWT | C1 零新依赖；与 T1 `NOTEBOOKLM_API_KEYS` 同风格；进程启动时读取，不支持热更新（admin 变更需重启，可审计） |
| FD-2 | `AuthPrincipal` 扩展为 `AuthPrincipal(principal_id, is_admin: bool = False)` | 非 breaking（新字段默认 False）；所有现存测试通过 |
| FD-3 | 新建 `core/governance/admin.py` 模块，提供 `resolve_admin(principal_id)`、`require_admin` FastAPI dependency | 与 auth/audit/quota 正交，避免把逻辑塞进已冻结文件 |
| FD-4 | Admin API 路由前缀 `/api/v1/admin/*`，与 T2 禁止公开暴露的 `/audit/*` 严格区分 | admin 路由受 `require_admin` 守护，非 admin 返回 403（不是 404，便于审计） |
| FD-5 | Dashboard：**纯 JSON API + vanilla JS 单文件 HTML**（挂 `/admin/ui/`）；无 HTMX、无 React | C1 零新依赖；HTML ≤ 250 行，fetch 调用 `/api/v1/admin/*` |
| FD-6 | Quota bypass：在 `DailyUploadQuota.check_and_record` 和 `NotebookCountCap.check` 内加 `is_admin` 短路（调用方传入 bool） | 最小侵入；bypass 仍写 audit event（`outcome="admin_bypass"`），不静默 |
| FD-7 | Rate-limit bypass：通过 `limiter.key_func` 内的 admin 检查返回特殊 key + `limiter.exempt_when`，或使用 slowapi `exempt_when` 回调 | 具体实现方式见 Step 3；TDD 先写测试再定 |
| FD-8 | Admin 操作强制 audit：所有 `/api/v1/admin/*` 请求通过 middleware 或 route dependency 记录一条 `admin.access` event（新增 AuditEvent 枚举值） | 满足 C3 审计完整性；T2 哨兵测试需增补用例 |
| FD-9 | 不引入角色层级（super-admin / viewer-admin）；is_admin 二值化 | 避免超范围；V4.3+ 再分级 |
| FD-10 | Admin 路由**不 bypass auth**（仍需有效 API key），只 bypass quota | 防止 env 配置错误导致的无认证访问；admin = "有 key + 在 allowlist" 双重条件 |

## 3. File Plan

### 新增（5）

| 文件 | 用途 | 预计 LOC |
|------|------|----------|
| `core/governance/admin.py` | admin role 解析 + `require_admin` dependency | 80 |
| `apps/api/admin_routes.py` | FastAPI APIRouter，`/api/v1/admin/*` 端点 | 180 |
| `apps/api/static/admin/index.html` | vanilla JS dashboard（audit + quota 两个 tab） | 220 |
| `tests/test_admin_role.py` | admin 识别、principal 扩展、bypass 单元测试 | 220 |
| `tests/test_admin_api.py` | `/api/v1/admin/*` 端到端（auth/403/bypass/audit） | 260 |

### 追加（禁改文件扩展，须在 PR body 列明）

| 文件 | 扩展内容 | 保证 |
|------|----------|------|
| `core/security/auth.py` | `AuthPrincipal` 加 `is_admin: bool = False` 字段；`get_current_principal` 调用 `admin.resolve_admin` 填充 | 不改 `API_KEYS_ENV` 语义；T1 所有测试绿 |
| `core/governance/audit_store.py` | 新增 `query_events(...)` 方法（分页 + filter by event/principal/time） | 不改 `append()` / 不改 schema |
| `core/governance/audit_events.py` | 新增枚举值 `ADMIN_ACCESS = "admin.access"` | T2 redaction 白名单同步更新 |
| `core/governance/quota_store.py` | `DailyUploadQuota.check_and_record` / `NotebookCountCap.check` 支持 `is_admin=False` 入参；新增 `snapshot_all_principals()` 只读方法 | 不改既有默认行为 |
| `core/governance/rate_limit.py` | `limiter.exempt_when` 回调基于 `request.state.principal.is_admin` | 不改 CHAT_RATE_ENV / 不改 429 响应格式 |
| `apps/api/main.py` | 挂载 `admin_routes.router`；挂 static `/admin/ui/`；quota check 调用传入 `is_admin` | 不改现有业务路由 |
| `tests/test_rate_limit.py` | 移除 `test_admin_role_bypass_quota` 的 `skipif(True)` | 变成真实断言 |

### 禁改（明确不动）

- `core/governance/audit_logger.py`（T2 核心写入链，仅 event 枚举扩展已覆盖）
- `core/storage/migrations/v4_2_t5_fk_enforcement.py`（T5 迁移，只读依赖）
- `tests/test_audit_log.py` / `test_fk_enforcement.py` / `test_storage_concurrency.py` / `test_sqlite_migration.py` / `test_retrieval_quality_regression.py`（哨兵，仅新增用例不删改断言）
- `core/governance/gateway.py`（C2 citation 管线）

## 4. API Contract

### Routes (all require `X-API-Key` + admin allowlist)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/admin/audit/events` | 分页查询审计事件，支持 `?event=&principal_id=&since=&until=&limit=&cursor=` |
| GET | `/api/v1/admin/audit/events/{event_id}` | 单条事件详情（含 payload_json） |
| GET | `/api/v1/admin/quota/usage` | 所有 principal 的 daily_upload + notebook_count 快照 |
| GET | `/api/v1/admin/quota/usage/{principal_id}` | 单 principal 当前配额状态 |
| GET | `/api/v1/admin/health` | admin 路由心跳（返回 `{status, admin_principal_count, api_version}`） |
| GET | `/admin/ui/` | 静态 HTML 面板 |

- 非 admin（无 key 或 key 不在 allowlist）：401 / 403
- Admin 未配置（env 为空）：所有路由返回 503 `{detail:"Admin not configured"}`
- 所有成功请求写 `audit.admin_access` event

### Response schemas (stable, not to change in T3)

```json
// GET /api/v1/admin/audit/events
{
  "events": [ { "event_id":"...", "ts_utc":"...", "event":"...", "principal_id":"...", ... } ],
  "next_cursor": "...",
  "total_returned": 50
}

// GET /api/v1/admin/quota/usage
{
  "principals": [
    { "principal_id":"alice", "daily_upload_bytes":12345, "daily_upload_limit":524288000,
      "notebook_count":3, "notebook_cap":50, "is_admin": false }
  ]
}
```

## 5. Test Plan

### 新增测试（最少用例数 = 20，目标 full suite +25~30 passed）

`tests/test_admin_role.py`（~10 cases）
- T1: AuthPrincipal 向后兼容（无 is_admin 参数）
- T2: `resolve_admin` 从 env 解析多个 principal
- T3: env 空 → 所有 principal is_admin=False
- T4: env 含非法格式 → warn + fallback（不 crash）
- T5: `require_admin` 对 admin principal 通过
- T6: `require_admin` 对非 admin 返回 403
- T7: `require_admin` 对未认证返回 401
- T8: `DailyUploadQuota.check_and_record(is_admin=True)` 不触发 QuotaExceededError
- T9: `NotebookCountCap.check(is_admin=True)` 返回 cap 不 block
- T10: admin bypass 仍写 audit event（`outcome="admin_bypass"`）

`tests/test_admin_api.py`（~10 cases）
- T1: GET `/api/v1/admin/health` 未认证 → 401
- T2: 非 admin → 403
- T3: admin → 200 + 预期 schema
- T4: `/admin/audit/events` 分页 + filter
- T5: `/admin/audit/events/{id}` 单条查询
- T6: `/admin/audit/events/{id}` 不存在 → 404
- T7: `/admin/quota/usage` 多 principal 聚合
- T8: `/admin/quota/usage/{principal_id}` 不存在 → 404
- T9: admin 请求写入 `admin.access` audit event
- T10: admin not configured → 503

`tests/test_rate_limit.py::test_admin_role_bypass_quota`（1 case，已预留）
- 移除 skipif，断言 admin 发起 31 次 chat 不触发 429

### 哨兵回归（must stay green）

| 测试文件 | 当前绿 | T3 后期望 |
|----------|--------|-----------|
| `test_audit_log.py` | 18 | 18+ |
| `test_rate_limit.py` | 17 skipped→1 实 | 18 |
| `test_fk_enforcement.py` | 15 | 15 |
| `test_storage_concurrency.py` | 6 | 6 |
| `test_sqlite_migration.py` | 11 | 11 |
| `test_retrieval_quality_regression.py` | 8 | 8 |

### 全量基线

- T3 前：290 passed, 1 skipped
- T3 后：~315 passed, 0 skipped（+20 新增 + 1 unskipped，其余持平）

## 6. Execution Order

| Step | 内容 | 测试 | 预计 LOC | 预计时间 |
|------|------|------|---------|----------|
| 1 | `AuthPrincipal.is_admin` 扩展 + `admin.resolve_admin` + env 解析 | test_admin_role T1-T4 | +60 | 30 min |
| 2 | `require_admin` dependency + admin module 完整 | test_admin_role T5-T7 | +40 | 20 min |
| 3 | `AuditStore.query_events` 实现（SQL + 分页） | 新增 audit_store 单测（追加 test_audit_log.py） | +70 | 45 min |
| 4 | `QuotaStore.snapshot_all_principals` + bypass 支持 | test_admin_role T8-T10 | +80 | 45 min |
| 5 | `limiter.exempt_when` + chat bypass | test_rate_limit::admin_role_bypass_quota | +30 | 30 min |
| 6 | `apps/api/admin_routes.py` + 挂载 | test_admin_api T1-T8 | +180 | 60 min |
| 7 | `audit.admin_access` event + middleware | test_admin_api T9-T10 | +40 | 30 min |
| 8 | Dashboard HTML + static mount | 手动冒烟（记录在 PR body） | +220 | 40 min |
| 9 | 文档：`docs/admin_role_and_dashboard.md` | — | +150 | 20 min |
| 10 | PR body + verification dump | — | — | 20 min |

**预计总工时**：5~6 小时（单 session 可完成）
**预计总 LOC**：新增 ~960，追加 ~130，合计 ~1090（低于 1500 LOC 拆分阈值）
**预计文件改动**：新增 5 + 追加 7 = 12（低于 20 文件阈值）

## 7. Stop Conditions（T3 特化）

除通用 8 条外：
- S9: 若 env allowlist 设计需要依赖 JWT/OAuth → 停下重新讨论（超出 C1）
- S10: 若 Dashboard 需要前端框架 → 停下（超出 C1）
- S11: 若 admin bypass 实现必须改 T1 rate_limit 核心语义（如改 limiter.key_func 返回 None 默认行为）→ 停下，考虑换方案
- S12: 若全量 pytest 新增红灯不是本次引入（T3 无关）→ 停下上报

## 8. Compliance Declaration（PR body 用）

- [x] **C1**：零新 Python 依赖（仅用已存在的 fastapi/slowapi/sqlite3/stdlib）；无外联；offline-safe
- [x] **C2**：citation XML 管线 / `gateway.py` / `test_retrieval_quality_regression.py` 零改动
- [x] **C3**：独立 feat 分支；PR 待 Opus 4.7 Gate Review；不自 approve

## 9. Known Risks / Open Questions

1. **R1**：slowapi `exempt_when` 在 `limiter.limit` decorator 上的支持需实测；若不行，fallback 方案是 admin 专属 key_func 返回 `f"admin-exempt:{id}"` + 配置超高 limit。→ Step 5 先写测试再定。
2. **R2**：`AuditStore.query_events` 分页使用 cursor-based（按 ts_utc DESC, event_id）还是 offset-based？倾向 cursor（可扩展、无漂移）。
3. **R3**：Dashboard HTML 的 CSP / XSS 防护——用 `textContent` 而非 `innerHTML`，不引入模板引擎，JSON 全部 fetch 不拼接。
4. **OQ-1**：admin 是否需要看到 chat 内容的审计？当前 T2 chat event payload 仅存 metadata（符合 redaction 白名单），admin 看不到原文。→ 不在 T3 scope。
5. **OQ-2**：admin bypass 是否需要频率上限（防滥用）？当前 FD-10 已要求 admin 必须先有 key，key 本身不可无限轮换；T3 不做额外限制。

## 10. Next Action（user 冷读后）

1. 如有修改意见 → 本地 markdown 调整
2. 如通过冷读 → 我推送 freeze pack 到 Notion（需要你指定目标子页 ID，或在控制塔底部新建 `V4.2 Phase / T3 Admin Role` 子页）
3. 确认 PR #41 已 merge → 拉 main → 开 `feat/v4-2-t3-admin-dashboard` → 开始 Step 1

---

## Appendix A: T3 与既有架构的接缝图

```
                   ┌─────────────────────────────┐
                   │ NOTEBOOKLM_ADMIN_PRINCIPALS │ (env)
                   └──────────────┬──────────────┘
                                  │
                                  ▼
   HTTP ──► get_current_principal ──► AuthPrincipal(id, is_admin=True|False)
                                  │
           ┌──────────────────────┼────────────────────────┐
           │                      │                        │
           ▼                      ▼                        ▼
   /api/v1/admin/*        /chat, /upload...         normal routes
   (require_admin)        is_admin passed to
                          quota/limiter
                                  │
                                  ▼
                    AuditLogger.emit(ADMIN_ACCESS) / bypass audit
```

## Appendix B: Non-goals (明确不做)

- 不做 admin UI 的 CRUD（增删 principal）——env-based 不可变
- 不做 role 层级 / 多 tenant
- 不做 login / session（仍是 API key）
- 不做 audit 事件的导出（CSV/JSON 下载）——可在 V4.3 按需
- 不做 realtime push / websocket
- 不做 quota 动态调整（env 外修改）
