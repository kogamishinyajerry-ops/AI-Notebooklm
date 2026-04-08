# APLH Phase 2B 架构规划包

**Document ID:** APLH-ARCH-004
**Version:** 0.4.0-revised-R4
**Status:** PLANNING — Pending final re-review before implementation
**Authored by:** Phase 2B Planning Session (Opus 4.6)
**Revised by:** R1 (Opus 4.6) — closes 5 execution contract gaps; R2 (Opus 4.6) — closes 4 remaining gaps; R4 (Opus 4.6) — closes last handoff-contract gap (P2B-F5 full §12.2 7-heading gate + 4-site synchronization)
**Date:** 2026-04-04

---

## 1. 总体结论

### 1.1 当前是否允许开始 Phase 2B 规划

**是。** Phase 2A 已实施且通过独立审查确认。111 项测试全部通过。3 个新模型（MODE, TRANS, GUARD）、9 个 P0/P1 additive fields、3 个 reciprocal fields、11 个新 trace directions、predicate grammar 均已落地。2A schema 合同现已冻结。

**证据来源：**
- `docs/PHASE2A_IMPLEMENTATION_NOTES.md` — Status: Implementation Complete
- `.venv/bin/python -m pytest` — 111 passed
- `models/mode.py`, `models/transition.py`, `models/guard.py` — 已存在且含完整字段
- `models/trace.py` — 25 个 VALID_TRACE_DIRECTIONS（14 P0/P1 + 11 Phase 2A）

### 1.2 当前不允许假设什么

1. **formal `artifacts/` root 仍未 freeze-complete。** `.aplh/freeze_gate_status.yaml` 所有布尔值均为 `false`。
2. **demo set 不等于 formal baseline。** `minimal_demo_set` 仅含 P0/P1 类型（7 子目录，无 modes/transitions/guards）。
3. **Phase 2B 不等于 Phase 2 完成。** 2B 只建立静态验证层，不建执行引擎。
4. **不可修改 2A 冻结 schema。** MODE/TRANS/GUARD 模型字段、trace directions、predicate grammar 均为冻结输入。

---

## 2. Phase 2B 定义

### 2.1 目标

在 2A 冻结的 schema 合同基础上，建立 **静态逻辑验证与关系闭环层**：

1. 将 MODE / TRANS / GUARD 纳入 reverse-loop consistency enforcement
2. 构建 mode/transition 结构图（directed graph）
3. 实现 transition completeness、unreachable mode、dead-edge 基础分析
4. 实现 guard linkage / predicate structure 校验
5. 为 2C 的 demo-scale execution readiness 提供可信前置条件

**核心问题：** "能不能静态证明这批 mode/transition/guard artifacts 结构上自洽、追溯上闭环、足以进入 demo-scale execution 准备"

### 2.2 非目标（Out of Scope）

| 排除项 | 为什么排除 |
|---|---|
| Execution engine / state step | 2B 是静态验证，不是运行时执行 |
| Predicate evaluator / DSL interpreter | Phase 3+，§4.9 只做结构验证 |
| Demo artifact authoring | Phase 2C scope |
| Scenario executor / test vector runner | Phase 3+ |
| New UI / visual editor | Phase 3+ |
| `TRANS → FUNC` trace direction | §4.8 frozen: field-only, not in consistency scope |
| `TRANS → IFACE` trace direction | §4.6 frozen: field-only |
| Formal baseline population | 独立活动 |
| codegen / simulator / cert mapping | Phase 3+ |

### 2.3 为什么 2B 必须建立在 2A 冻结输入之上

- `_get_all_embedded_links()` 扩展依赖 2A 中声明的 9 个 additive fields 和 3 个 reciprocal fields 的 **确切字段名**
- mode graph 构建依赖 `TRANS.source_mode` / `TRANS.target_mode` / `TRANS.guard` 的 **确切语义**
- predicate structural checker 依赖 `AtomicPredicate` / `CompoundPredicate` 的 **确切 Pydantic schema**
- 如果 2B 回头改 2A 字段，所有 111 个现有测试以及已导出的 9 份 JSON schema 都会断裂

### 2.4 2B 与 2A、2C 的边界关系

```
Phase 2A (冻结)          Phase 2B (本轮规划)         Phase 2C (未来)
─────────────────       ─────────────────────       ──────────────────
schema + models    ──►  consistency extension  ──►  demo data authoring
trace extension    ──►  mode graph builder     ──►  demo-scale gate P2-F
additive fields    ──►  mode validator         ──►  T2 manual signoffs
reciprocal fields  ──►  coverage validator     ──►  integration tests
predicate grammar  ──►  CLI validate-modes     ──►  review signoff YAML
```

---

## 3. 模块树

```
aero_prop_logic_harness/
├── services/
│   ├── artifact_registry.py         # [EXISTING — NO CHANGE]
│   └── mode_graph.py                # [NEW — 2B CORE] 有向图构建
│
├── validators/
│   ├── consistency_validator.py     # [EXTEND — 2B CORE] reverse-loop 扩展
│   ├── mode_validator.py            # [NEW — 2B CORE] 结构完整性检查
│   ├── coverage_validator.py        # [NEW — 2B CORE] ABN 覆盖检查
│   ├── schema_validator.py          # [EXISTING — NO CHANGE]
│   └── trace_validator.py           # [EXISTING — NO CHANGE]
│
├── cli.py                           # [EXTEND — 2B] 新命令 validate-modes
│
├── models/                          # [2A 冻结 — 2B 不可修改]
└── loaders/                         # [2A 冻结 — 2B 不可修改]
```

### 模块职责与核心/非核心标注

| 模块 | 职责 | 核心等级 | Phase |
|---|---|---|---|
| `services/mode_graph.py` | 从 registry 构建 MODE 节点 + TRANS 边的有向图；提供只读拓扑查询（reachable_from, dead_transitions, unreachable_modes） | **2B 核心** | 2B-2 |
| `validators/consistency_validator.py` (扩展) | 在 `_get_all_embedded_links()` 追加 MODE/TRANS/GUARD + additive/reciprocal 字段提取；reverse-loop enforcement | **2B 核心** | 2B-1 |
| `validators/mode_validator.py` | 初始 mode 存在性、mode 可达性、transition 端点解析、guard 引用解析、trigger_signal IFACE 存在性检查、TRANS.actions FUNC 存在性检查、自环合理性 | **2B 核心** | 2B-3 |
| `validators/coverage_validator.py` | ABN→MODE 映射覆盖、degraded mode recovery/terminal 检查、emergency mode 可达性 | **2B 核心** | 2B-3 |
| `cli.py` (`validate-modes`) | 新 CLI 入口，运行 mode_validator + coverage_validator，接受 `--dir` 和 `--coverage` | **2B 核心** | 2B-3 |
| `reporters/mode_report.py` | DOT/text 导出 | 2C+ 再说 | 2D |
| Scenario executor | 执行 transition sequences | **不做** | 3+ |
| Predicate evaluator | 求值 guard predicates | **不做** | 3+ |

---

## 4. 2A → 2B 数据契约

### 4.1 2B 必须读取的字段

#### MODE 字段

| 字段 | 类型 | 2B 用途 | 进入 consistency scope? |
|---|---|---|---|
| `id` | str | 图节点 key | N/A |
| `mode_type` | str | coverage_validator 的 degraded/emergency 判定 | No |
| `is_initial` | bool | mode_validator 初始 mode 检查 | No |
| `parent_mode` | str | 层级分析（2B 仅检查引用解析） | No |
| `active_functions` | list[str] | reverse-loop: `(MODE, FUNC, activates)` 源侧 | **Yes** |
| `monitored_interfaces` | list[str] | reverse-loop: `(MODE, IFACE, monitors)` 源侧 | **Yes** |
| `related_requirements` | list[str] | reverse-loop: `(REQ, MODE, requires_mode)` 目标侧 | **Yes** |
| `related_abnormals` | list[str] | reverse-loop + coverage_validator | **Yes** |
| `incoming_transitions` | list[str] | reverse-loop: `(TRANS, MODE, enters)` 目标侧 §2.7 reciprocal | **Yes** |
| `outgoing_transitions` | list[str] | reverse-loop: `(TRANS, MODE, exits)` 目标侧 §2.7 reciprocal | **Yes** |

#### TRANS 字段

| 字段 | 类型 | 2B 用途 | 进入 consistency scope? |
|---|---|---|---|
| `source_mode` | str | 图构建 + reverse-loop: `(TRANS, MODE, exits)` 源侧 | **Yes** |
| `target_mode` | str | 图构建 + reverse-loop: `(TRANS, MODE, enters)` 源侧 | **Yes** |
| `guard` | str | guard 引用解析 + reverse-loop: `(TRANS, GUARD, guarded_by)` 源侧 | **Yes** |
| `trigger_signal` | str | mode_validator 结构解析（检查 IFACE ID 存在） | **No** (field-only §4.6) |
| `actions` | list[str] | mode_validator 结构解析（检查 FUNC ID 存在） | **No** (field-only §4.8) |
| `priority` | int | advisory: 同源 mode 优先级冲突标记 | No |
| `related_requirements` | list[str] | reverse-loop: `(REQ, TRANS, requires_transition)` 目标侧 | **Yes** |
| `related_abnormals` | list[str] | reverse-loop: `(ABN, TRANS, triggers_transition)` 目标侧 | **Yes** |

#### GUARD 字段

| 字段 | 类型 | 2B 用途 | 进入 consistency scope? |
|---|---|---|---|
| `predicate` | AtomicPredicate\|CompoundPredicate | predicate structural checker | No (已在 load 时验证) |
| `related_interfaces` | list[str] | reverse-loop: `(GUARD, IFACE, observes)` 源侧 | **Yes** |
| `related_requirements` | list[str] | reverse-loop: `(REQ, GUARD, defines_condition)` 目标侧 | **Yes** |
| `used_by_transitions` | list[str] | reverse-loop: `(TRANS, GUARD, guarded_by)` 目标侧 §2.7 reciprocal | **Yes** |

#### P0/P1 additive fields (2B 必须读取)

| 模型 | 新字段 | 进入 consistency scope? |
|---|---|---|
| Requirement | `linked_modes`, `linked_transitions`, `linked_guards` | **Yes** |
| Function | `related_modes`, `related_transitions` | `related_modes`: **Yes**; `related_transitions`: **No** (§4.8) |
| Interface | `related_modes`, `related_guards` | **Yes** |
| Abnormal | `related_modes`, `related_transitions` | **Yes** |

### 4.2 2B 明确忽略的字段

| 字段 | 为什么忽略 |
|---|---|
| `MODE.entry_conditions` / `MODE.exit_conditions` | Human summary, §4.7 明确标注 NOT machine-checkable |
| `GUARD.description` | Human summary, §4.7 R3 freeze |
| `GUARD.input_signals` | Informational convenience, 权威在 `predicate.signal_ref` |
| `TRANS.is_reversible` | Advisory; 不影响结构验证 |
| `TRANS.actions` (consistency 方面) | §4.8 frozen: field-only, NOT in consistency scope |
| `Function.related_transitions` (consistency 方面) | §4.8 frozen: 不被 `_get_all_embedded_links()` 提取 |

### 4.3 TRANS.actions / Function.related_transitions 为什么不进入 consistency scope

**根据 §4.8 冻结决定：** 这对字段代表"运行时行为绑定"而非"工程追溯关系"。它们由 `mode_validator.py` 做 **结构解析检查**（ID 是否存在），但不参与 `ConsistencyValidator._get_all_embedded_links()` 提取或 `_validate_trace_reverse_loop()` 验证。

### 4.4 predicate grammar 在 2B 的检查范围

2B **只做结构合法性检查**，不做更多：

| 检查 | 2B 是否做 | 实现位置 |
|---|---|---|
| `signal_ref` 格式匹配 IFACE-NNNN.signal_name | 已在 load 时由 Pydantic 完成 | predicate.py |
| `signal_ref` 引用的 IFACE + signal 真实存在 | **Yes** | mode_validator.py |
| `signal_ref` 覆盖与 `related_interfaces` 一致 | **Yes** | mode_validator.py |
| operator/threshold 类型一致 | 已在 load 时由 Pydantic 完成 | predicate.py |
| 两个 predicates 语义重叠检测 | **No** — T3 advisory, Phase 3+ | N/A |
| threshold 值与 REQ 一致 | **No** — 需要 domain judgment | N/A |

---

## 5. Reverse-loop consistency 扩展设计

### 5.1 当前 ConsistencyValidator 现状

当前 `_get_all_embedded_links()` (consistency_validator.py L44-62) 只处理 4 种 P0/P1 类型：Requirement, Function, Interface, Abnormal。对 Mode, Transition, Guard 返回空列表 — 意味着它们的 reverse-loop 完全未被执行。

### 5.2 扩展方案

在 `_get_all_embedded_links()` 中追加 3 个 `isinstance` 分支。需导入 `Mode`, `Transition`, `Guard`。

**Mode 分支提取：**
```python
elif isinstance(artifact, Mode):
    links.extend(artifact.active_functions)        # (MODE, FUNC, activates) 源侧
    links.extend(artifact.monitored_interfaces)    # (MODE, IFACE, monitors) 源侧
    links.extend(artifact.related_requirements)    # (REQ, MODE, requires_mode) 目标侧
    links.extend(artifact.related_abnormals)       # (ABN, MODE, triggers_mode) 目标侧
    links.extend(artifact.incoming_transitions)    # (TRANS, MODE, enters) 目标侧 §2.7
    links.extend(artifact.outgoing_transitions)    # (TRANS, MODE, exits) 目标侧 §2.7
```

**Transition 分支提取：**
```python
elif isinstance(artifact, Transition):
    links.append(artifact.source_mode)             # (TRANS, MODE, exits) 源侧
    links.append(artifact.target_mode)             # (TRANS, MODE, enters) 源侧
    if artifact.guard:
        links.append(artifact.guard)               # (TRANS, GUARD, guarded_by) 源侧
    links.extend(artifact.related_requirements)    # (REQ, TRANS, requires_transition) 目标侧
    links.extend(artifact.related_abnormals)       # (ABN, TRANS, triggers_transition) 目标侧
    # NOTE: artifact.actions 不提取 — §4.8 frozen decision
```

**Guard 分支提取：**
```python
elif isinstance(artifact, Guard):
    links.extend(artifact.related_interfaces)      # (GUARD, IFACE, observes) 源侧
    links.extend(artifact.related_requirements)    # (REQ, GUARD, defines_condition) 目标侧
    links.extend(artifact.used_by_transitions)     # (TRANS, GUARD, guarded_by) 目标侧 §2.7
```

**P0/P1 模型 additive fields 追加提取：**

在现有 4 个分支中追加：

```python
# Requirement 分支追加：
links.extend(artifact.linked_modes)
links.extend(artifact.linked_transitions)
links.extend(artifact.linked_guards)

# Function 分支追加：
links.extend(artifact.related_modes)
# NOTE: artifact.related_transitions 不提取 — §4.8

# Interface 分支追加：
links.extend(artifact.related_modes)
links.extend(artifact.related_guards)

# Abnormal 分支追加：
links.extend(artifact.related_modes)
links.extend(artifact.related_transitions)
```

### 5.3 完整 reverse-loop 覆盖矩阵（程序化参照表）

| # | Trace direction | 源侧字段 | 目标侧字段 | 2B enforcement |
|---|---|---|---|---|
| 1 | `(REQ, MODE, requires_mode)` | `Requirement.linked_modes` | `MODE.related_requirements` | **T1** |
| 2 | `(REQ, TRANS, requires_transition)` | `Requirement.linked_transitions` | `TRANS.related_requirements` | **T1** |
| 3 | `(REQ, GUARD, defines_condition)` | `Requirement.linked_guards` | `GUARD.related_requirements` | **T1** |
| 4 | `(ABN, MODE, triggers_mode)` | `Abnormal.related_modes` | `MODE.related_abnormals` | **T1** |
| 5 | `(ABN, TRANS, triggers_transition)` | `Abnormal.related_transitions` | `TRANS.related_abnormals` | **T1** |
| 6 | `(MODE, FUNC, activates)` | `MODE.active_functions` | `Function.related_modes` | **T1** |
| 7 | `(MODE, IFACE, monitors)` | `MODE.monitored_interfaces` | `Interface.related_modes` | **T1** |
| 8 | `(TRANS, MODE, exits)` | `TRANS.source_mode` | `MODE.outgoing_transitions` | **T1** |
| 9 | `(TRANS, MODE, enters)` | `TRANS.target_mode` | `MODE.incoming_transitions` | **T1** |
| 10 | `(TRANS, GUARD, guarded_by)` | `TRANS.guard` | `GUARD.used_by_transitions` | **T1** |
| 11 | `(GUARD, IFACE, observes)` | `GUARD.related_interfaces` | `Interface.related_guards` | **T1** |

### 5.4 明确不进入 consistency scope 的关系

| 关系 | 原因 | 证据 |
|---|---|---|
| `TRANS → FUNC` | §4.8 frozen: field-only | trace.py L73 注释 |
| `TRANS → IFACE` | §4.6 frozen: field-only | trace.py L74 注释 |
| `Function.related_transitions` | §4.8: 不进入 `_get_all_embedded_links()` | PHASE2_ARCHITECTURE_PLAN §4.8 |

---

## 6. mode_graph / mode_validator 分工

### 6.1 mode_graph (`services/mode_graph.py`)

**职责：纯数据结构，只读查询接口**

```python
class ModeGraph:
    nodes: dict[str, Mode]           # MODE-xxxx → Mode instance
    edges: dict[str, Transition]     # TRANS-xxxx → Transition instance
    guards: dict[str, Guard]         # GUARD-xxxx → Guard instance
    initial_mode: str | None         # MODE-xxxx of is_initial=True

    # ── 构建方法 ──
    @classmethod
    def from_registry(cls, registry: ArtifactRegistry) -> "ModeGraph":
        """从 registry 中提取 MODE/TRANS/GUARD 构建图。"""

    # ── 只读查询 ──
    def reachable_from(self, mode_id: str) -> set[str]: ...
    def unreachable_modes(self) -> list[str]: ...
    def dead_transitions(self) -> list[str]: ...
    def transitions_from(self, mode_id: str) -> list[str]: ...
    def transitions_to(self, mode_id: str) -> list[str]: ...
```

**绝不包含：** 任何 `step()` / `fire()` / `execute()` 方法。ModeGraph 是静态快照，不是状态机引擎。

### 6.2 mode_validator (`validators/mode_validator.py`)

**职责：消费 ModeGraph，产出 issue 列表**

| 检查项 | 对应 Gate | Tier |
|---|---|---|
| 恰好 1 个 `is_initial: true` MODE | P2B-C / P2-B1 | T1 |
| 所有 MODE 从 initial 可达 | P2B-C / P2-B2 | T1 |
| 每个 TRANS.source_mode / target_mode 解析到真实 MODE | P2B-C / P2-B3 | T1 |
| 每个非空 TRANS.guard 解析到真实 GUARD | P2B-C / P2-B5 | T1 |
| 每个 TRANS.trigger_signal 的 IFACE ID 存在 | P2B-D / structural | T1 |
| 每个 TRANS.actions 中 FUNC ID 存在 | P2B-D / structural (§4.8) | T1 |
| self-loop (`source_mode == target_mode`) 必须有 `len(notes.strip()) > 0` | P2B-C / P2-B4 | T1 |
| 无 unreachable mode（非 initial 且无入边） | P2B-C / P2-C1 | T1 |
| dead-end mode (zero outgoing TRANS) 必须有 `mode_type in {'shutdown', 'emergency'}` | P2B-C / P2-C2 | T1 |
| 无 orphan transition（源 mode 不可达） | P2B-C / P2-C3 | T1 |
| 同源 mode 优先级 + guard 冲突 | P2B-C / P2-C4-R | **T3 advisory** |
| predicate signal_ref → IFACE+signal 存在 | P2B-D | T1 |
| predicate signal_ref 覆盖 ⊆ related_interfaces | P2B-D | T1 |

### 6.3 coverage_validator (`validators/coverage_validator.py`)

| 检查项 | 对应 Gate | Tier |
|---|---|---|
| 每个 ABN 至少被 1 个 MODE.related_abnormals 或 TRANS.related_abnormals 引用 | P2-D1 | T1 |
| degraded mode (`mode_type == 'degraded'`) 必须有 `len(outgoing_transitions) > 0` | P2-D2 | T1 |
| degraded mode 出边是否通向 recovery (normal mode) | P2-D2-R | **T2 manual signoff at 2C** |
| emergency mode 至少是 1 条 TRANS 的 target | P2-D3 | T1 |
| ABN severity ↔ mode_type 对齐 | P2-D4-R | **T3 advisory** |

### 6.5 `validate-modes` CLI 作用域合同

**本节为正式行为合同（R2 冻结）。** Phase 2B 执行器在实现 `validate-modes` 命令时，必须按此合同实现，不得自行解释。

#### 通用行为

- 必须使用 `iter_artifact_yamls()` + `ArtifactRegistry` 加载 — 不得自行 glob
- 目录分类采用 **三类判定逻辑**（见下文 A/B/C），不是二分法
- 输出第一行必须标注目录类型标签
- 输出必须包含 Phase 2 artifact 计数：`Found: X modes, Y transitions, Z guards`

#### 目录分类逻辑（三类，不可混淆）

```python
# 伪代码 — 执行器必须实现等价逻辑
if is_formal_baseline_root(target_dir):
    scope_label = "[Formal]"
elif has_baseline_local_aplh(target_dir):  # target_dir / .aplh / freeze_gate_status.yaml 存在
    scope_label = "[Demo-scale]"  # 仅当 baseline_scope == "demo-scale" 时
else:
    scope_label = "[Unmanaged]"   # 既非 formal 也非 demo baseline
```

**判定依据：**
- `[Formal]`：`is_formal_baseline_root(target_dir)` == True（即 `artifacts/` 的绝对路径）
- `[Demo-scale]`：NOT formal，但 `target_dir/.aplh/freeze_gate_status.yaml` 存在且 `baseline_scope == "demo-scale"`
- `[Unmanaged]`：既不是 formal root，也没有 `.aplh/freeze_gate_status.yaml`（或 baseline_scope 不是已知值）

#### A. Formal root：`validate-modes --dir artifacts/`

| 条件 | 当前现实 |
|---|---|
| `is_formal_baseline_root()` | `True` |
| `.aplh/freeze_gate_status.yaml` baseline_scope | `freeze-complete`（但全部布尔值为 false） |
| Phase 2 artifact count | 0（formal baseline 无 MODE/TRANS/GUARD） |

**合同行为：**
```
[Formal] artifacts/
Found: 0 modes, 0 transitions, 0 guards
Mode graph validation not applicable — no Phase 2 artifacts found.
Exit code: 0
```

**理由：** 零 Phase 2 artifact 不是错误，是"无可验证内容"。与 P0/P1 `validate-artifacts` 在空目录上 exit 0 的惯例一致。

#### B. Demo root：`validate-modes --dir artifacts/examples/minimal_demo_set/`

| 条件 | 当前现实 |
|---|---|
| `is_formal_baseline_root()` | `False` |
| `.aplh/freeze_gate_status.yaml` baseline_scope | `demo-scale` |
| Phase 2 artifact count | 0（demo 仅含 P0/P1 类型） |

**合同行为（当前无 Phase 2 artifact 时）：**
```
[Demo-scale] artifacts/examples/minimal_demo_set/
Found: 0 modes, 0 transitions, 0 guards
Mode graph validation not applicable — no Phase 2 artifacts found.
Exit code: 0
```

**合同行为（Phase 2C 添加 demo mode artifact 后）：**
```
[Demo-scale] artifacts/examples/minimal_demo_set/
Found: 3 modes, 3 transitions, 2 guards
Demo-scale mode graph checks passed.
  Initial mode: MODE-0001 (Normal Governing)
  All modes reachable: YES
  Dead transitions: 0
  ...
Exit code: 0 (if all T1 checks pass) or 1 (if any T1 check fails)
```

**关键：** 输出永远不会说 "Ready for Formal Baseline Freeze" 或 "Formal mode graph validated"。

#### C. 任意非 formal、非 demo 目录（`[Unmanaged]`）

| 条件 | 示例 |
|---|---|
| `is_formal_baseline_root()` | `False` |
| `.aplh/freeze_gate_status.yaml` | 不存在 |
| Phase 2 artifact count | 可能为 0 或 >0（如 `tmp_path` 合成测试目录） |

**合同行为（零 Phase 2 artifact）：**
```
[Unmanaged] /some/arbitrary/path
Found: 0 modes, 0 transitions, 0 guards
Mode graph validation not applicable — no Phase 2 artifacts found.
Exit code: 0
```

**合同行为（有 Phase 2 artifact，如合成测试数据）：**
```
[Unmanaged] /tmp/pytest-xxx/test_xxx/
Found: 10 modes, 12 transitions, 5 guards
Unmanaged mode graph checks:
  Initial mode: MODE-0001
  All modes reachable: YES
  ...
Exit code: 0 (if all T1 checks pass) or 1 (if any T1 check fails)
```

**关键区别：** `[Unmanaged]` 目录不得输出 `[Demo-scale]` 标签。`[Demo-scale]` 仅用于有 `.aplh/freeze_gate_status.yaml` 且 `baseline_scope == "demo-scale"` 的真实 demo baseline root。合成测试目录属于 `[Unmanaged]`。

#### D. 不存在的目录

**合同行为：**
```
Error: Directory does not exist: /path/to/nonexistent
Exit code: 1
```

#### E. 含 Phase 2 artifact 但验证失败

**合同行为：** exit 1, 输出所有 T1 issue 列表。标签仍按 A/B/C 分类显示。

#### `--coverage` flag 行为

- 不加 `--coverage`：只运行 `mode_validator` 的结构检查（P2-B1~B5, P2-C1~C3）
- 加 `--coverage`：额外运行 `coverage_validator`（P2-D1~D3）
- T3 advisory 项（P2-C4-R, P2-D4-R）在两种模式下均输出为 `[ADVISORY]` 标记，不影响 exit code

### 6.4 哪些还不做

| 功能 | 为什么2B不做 |
|---|---|
| 执行语义（fire transition） | Phase 3+ execution engine |
| 并行 region / history pseudostate | Phase 3+ if needed |
| 时序约束检查 | Phase 3+ timing extension |
| predicate 语义重叠检测 | Phase 3+, requires range analysis |
| DOT/text 导出 | Phase 2D reporter |

---

## 7. Gate 设计

### Gate P2B-A: 2A schema contract preserved

**目标：** 证明 Phase 2B 实施没有破坏 2A 冻结的 schema 合同。检查"合同是否被保持"，而非"工作树是否干净"。

**T1 检查项（程序化 hard gate）：**

| # | 检查 | 通过条件 | 验证方式 |
|---|---|---|---|
| P2B-A1 | 2A 全部测试无回归 | `.venv/bin/python -m pytest tests/test_phase2a_models.py tests/test_control_surface.py tests/test_example_artifacts.py tests/test_id_rules.py tests/test_remediation_negative.py tests/test_schema_validation.py tests/test_traceability.py` 退出 0，原 111 测试全部 pass。**注意：** 仓库中 2A 测试文件的真实名称是 `tests/test_phase2a_models.py`（不是 `test_phase2_models.py`），其余 6 个文件为 P0/P1 测试。 | pytest |
| P2B-A2 | JSON schema 字节一致 | `scripts/dump_schemas.py` 输出与 2A 冻结版本一致 | 脚本比较 |
| P2B-A3 | Trace direction 集合大小不变 | `len(VALID_TRACE_DIRECTIONS) == 25` | 单元测试断言 |
| P2B-A4 | §4.8 exclusion 维持 | `_get_all_embedded_links()` 对含 `actions` 的 Transition 不返回 FUNC IDs | 负面单元测试 |
| P2B-A5 | §4.8 exclusion 维持 | `_get_all_embedded_links()` 对含 `related_transitions` 的 Function 不返回 TRANS IDs | 负面单元测试 |

**T3 辅助信号（非阻塞）：**

| # | 信号 | 用途 |
|---|---|---|
| P2B-A6-T3 | `git diff` 对 2A 冻结文件（models/ 下 10 个文件 + trace.py）的变更 | 供 reviewer 快速定位意外修改；不作为 hard gate |

**失败模式：**
- 2B 开发者因"发现 2A schema 不够好"而偷改字段名/类型 → 被 P2B-A1 和 P2B-A2 捕获
- 2B 开发者误把 `TRANS.actions` 拉入 consistency scope → 被 P2B-A4 捕获
- 2B 开发者误加 trace direction → 被 P2B-A3 捕获

**若确实发现 2A schema 有阻断性问题：** 必须回到主控会话审批 schema 修订，不得 in-place 修改。

### Gate P2B-B: Reverse-loop consistency extended

| 项 | 内容 |
|---|---|
| **输入** | 扩展后的 `consistency_validator.py` + 合成测试数据 |
| **检查项** | `_get_all_embedded_links()` 对 MODE/TRANS/GUARD 提取完整 11 个方向；`_validate_trace_reverse_loop()` 对这些方向执行双向检查 |
| **通过条件** | §5.3 覆盖矩阵 11 条方向均有测试覆盖；合成 `tmp_path` 数据中故意缺失 reciprocal 的情况被检出 |
| **失败模式** | 漏提取某个 additive/reciprocal 字段；误提取 §4.8 excluded 字段 |
| **Tier** | **T1** — pytest 自动化 |
| **边界** | 不检查 TRANS.actions / Function.related_transitions |

### Gate P2B-C: Mode/transition graph structurally valid

| 项 | 内容 |
|---|---|
| **输入** | `mode_graph.py` + `mode_validator.py` + 合成测试数据 |
| **检查项** | P2-B1 through P2-B5, P2-C1 through P2-C3 |
| **通过条件** | 合成数据包含 ≥10 modes, priority collisions, unreachable states, dangling guards 等对抗性用例；所有 T1 项通过 |
| **失败模式** | graph 与 validator 耦合；缺少对抗性测试用例 |
| **Tier** | **T1** (C1-C3), **T3** (C4-R advisory) |
| **边界** | 不含执行语义 |

### Gate P2B-D: Guard linkage / predicate structure valid

| 项 | 内容 |
|---|---|
| **输入** | mode_validator + 合成 guard 数据 |
| **检查项** | signal_ref 解析到真实 IFACE+signal；coverage ⊆ related_interfaces；TRANS.actions FUNC 存在性 |
| **通过条件** | 合成数据含无效 signal_ref, 缺失 IFACE, 缺失 FUNC 等负面用例均被检出 |
| **失败模式** | predicate checker 变成 evaluator |
| **Tier** | **T1** |
| **边界** | 不做语义求值 |

### Gate P2B-E: Dead transition / unreachable mode analysis ready

| 项 | 内容 |
|---|---|
| **输入** | mode_validator + coverage_validator + 合成数据 |
| **检查项** | P2-D1 through P2-D3；dead-end / orphan detection |
| **通过条件** | ABN 映射、degraded recovery、emergency 可达性在合成数据中全部通过；对抗性数据被正确检出 |
| **失败模式** | coverage 检查忽略某个 degraded mode |
| **Tier** | **T1** (D1-D3), **T3** (D4-R advisory) |
| **边界** | severity↔mode_type 对齐在 2B 是 T3，升为 T2 在 2C |

### Gate P2B-F: Phase 2C readiness handoff package ready

**T1 检查项（程序化 hard gate）：**

| # | 检查 | 通过条件 | 验证方式 |
|---|---|---|---|
| P2B-F1 | `validate-modes` CLI 命令可用 | `python -m aero_prop_logic_harness validate-modes --help` exit 0 | integration test |
| P2B-F2 | `validate-modes` integration test 通过 | 至少 1 个 `tmp_path` + subprocess 测试，含正面 + 负面用例 | pytest |
| P2B-F3 | `validate-modes` 零 artifact 目录行为符合 §6.5 | exit 0, 输出 "not applicable" | integration test |
| P2B-F4 | `validate-modes` 输出含三类标签 | 输出含 `[Formal]` / `[Demo-scale]` / `[Unmanaged]` 之一（按 §6.5 三类判定逻辑） | integration test |
| P2B-F5 | Human review checklist 文档存在且结构达标 | `docs/phase2b_review_checklist.md` 存在，且包含 §12.2 定义的全部 7 个必须 heading：(1) `# APLH Phase 2B Human Review Checklist`, (2) `## 1. Scope`, (3) `## 2. Review Items`, (4) `### 2.1 P2-C4-R`, (5) `### 2.2 P2-D4-R`, (6) `### 2.3 P2-D2-R`, (7) `## 3. Signoff`。P2B-F5 检查的是 §12.2 的完整最小骨架，不是缩减子集。验证方式：pytest 读取文件内容，用 `re.findall(r'^#{1,3} .+', content, re.MULTILINE)` 提取 heading 列表，断言全部 7 个必须 heading 均出现。仅检查 heading 文本前缀匹配，不检查 heading 下方具体内容。 | pytest 结构检查 |
| P2B-F6 | T3 advisory 项在输出中标记 | `validate-modes` 输出中 P2-C4-R / P2-D4-R 标记为 `[ADVISORY]` | integration test |
| P2B-F7 | 全部 pytest 通过 | `python -m pytest` exit 0（原 111 + 2B 新增） | pytest |

**Tier:** 全部 **T1** — 无 T2 在 2B 阶段。T2 signoff 推迟到 Phase 2C 入口（见 §12.4）。

**边界：** 不含 demo data；不宣布 Gate P2-F passed（那是 2C 的事）。

---

## 8. 开发顺序与里程碑

### Phase 2B-1: Consistency extension (先做)

**交付物：**
1. 扩展 `consistency_validator.py` 的 `_get_all_embedded_links()` — 追加 MODE/TRANS/GUARD 分支 + P0/P1 additive fields 追加
2. 单元测试：覆盖 §5.3 的 11 条方向，含正面和负面用例
3. 回归测试：确认原 P0/P1 reverse-loop 行为不变

**不做：** graph, validator, CLI

**通过标准：** Gate P2B-A + P2B-B pass

**进入下一阶段条件：** P2B-B 的 11 条方向全部有测试覆盖且通过

### Phase 2B-2: Mode graph foundation (第二做)

**交付物：**
1. `services/mode_graph.py` — `ModeGraph` class with `from_registry()`, `reachable_from()`, `unreachable_modes()`, `dead_transitions()`
2. 单元测试：合成数据 ≥10 modes, 含对抗性用例

**不做：** validator, coverage, CLI, 执行引擎

**通过标准：** ModeGraph 能正确构建图、答复拓扑查询

**进入下一阶段条件：** graph 测试通过

### Phase 2B-3: Mode validator + coverage validator + CLI (第三做)

**交付物：**
1. `validators/mode_validator.py` — 消费 ModeGraph 产出 issues
2. `validators/coverage_validator.py` — ABN 覆盖检查
3. CLI `validate-modes --dir <path> [--coverage]`
4. Integration tests via `tmp_path` + subprocess
5. `docs/phase2b_review_checklist.md` — 按 §12.2 最小章节结构，覆盖 P2-C4-R, P2-D4-R, P2-D2-R

**不做：** demo data authoring, DOT export, execution engine

**通过标准：** Gate P2B-C + P2B-D + P2B-E + P2B-F pass（含 §6.5 CLI 合同测试 + P2B-F5 §12.2 完整 7-heading 结构 gate）

**进入下一阶段条件：** 全部 pytest 通过；CLI integration test 通过；checklist 文件存在且通过 P2B-F5 完整结构 gate（§12.2 全部 7 个必须 heading）

### Phase 2B-4: Handoff / reporting / 2C readiness package (最后做)

**交付物：**
1. `docs/PHASE2B_IMPLEMENTATION_NOTES.md` — 实施记录
2. 更新 `docs/ARTIFACT_MODEL.md` §8 — 反映 2B 实际产出
3. 更新 `docs/REVIEW_GATES.md` — 追加 Phase 2 gates
4. 2C 入口条件文档

**不做：** 代码变更

**通过标准：** 文档审查通过

---

## 9. 风险清单

### R-2B-1: 2B 回头污染 2A schema 合同

| 项 | 内容 |
|---|---|
| **风险描述** | 2B 开发者在扩展 validator 时发现 2A schema "不够好"，偷改字段名/类型 |
| **为什么真实** | 2B 是第一次真正"消费" 2A schema 的阶段，可能发现设计盲区 |
| **后果** | 111 个现有测试断裂，9 份 JSON schema 失效，未来 2C demo 数据与 schema 不匹配 |
| **缓解** | Gate P2B-A 的 5 项 T1 检查（pytest 回归 + JSON schema 一致 + trace direction 数 + §4.8 负面测试）；`git diff` 作为 T3 辅助信号供 reviewer 参考；如确实发现阻断性问题，必须回到主控会话审批，不得 in-place 修改 |

### R-2B-2: Reverse-loop 扩展漏项

| 项 | 内容 |
|---|---|
| **风险描述** | `_get_all_embedded_links()` 扩展时遗漏某个 additive/reciprocal 字段 |
| **为什么真实** | 9 个 additive fields + 3 个 reciprocal fields + 5 个 TRANS 嵌入字段 = 17 个字段需要正确提取，容易漏 |
| **后果** | 某些 trace direction 的 reverse-loop 验证被静默跳过 |
| **缓解** | 用 §5.3 覆盖矩阵作为测试 checklist；每个方向必须有独立正面+负面测试 |

### R-2B-3: Graph / validator 职责耦死

| 项 | 内容 |
|---|---|
| **风险描述** | `mode_graph.py` 逐渐吸收 validation 逻辑，或 validator 直接操作 graph 内部状态 |
| **为什么真实** | 两者操作相同数据集，开发者图省事倾向合并 |
| **后果** | Phase 3 execution engine 无法复用 graph 而不触发 validation side effects |
| **缓解** | ModeGraph 只暴露只读查询方法；mode_validator 通过查询接口消费，不持有 ModeGraph 可变引用 |

### R-2B-4: Field-only 关系误拉入 trace skeleton

| 项 | 内容 |
|---|---|
| **风险描述** | 开发者误把 `TRANS.actions` 或 `Function.related_transitions` 放入 `_get_all_embedded_links()` |
| **为什么真实** | 这些字段"看起来"应该进入 consistency scope，§4.8 的 frozen decision 容易被忘记 |
| **后果** | trace 系统要求补建 `(TRANS, FUNC, executes)` TraceLink，violation of §4.8 |
| **缓解** | 在 `_get_all_embedded_links()` 的 TRANS 分支加明确注释 `# NOTE: actions excluded per §4.8`；加负面测试确认 actions 不被提取 |

### R-2B-5: Predicate grammar 被滥用成 evaluator

| 项 | 内容 |
|---|---|
| **风险描述** | mode_validator 中的 predicate checker 逐渐增加"计算"能力（range overlap, symbolic execution） |
| **为什么真实** | P2-C4-R 明确提到 guard overlap 需要 range analysis，开发者可能提前实现 |
| **后果** | 2B 引入半成品 evaluator，成为 Phase 3 的技术债 |
| **缓解** | 2B 的 predicate checker 只做 structural checks（signal_ref 解析 + coverage 检查）；P2-C4-R 在 2B 显式标为 T3 advisory |

### R-2B-6: Demo/formal boundary 再次污染

| 项 | 内容 |
|---|---|
| **风险描述** | 新 CLI `validate-modes` 命令不尊重 `iter_artifact_yamls()` traversal 规则，或缺少 demo/formal 标识 |
| **为什么真实** | 新命令是从零写的，容易跳过已有的边界基础设施 |
| **后果** | demo 数据泄漏到 formal scope 评估 |
| **缓解** | validate-modes 必须使用 `iter_artifact_yamls()` + registry；输出必须含 "Demo-scale" / "Formal" 标签；加 integration test 验证 |

---

## 10. Phase 2B 实施提示词骨架

```
【会话名】
APLH-Phase2B-Exec

【负责模型】
Opus 4.6

【职责类型】
主执行 / Phase 2B 实施

【角色定义】
你是 APLH Phase 2B 的实施执行器。
你的唯一任务是实现 Phase 2B：reverse-loop consistency extension + mode graph + mode validator。
你不是规划者（规划已完成，见 docs/PHASE2B_ARCHITECTURE_PLAN.md）。
你不能修改 2A 冻结 schema 合同。
你不能宣布 Phase 2 已完成。
你不能实现 execution engine / evaluator / demo authoring。

【唯一目标】
实现 Phase 2B 交付物并通过 Gates P2B-A through P2B-F。

【输入上下文】
- 架构规划：docs/PHASE2B_ARCHITECTURE_PLAN.md
- 2A 冻结合同：docs/PHASE2A_IMPLEMENTATION_NOTES.md
- 2A 实现参考：models/mode.py, models/transition.py, models/guard.py, models/predicate.py
- additive/reciprocal 字段：models/requirement.py, function.py, interface.py, abnormal.py (§2.6/§2.7)
- 现有 consistency validator：validators/consistency_validator.py
- trace directions：models/trace.py (25 directions)
- 现有 registry：services/artifact_registry.py
- 现有 CLI：cli.py
- reverse-loop 覆盖矩阵：PHASE2B_ARCHITECTURE_PLAN §5.3

【交付物】
Phase 2B-1:
  1. 扩展 consistency_validator.py: _get_all_embedded_links() 追加 MODE/TRANS/GUARD + P0/P1 additive 提取
  2. 测试：§5.3 覆盖矩阵 11 条方向 × (正面 + 负面) + 回归

Phase 2B-2:
  3. services/mode_graph.py: ModeGraph class with from_registry(), reachable_from(), unreachable_modes(), dead_transitions()
  4. 测试：合成 ≥10 modes 对抗性数据

Phase 2B-3:
  5. validators/mode_validator.py: 结构完整性检查（见 §6.2 检查项表）
  6. validators/coverage_validator.py: ABN 覆盖（见 §6.3 检查项表）
  7. cli.py: validate-modes --dir <path> [--coverage]
  8. Integration tests via tmp_path + subprocess
  9. docs/phase2b_review_checklist.md（按 §12.2 结构，覆盖 P2-C4-R / P2-D4-R / P2-D2-R）

Phase 2B-4:
  10. docs/PHASE2B_IMPLEMENTATION_NOTES.md
  11. 更新 docs/ARTIFACT_MODEL.md §8, docs/REVIEW_GATES.md

【Gate 通过条件（R2 更新）】
- Gate P2B-A: `.venv/bin/python -m pytest tests/test_phase2a_models.py tests/test_control_surface.py tests/test_example_artifacts.py tests/test_id_rules.py tests/test_remediation_negative.py tests/test_schema_validation.py tests/test_traceability.py` 退出 0（原 111 测试） + JSON schema 字节一致 + trace direction 数 == 25 + §4.8 负面测试通过（详见 §7 P2B-A）。**注意：仓库中 2A 测试文件真实名称是 `test_phase2a_models.py`，不是 `test_phase2_models.py`。**
- Gate P2B-B: §5.3 11 条方向全部有正面+负面测试
- Gate P2B-C: P2-B1~B5, P2-C1~C3 在合成数据上通过。注意：所有 T1 gate 必须基于结构化字段，不得依赖自由文本判定（§7 P2B-C 附注）
- Gate P2B-D: signal_ref 解析, FUNC 存在性, coverage 检查通过
- Gate P2B-E: ABN 映射、degraded 有出边（结构检查）、emergency 可达性在合成数据上通过
- Gate P2B-F: CLI integration test 通过（含 §6.5 三类目录行为 + P2B-F5 完整结构 gate）；`docs/phase2b_review_checklist.md` 存在且通过 §12.2 全部 7 个必须 heading 结构检查（不是缩减子集）

【代码文件授权（§11.3）】
允许创建：
- services/mode_graph.py
- validators/mode_validator.py
- validators/coverage_validator.py
- tests/test_phase2b_*.py
- docs/phase2b_review_checklist.md
- docs/PHASE2B_IMPLEMENTATION_NOTES.md
禁止修改：models/ 下全部 2A 文件、loaders/、path_constants.py、freeze-readiness 逻辑

【validate-modes CLI 合同（§6.5 R2 冻结）】
- 三类目录标签：[Formal] / [Demo-scale] / [Unmanaged]（不是二分法）
- [Formal] = is_formal_baseline_root() == True
- [Demo-scale] = NOT formal, 但 .aplh/freeze_gate_status.yaml 存在且 baseline_scope == "demo-scale"
- [Unmanaged] = 既非 formal 也非 demo baseline（含 tmp_path 合成测试目录）
- 零 Phase 2 artifact 目录 → exit 0, "not applicable"
- --coverage flag 额外运行 coverage_validator
- T3 advisory 项输出为 [ADVISORY]，不影响 exit code

【边界 / 禁止事项】
- 不要修改 2A 模型 schema（见 §11.3 禁止清单）
- 不要新增 TRANS→FUNC trace direction
- 不要新增 TRANS→IFACE trace direction
- 不要将 TRANS.actions 纳入 _get_all_embedded_links()
- 不要将 Function.related_transitions 纳入 _get_all_embedded_links()
- 不要实现 predicate evaluator / 语义求值
- 不要实现 execution engine / step / fire
- 不要创建 demo Phase 2 artifact 数据
- 不要修改 freeze-readiness 命令
- 不要修改 path_constants.py
- 不要破坏任何现有测试
- ModeGraph 不能有 step/fire/execute 方法
- mode_validator 不能直接修改 ModeGraph 内部状态
- T1 gate 不得依赖自由文本 notes/rationale 判定（self-loop 除外：检查 `len(notes.strip()) > 0`）
- dead-end mode T1 = mode_type in {shutdown, emergency}，不接受 notes 逃逸

【开发顺序】
严格按 2B-1 → 2B-2 → 2B-3 → 2B-4 执行，每阶段通过后再进入下一阶段。
```

---

## 11. 最终建议

### 11.1 下一轮会话分配

| 动作 | 推荐会话名 | 推荐模型 | 理由 |
|---|---|---|---|
| 2B 实施 | `APLH-Phase2B-Exec` | **Opus 4.6** | graph 算法实现 + 对抗性测试设计需要强推理 |
| 2B 审查 | `APLH-Phase2B-Review` | **Opus 4.6** 或独立人工 | gate 验证深度同实施 |
| 2C 实施 | `APLH-Phase2C-Exec` | Opus 4.6 或 GPT-5.4 | 数据 authoring 相对常规 |

### 11.2 推荐下一步

1. 将本规划文档提交主控会话审查
2. 如批准，使用 §10 的提示词骨架启动 `APLH-Phase2B-Exec / Opus 4.6`
3. 2B 完成后，基于 Gate P2B-F 判定是否进入 2C
4. 不跳阶段，不并行 2B 与 2C

### 11.3 代码文件授权合同

Phase 2B **允许**创建以下类别的新代码文件：

| 类别 | 允许的文件 | 理由 |
|---|---|---|
| 核心服务 | `services/mode_graph.py` | 2B-2 交付物：有向图构建 |
| 核心验证器 | `validators/mode_validator.py` | 2B-3 交付物：结构完整性检查 |
| 核心验证器 | `validators/coverage_validator.py` | 2B-3 交付物：ABN 覆盖检查 |
| CLI 扩展 | `cli.py`（扩展，非新建） | 2B-3 交付物：`validate-modes` 命令 |
| 测试文件 | `tests/test_phase2b_*.py` | 2B-1/2/3 各阶段的单元 + 集成测试 |
| 文档 | `docs/PHASE2B_IMPLEMENTATION_NOTES.md` | 2B-4 交付物 |
| 文档 | `docs/phase2b_review_checklist.md` | 2B-3 交付物（§12 定义） |

Phase 2B **禁止**创建或修改以下类别的文件：

| 类别 | 禁止的文件 | 理由 |
|---|---|---|
| 2A 冻结模型 | `models/mode.py`, `transition.py`, `guard.py`, `predicate.py`, `common.py`, `trace.py` | 2A schema 合同冻结 |
| 2A 冻结模型 | `models/requirement.py`, `function.py`, `interface.py`, `abnormal.py` | 2A additive fields 冻结 |
| 2A 冻结加载器 | `loaders/artifact_loader.py` | 2A 加载逻辑冻结 |
| 路径常量 | `path_constants.py` | 已足够 |
| 冻结逻辑 | `freeze-readiness` 相关 | P0/P1 gate 不可动 |
| Demo 数据 | `artifacts/examples/**/*.yaml` | Phase 2C scope |
| 执行引擎 | 任何含 `step`, `fire`, `execute` 语义的模块 | Phase 3+ |

### 11.4 本文档不授权什么

- 不宣布 Phase 2B 已实现
- 不修改 2A 冻结 schema
- 不推进到 2C

---

## 12. P2B-F Human Review Checklist 产物合同

### 12.1 文件路径与格式

| 项 | 冻结值 |
|---|---|
| **路径** | `docs/phase2b_review_checklist.md` |
| **格式** | Markdown |
| **创建时机** | Phase 2B-3（与 mode_validator / coverage_validator 同时交付） |
| **作者** | Phase 2B 执行器 |

### 12.2 最小必须章节

文档必须包含以下章节，不可缺省：

```markdown
# APLH Phase 2B Human Review Checklist

## 1. Scope
- What this checklist covers (P2-C4-R, P2-D4-R, P2-D2-R)
- What it does NOT cover (T1 items handled by automated gates)

## 2. Review Items

### 2.1 P2-C4-R: Priority conflicts with overlapping guards
- [ ] For each source_mode with multiple outgoing transitions:
  - List transitions sharing equal priority
  - Assess whether guard predicates could overlap
  - Record: PASS / CONCERN / N/A

### 2.2 P2-D4-R: ABN severity matches mode type
- [ ] For each ABN → MODE mapping:
  - Verify severity_hint is consistent with target mode_type
  - Record: PASS / CONCERN / N/A

### 2.3 P2-D2-R: Degraded mode recovery path quality
- [ ] For each degraded mode with outgoing transitions:
  - Verify at least one path leads to a normal mode
  - Record: PASS / CONCERN / N/A

## 3. Signoff
- Reviewer:
- Date:
- Verdict: PASS / REVISE
```

### 12.3 Signoff 规则（R2 冻结：baseline-local `.aplh` 锚定）

#### 12.3.1 路径锚定合同

Signoff 文件 **必须** 与其背书的 baseline 物理同位（collocation 规则），与现有 `freeze_gate_status.yaml` 的 collocation 治理一致。

| baseline | signoff 绝对路径 | 理由 |
|---|---|---|
| **Formal baseline** (`artifacts/`) | `artifacts/.aplh/review_signoffs.yaml` | 与 `artifacts/.aplh/freeze_gate_status.yaml` 同位 |
| **Demo baseline** (`artifacts/examples/minimal_demo_set/`) | `artifacts/examples/minimal_demo_set/.aplh/review_signoffs.yaml` | 与 demo 的 `freeze_gate_status.yaml` 同位 |
| **Unmanaged path** (无 `.aplh/`) | **不允许 signoff** | 没有 `.aplh/` 的目录不是受治理 baseline，不能记录 signoff |

**禁止的路径：**
- 项目根目录下的 `.aplh/review_signoffs.yaml`（不存在这样的目录）
- 当前工作目录或任意祖先目录下注入 signoff
- 与 baseline 不同位的任何路径

#### 12.3.2 Signoff 元数据

| 项 | 冻结值 |
|---|---|
| **Signoff 角色** | Phase 2B reviewer（与执行器不同人/不同会话） |
| **Signoff 字段** | `reviewer`, `date`, `checklist_path`, `checklist_version`, `items_reviewed: [P2-C4-R, P2-D4-R, P2-D2-R]`, `verdict` |
| **创建责任** | Phase 2C 执行器或 reviewer 在做 T2 signoff 时创建；Phase 2B 执行器 **不创建** signoff 文件 |

#### 12.3.3 Signoff schema 示例

```yaml
# 文件路径示例：artifacts/examples/minimal_demo_set/.aplh/review_signoffs.yaml
# （因为 Phase 2C demo data 在 demo baseline 下，signoff 也在 demo baseline 的 .aplh 下）
phase2b_review_signoff:
  reviewer: "APLH-Phase2B-Review / Opus 4.6"
  date: "2026-04-XX"
  checklist_path: "docs/phase2b_review_checklist.md"
  checklist_version: "1.0"
  baseline_path: "artifacts/examples/minimal_demo_set/"  # 标明此 signoff 背书哪个 baseline
  items_reviewed:
    - id: "P2-C4-R"
      verdict: "PASS"
      notes: ""
    - id: "P2-D4-R"
      verdict: "PASS"
      notes: ""
    - id: "P2-D2-R"
      verdict: "PASS"
      notes: ""
  overall_verdict: "PASS"
```

### 12.4 与 Gate 治理体系的关系

| 阶段 | Checklist items tier | 阻塞效果 | Signoff 文件位置 |
|---|---|---|---|
| Phase 2B | **T3 advisory** | 不阻塞 2B→2C 进入。Checklist 文档必须存在（P2B-F5 T1 结构检查），但 signoff **不要求**，signoff 文件 **不创建**。 | N/A |
| Phase 2C | **T2 manual signoff** | 阻塞 2C→2D 进入。Signoff 必须记录在 **demo baseline 的** `artifacts/examples/minimal_demo_set/.aplh/review_signoffs.yaml`（因为 2C demo data 在 demo baseline 下）。Phase 2C 执行器或 reviewer 在此时创建该文件。 | `<demo_baseline>/.aplh/review_signoffs.yaml` |

### 12.5 Phase 2B 执行器的义务

Phase 2B 执行器只需：
1. 创建 `docs/phase2b_review_checklist.md`，遵循 §12.2 最小章节结构
2. 在 T3 advisory 输出中标记所有 P2-C4-R / P2-D4-R / P2-D2-R 项
3. 不需要自己做 signoff（那是 reviewer 的事）

---

*End of APLH Phase 2B Architecture Planning Package.*
