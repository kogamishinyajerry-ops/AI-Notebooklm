# 《APLH Phase 3 架构规划包》

**Document ID:** APLH-PLAN-P3  
**Version:** 1.0.0  
**Date:** 2026-04-04  
**Author:** Phase 3 Architecture Session (Opus 4.6)  
**Status:** DRAFT — Pending Main Controller Review  

---

## 1. 总体结论

### 1.1 当前是否允许开始 Phase 3 规划

**是。**

依据：
- Phase 2A Accepted — schema contract 冻结（参见 `docs/PHASE2A_IMPLEMENTATION_NOTES.md`）
- Phase 2B Accepted — ModeGraph + 三 validator 纯度保持（参见 `docs/PHASE2B_IMPLEMENTATION_NOTES.md`）
- Phase 2C Accepted — demo-scale execution readiness 已落地（参见 `docs/PHASE2C_REVIEW_REPORT.md`）
- 2C 审查报告明确写出 **"支持进入 Phase 3 准备阶段"**
- 4 项非阻塞技术债已登记，须在 Phase 3 处理

### 1.2 当前不允许假设什么

| # | 不允许的假设 | 理由 |
|---|-------------|------|
| 1 | "Phase 2 已完成 = Formal Ready" | formal baseline 仍未 freeze-complete（`artifacts/` 无 Phase 2 artifact） |
| 2 | "Phase 3 = Production Runtime" | Phase 3 仍是 demo-scale 增强层 |
| 3 | "Phase 3 可修改 2A/2B/2C contract" | 所有冻结决策必须持续成立 |
| 4 | "Phase 3 = Cert Software / Airworthiness" | APLH 不是适航软件 |
| 5 | "Phase 3 evaluator = 通用 DSL 平台" | evaluator 增强有严格边界 |

---

## 2. Phase 3 定义

### 2.1 目标

Phase 3 的核心定义：

> 在 2A/2B/2C 已冻结的 schema、静态验证层、demo-scale execution 层之上，建立一个**受控增强层**，用于：
> 1. 提升 guard evaluation 的表达能力边界（有限算术 / 时间窗口 / 滞后）
> 2. 提升 scenario authoring / replay / audit 的可用性与可追踪性
> 3. 强化 signoff 的审计粒度（reviewer / scenario_id / run_id / trace linkage）
> 4. 清偿 2C 审查报告点名的 4 项技术债
> 5. 为更后续阶段的 formal readiness 提供更稳固的 demo-scale 中间层

### 2.2 非目标（Out of Scope）

| # | 非目标 | 为什么排除 |
|---|--------|-----------|
| 1 | Formal Baseline Freeze | formal `artifacts/` 仍无 Phase 2+ artifact |
| 2 | Production Runtime / Cert Software | APLH 是开发辅助系统，不是飞控 |
| 3 | Physics Simulator / Control-Response Loop | 超出 knowledge harness 边界 |
| 4 | 大平台 UI / Authoring Studio | 保持 CLI-first + YAML-driven 架构 |
| 5 | 通用 DSL / Expression Language | evaluator 增强有明确天花板 |
| 6 | `TRANS -> FUNC` / `TRANS -> IFACE` trace 方向 | §4.8 / §4.6 冻结决策 |
| 7 | `predicate_expression` 重新引入 | `predicate` 是唯一权威字段 |
| 8 | ModeGraph 长出 `step/fire/evaluate/execute` | ModeGraph 保持只读 |
| 9 | Validators 变成 evaluator / dispatcher | validators 保持静态判断器纯度 |

### 2.3 为什么 Phase 3 必须建立在 2A/2B/2C 冻结输入之上

1. **Schema stability**: 2A 的 MODE/TRANS/GUARD 模型、predicate grammar、trace directions 是所有后续层的基础
2. **Purity guarantee**: 2B 的 ModeGraph 只读性 + validator 分层是 evaluator 增强能安全实施的前提
3. **Execution readiness**: 2C 的 ScenarioEngine / RuntimeState / GuardEvaluator 是 Phase 3 增强的直接基座
4. **Contract chain**: 每个 Phase 的输出是下一 Phase 的不可变输入。如果回改 2A/2B/2C，整条验证链失效

### 2.4 为什么 Phase 3 仍不能进入 formal baseline freeze / production runtime / cert software

1. formal `artifacts/` 目录当前只有 P0/P1 artifact，无 Mode/Transition/Guard 实体
2. demo-scale baseline (`artifacts/examples/minimal_demo_set/`) 只有 1 个 scenario (`test.yml`)
3. ScenarioEngine 仍是 demo-level 分发器，无 formal verification coverage
4. GuardEvaluator 仍无 formal 边界测试覆盖（如 compound predicate 无测试）
5. Phase 3 的增强内容本身需要经历开发→审查→接受流程，不能直接声称 formal

### 2.5 Phase 3 与 2C、后续阶段的边界关系

```
Phase 2C (已冻结)              Phase 3 (本规划)              Phase 4+ (未来)
┌─────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────┐
│ ScenarioEngine      │───>│ Enhanced ScenarioEngine  │───>│ Formal Verification  │
│ GuardEvaluator      │───>│ Richer GuardEvaluator    │───>│ Cert Evaluator       │
│ DecisionTrace       │───>│ Correlated AuditTrace    │───>│ Formal Audit Pack    │
│ Signoff (basic)     │───>│ Enriched Signoff Schema  │───>│ Formal Signoff       │
│ Scenario (basic)    │───>│ Validated Scenarios      │───>│ Formal Test Suite    │
└─────────────────────┘    └──────────────────────────┘    └──────────────────────┘
      demo-scale                 demo-scale enhanced            formal-scale
```

Phase 3 是增强层，不是推翻重来。Phase 4+ 才考虑 formal readiness。

---

## 3. 模块树

### 3.1 Phase 3 核心模块

```
aero_prop_logic_harness/
├── models/
│   ├── scenario.py             [MODIFY]  — 增加 run_id, 增强验证
│   └── signoff.py              [NEW]     — Signoff entry 结构化 schema
│
├── services/
│   ├── guard_evaluator.py      [MODIFY]  — richer evaluation boundary
│   ├── scenario_engine.py      [MODIFY]  — run session identity + replay support
│   ├── decision_tracer.py      [MODIFY]  — trace correlation (run_id / scenario_id)
│   ├── scenario_validator.py   [NEW]     — scenario 结构预检 (graph compatibility)
│   ├── replay_engine.py        [NEW]     — deterministic replay from trace
│   └── audit_correlator.py     [NEW]     — trace ↔ signoff ↔ scenario 关联
│
├── cli.py                      [MODIFY]  — --reviewer param, replay command, etc.
│
tests/
├── test_phase3_evaluator.py    [NEW]     — richer evaluator boundary tests
├── test_phase3_replay.py       [NEW]     — replay / audit correlation tests
├── test_phase3_signoff.py      [NEW]     — signoff schema + formal rejection tests
└── test_phase3_scenario_val.py [NEW]     — scenario validation tests
```

### 3.2 模块职责矩阵

| 模块 | 职责 | Phase 3 核心? | 禁止延伸 |
|------|------|:---:|------|
| `signoff.py` | Signoff 条目结构化 schema（reviewer, scenario_id, run_id, resolution, timestamp） | ✅ | 不得进入 graph/validator |
| `guard_evaluator.py` (richer) | 有限算术组合 / 时间窗口 / 滞后 evaluator adapter | ✅ | 不得变成通用 DSL |
| `scenario_validator.py` | 预检 scenario 对 ModeGraph 的兼容性 | ✅ | 不得执行 scenario |
| `replay_engine.py` | 从已有 trace 确定性重放 | ✅ | 不得修改 ModeGraph |
| `audit_correlator.py` | run_id → scenario_id → signoff → trace 关联查询 | ✅ | 不得生成 signoff |
| `scenario.py` (enhanced) | 增加验证钩子、version field | ⚠️ 附属 | 不得破坏 2C contract |
| `decision_tracer.py` (enhanced) | 增加 run_id, scenario_id | ⚠️ 附属 | 不得破坏输出格式 |
| CLI 增强 | --reviewer, replay-scenario, validate-scenario | ⚠️ 附属 | 不得引入 UI |

### 3.3 不在 Phase 3 范围的模块

| 模块 | 为什么不在 Phase 3 |
|------|-------------------|
| ModeGraph 扩展 | ModeGraph 保持 2B 只读纯度 |
| 新 Validator | 现有 3 validator 保持 2B 分层 |
| Formal FreezeGateStatus 扩展 | formal freeze 不在 Phase 3 范围 |
| Auth / Access Control | 不是增强层 scope |

---

## 4. 2A/2B/2C → 3 数据契约

### 4.1 Phase 3 从 2A 读取的数据

| 模型 | 读取字段 | 用途 | 是否写入 |
|------|---------|------|:---:|
| `Mode` | `id`, `mode_type`, `is_initial`, `name` | 构建 ModeGraph（通过 2B API） | ❌ |
| `Mode` | `entry_conditions`, `exit_conditions` | ❌ 不读 — human summary only | ❌ |
| `Mode` | `active_functions`, `monitored_interfaces` | ❌ 不进入 evaluator scope | ❌ |
| `Transition` | `id`, `source_mode`, `target_mode`, `guard`, `priority` | ScenarioEngine 使用（同 2C） | ❌ |
| `Transition` | `actions` | 记录到 trace，不执行 | ❌ |
| `Transition` | `trigger_signal` | ❌ field-only, 不进入 evaluator | ❌ |
| `Guard` | `id`, `predicate` | GuardEvaluator 唯一输入 | ❌ |
| `Guard` | `description` | ❌ human summary, 不进入评估 | ❌ |
| `Guard` | `input_signals` | ❌ informational only | ❌ |
| `PredicateExpression` | 全部字段 | evaluator 核心 — Phase 3 增强此处 | ❌ |

### 4.2 Phase 3 从 2B 消费的 API

| API | 来源 | Phase 3 用法 |
|-----|------|-------------|
| `ModeGraph.from_registry()` | `mode_graph.py` | 构建图（只读） |
| `ModeGraph.transitions_from()` | `mode_graph.py` | ScenarioEngine candidate resolution |
| `ModeGraph.nodes` / `edges` / `guards` | `mode_graph.py` | 查询拓扑 |
| `ModeValidator.validate_all()` | `mode_validator.py` | scenario_validator 前置检查 |
| `CoverageValidator.validate_all()` | `coverage_validator.py` | 可选前置检查 |

**注意**：Phase 3 **不向 ModeGraph 添加新方法**。ScenarioEngine 使用的 public API 与 2C 完全相同。

### 4.3 Phase 3 从 2C 消费的数据

| 数据 | 来源 | Phase 3 用法 |
|------|------|-------------|
| `RuntimeState` | `scenario_engine.py` | 继续作为隔离运行时容器 |
| `DecisionTrace` / `TransitionRecord` | `decision_tracer.py` | 增加 run_id/scenario_id 关联 |
| `GuardEvaluator.evaluate()` | `guard_evaluator.py` | richer evaluator 在此基础上增强 |
| `review_signoffs.yaml` | `.aplh/` | 增强 schema，增加 scenario_id/run_id |
| `Scenario` / `ScenarioTick` | `scenario.py` | 增加预检，可选增强字段 |

### 4.4 Phase 3 不触及的冻结边界

| 冻结边界 | Phase 3 承诺 |
|---------|-------------|
| `GUARD.predicate` 是唯一机器权威字段 | ✅ 不变 |
| 不引入 `predicate_expression` | ✅ 不变 |
| `TRANS.actions` field-only, 不进入 consistency scope | ✅ 不变 |
| `Function.related_transitions` 不进入 consistency scope | ✅ 不变 |
| 不引入 `TRANS -> FUNC` trace | ✅ 不变 |
| 不引入 `TRANS -> IFACE` trace | ✅ 不变 |
| baseline-local `.aplh` collocation 规则 | ✅ 不变 |
| ModeGraph 不长出 `step/fire/evaluate/execute` | ✅ 不变 |
| Validators 不变成 evaluator / dispatcher | ✅ 不变 |
| `iter_artifact_yamls` 只扫 `*.yaml` | ✅ 不变 |

---

## 5. Richer Guard Evaluation Boundary

### 5.1 当前 GuardEvaluator 能力（2C 基线）

基于 `guard_evaluator.py` 实际代码：

- **AtomicPredicate**: `EQ, NE, GT, GE, LT, LE, BOOL_TRUE, BOOL_FALSE` — 单信号、单阈值对比
- **CompoundPredicate**: `AND, OR, NOT` — 布尔组合
- **无**: 算术表达式、跨信号运算、时间窗口、变化率、滞后、状态持续
- **失败模式**: 缺失信号 → `EvaluationError`（显式失败，正确行为）

### 5.2 Phase 3 允许扩展的能力

> [!IMPORTANT]
> Phase 3 evaluator 增强的基本原则：通过**外层 adapter / evaluator wrapper** 实现，不修改 predicate grammar 的核心语义。`predicate` 字段仍然是唯一权威。

#### 5.2.1 有限算术组合（允许）

**方式**: 在 `PredicateOperator` 枚举中新增有限算术运算符

| 新增 Operator | 语义 | 示例 |
|-------------|------|------|
| `DELTA_GT` | 信号变化量 > threshold | 本 tick `signal - prev_tick_signal > 10.0` |
| `DELTA_LT` | 信号变化量 < threshold | 本 tick `signal - prev_tick_signal < -5.0` |
| `IN_RANGE` | 信号值在 [low, high] 区间 | `20.0 <= signal <= 100.0` |

**实现约束**:
- `DELTA_*` 运算需要 `RuntimeState` 维护 `previous_signal_snapshot`（在 ScenarioEngine 中管理，不在 ModeGraph 中）
- `IN_RANGE` 需要 `threshold` 扩展为 `[low, high]` pair — 通过新增 `threshold_high` optional field 在 AtomicPredicate 上实现
- 不引入通用算术表达式解析器

#### 5.2.2 有限时间窗口（允许，受限）

| 新增 Operator | 语义 | 示例 |
|-------------|------|------|
| `SUSTAINED_GT` | 信号连续 N tick > threshold | `N2_speed > 95.0 for 3 ticks` |
| `SUSTAINED_LT` | 信号连续 N tick < threshold | `oil_pressure < 20.0 for 5 ticks` |

**实现约束**:
- 需要新增 `duration_ticks: Optional[int]` field 在 AtomicPredicate 上
- 状态由 `RuntimeState` 中的 `signal_history: Dict[str, List[Any]]` 管理
- 窗口大小硬限制：`1 <= duration_ticks <= 100`（防止无界内存增长）
- 不引入真实时间概念（仍是 tick-based）

#### 5.2.3 Hysteresis / 滞后（允许，受限）

| 概念 | Phase 3 实现 |
|------|-------------|
| Set-point hysteresis | 仅支持 `HYSTERESIS_BAND` operator：上升沿阈值 ≠ 下降沿阈值 |
| 实现方式 | 新增 `threshold_low` / `threshold_high` pair + `hysteresis_state` in RuntimeState |
| 不支持 | 自适应滞后、非对称死区、PID 积分 |

#### 5.2.4 实现架构：Evaluator Adapter 层

```
                ┌────────────────────┐
                │  ScenarioEngine    │  (unchanged control flow)
                └────────┬───────────┘
                         │ evaluate(predicate, snapshot)
                         ▼
                ┌────────────────────┐
                │  RicherEvaluator   │  [NEW — Phase 3]
                │  (adapter layer)   │  
                │  ┌───────────────┐ │
                │  │ delegates to  │ │
                │  │ GuardEvaluator│ │  (2C core — unchanged)
                │  └───────────────┘ │
                │  + delta_eval()    │
                │  + sustained_eval()│
                │  + hysteresis_eval()│
                └────────────────────┘
                         │ reads only
                         ▼
                ┌────────────────────┐
                │  RuntimeState      │  (extended with signal_history)
                └────────────────────┘
```

**关键设计决策**:
- `RicherEvaluator` 是 `GuardEvaluator` 的 **外层 adapter**，不是替代品
- 当 predicate 只使用 2C 基线 operator 时，直接委托给 `GuardEvaluator.evaluate()`
- 新 operator 在 adapter 层处理
- `GuardEvaluator` 本身代码保持不变

### 5.3 Phase 3 不允许扩展的能力

| 禁止项 | 理由 |
|--------|------|
| 通用字符串表达式解析 (`eval()`) | 航空级安全——显式失败优先 |
| 跨信号算术表达式 (`signal_A + signal_B > X`) | 超出 predicate grammar 设计意图 |
| PID / 积分 / 微分控制逻辑 | 这是 physics simulator 领域 |
| 自定义函数调用 | 通用 evaluator 平台风险 |
| 动态 predicate 构建 / 元编程 | 审计不可追踪 |
| 外部数据源引用 | 超出 local-first 架构 |
| `predicate_expression` 字段复活 | 已冻结 |

### 5.4 与 2C GuardEvaluator 的边界

| 维度 | 2C GuardEvaluator | Phase 3 RicherEvaluator |
|------|------------------|----------------------|
| 定位 | 核心 evaluator | 外层 adapter |
| 代码修改 | 不修改 | 新增独立模块 |
| Operator set | 8 个基线 | 8 + 5~6 个增强 |
| State dependency | stateless | reads RuntimeState.signal_history |
| 失败行为 | EvaluationError | 继承 EvaluationError |
| 测试覆盖 | 2C tests | 3 期新增独立 tests |

---

## 6. Scenario / Replay / Audit Strengthening

### 6.1 Scenario Authoring 增强

#### 6.1.1 Scenario 模板 / 样板生成

**规划**：提供 `templates/scenario.template.yml` 样板文件，而非 GUI authoring studio。

```yaml
# templates/scenario.template.yml
scenario_id: "SCENARIO-XXXX"
title: ""
description: ""
baseline_scope: "demo-scale"
initial_mode_id: "MODE-XXXX"
version: "1.0.0"             # [NEW in Phase 3]
tags: []
ticks:
  - tick_id: 1
    signal_updates:
      IFACE-XXXX.signal_name: 0.0
    notes: ""
```

新增可选字段（向后兼容）：
- `version: str` — scenario 版本控制
- `expected_final_mode: Optional[str]` — 预期终态，用于 regression 检测
- `expected_transitions: Optional[List[str]]` — 预期触发的 transition ID 列表

#### 6.1.2 Scenario Validation（预检）

新模块 `scenario_validator.py` 职责：

| 检查 | 描述 | Tier |
|------|------|------|
| SV-1 | `initial_mode_id` 在 ModeGraph 中存在 | T1 |
| SV-2 | `signal_updates` 中引用的 `IFACE-NNNN.signal` 在 registry 中存在 | T1 |
| SV-3 | `tick_id` 严格递增 | T1 |
| SV-4 | `baseline_scope` 必须是 `"demo-scale"` | T1 |
| SV-5 | 无空 tick（`signal_updates` 为空且 `notes` 为空） | T3 advisory |
| SV-6 | 如有 `expected_final_mode`，检查该 MODE 存在 | T1 |

**不做**：scenario 逻辑正确性预判（这需要执行）。SV 只做结构预检。

### 6.2 Replay 能力

#### 6.2.1 最小 replay 能力定义

**Replay** = 从一个已保存的 `DecisionTrace` 出发，重新执行同一 scenario，验证输出是否一致。

```python
# replay_engine.py 核心接口
class ReplayEngine:
    def replay(
        self, 
        scenario: Scenario, 
        graph: ModeGraph, 
        expected_trace: DecisionTrace
    ) -> ReplayResult:
        """Re-run scenario and compare with expected trace."""
```

`ReplayResult` 包含：
- `match: bool` — 是否完全一致
- `divergence_tick: Optional[int]` — 首次分歧的 tick_id
- `divergence_detail: str` — 分歧描述
- `actual_trace: DecisionTrace` — 实际输出

#### 6.2.2 Trace 持久化

Phase 3 增加 trace 输出到文件的能力：

```
{baseline}/.aplh/traces/
  run_{run_id}_{scenario_id}_{timestamp}.yaml
```

输出格式：`DecisionTrace` 的 Pydantic `.model_dump()` YAML 序列化。

### 6.3 Run/Session Identity

#### 6.3.1 `run_id` 定义

```python
# 生成方式
import uuid
run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
# 例: RUN-3A7F1BC9D2E4
```

#### 6.3.2 `run_id` 传播路径

```
CLI (run-scenario)
    │ generates run_id
    ▼
ScenarioEngine.run_scenario(scenario, run_id)
    │ attaches to RuntimeState
    ▼
DecisionTrace
    │ every TransitionRecord includes run_id
    ▼
Trace persistence
    │ filename includes run_id
    ▼
Signoff entry
    │ review_signoffs.yaml entry includes run_id
```

### 6.4 Audit Correlation

#### 6.4.1 Correlation Model

```
run_id ──── scenario_id ──── signoff_entry
  │              │                 │
  ▼              ▼                 ▼
trace file    scenario file    review_signoffs.yaml
```

`audit_correlator.py` 提供查询接口：

```python
class AuditCorrelator:
    def find_signoffs_for_run(self, run_id: str) -> List[SignoffEntry]
    def find_runs_for_scenario(self, scenario_id: str) -> List[str]
    def find_trace_for_run(self, run_id: str) -> Optional[Path]
    def verify_correlation_integrity(self) -> List[CorrelationIssue]
```

#### 6.4.2 Audit Output Strengthening

增强 `DecisionTrace.to_human_readable()` 输出：

```
=== Scenario Execution Trace ===
Run ID:       RUN-3A7F1BC9D2E4
Scenario ID:  SCENARIO-DEMO
Timestamp:    2026-04-04T21:00:00Z
Baseline:     demo-scale
───────────────────────────────
Tick 1:
  Signals: {...}
  Mode Before: MODE-0001
  ...
================================
```

增加 `to_machine_readable()` 方法，输出结构化 YAML/JSON。

---

## 7. Signoff Audit Enhancement

### 7.1 当前问题（2C 审查点名的 4 项技术债）

| # | 问题 | 位置 | 现状 |
|---|------|------|------|
| TD-1 | `test_signoff_formal_rejected` 为空 pass | `test_phase2c.py` L36-38 | 无实际断言 |
| TD-2 | README Phase Status 过时 | `README.md` L12 | 仍显示 Phase 2A |
| TD-3 | `reviewer` 硬编码 | `cli.py` L451 | `"Demo Reviewer"` |
| TD-4 | `review_signoffs.yaml` 无 `scenario_id` | `cli.py` L449-453 | 仅 `timestamp/reviewer/resolution` |

### 7.2 Signoff 条目最小 Schema

新模块 `models/signoff.py`：

```python
class SignoffEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    timestamp: str          # ISO 8601
    reviewer: str           # 参数化，来自 --reviewer CLI param
    resolution: str         # 审查决议文本
    scenario_id: str        # 关联的 scenario
    run_id: str             # 关联的执行 run
    baseline_scope: str     # "demo-scale" (Phase 3 不允许 formal)
```

### 7.3 技术债清偿方案

#### TD-1: `test_signoff_formal_rejected`

```python
def test_signoff_formal_rejected(tmp_path):
    """Ensure signoff is rejected for formal baseline directory."""
    # Create a fake project root structure pointing to tmp_path as formal
    # Use monkeypatch to override is_formal_baseline_root
    import aero_prop_logic_harness.path_constants as pc
    # Set up: make tmp_path appear as formal root
    (tmp_path / ".aplh").mkdir()
    gate_data = {
        "baseline_scope": "freeze-complete",
        "boundary_frozen": True,
        "schema_frozen": True,
        "trace_gate_passed": True,
        "baseline_review_complete": True,
        "signed_off_by": "Test",
        "signed_off_at": "2026-01-01T00:00:00Z"
    }
    # Write freeze_gate_status.yaml
    import ruamel.yaml
    yaml = ruamel.yaml.YAML()
    with open(tmp_path / ".aplh" / "freeze_gate_status.yaml", "w") as f:
        yaml.dump(gate_data, f)
    
    result = runner.invoke(app, [
        "signoff-demo", 
        "--dir", str(tmp_path),
        "--resolution", "test"
    ])
    # Should be rejected because it's formal
    # (needs monkeypatch for is_formal_baseline_root)
    assert result.exit_code == 1
```

实际实现需要 `monkeypatch` 来伪造 formal root。这是 Phase 3-1 的第一个交付物。

#### TD-2: README Phase Status 更新

将 `README.md` L12 更新为：

```markdown
Currently at **Phase 0 + Phase 1 (Baseline Freeze Candidate) + Phase 2A (Schema Extension) + Phase 2B (Graph/Validation) + Phase 2C (Execution Readiness) — All Accepted**.
```

#### TD-3: `reviewer` 参数化

在 `signoff-demo` CLI 命令中增加 `--reviewer` 参数：

```python
@app.command()
def signoff_demo(
    ...
    reviewer: str = typer.Option(
        ...,
        "--reviewer",
        help="Reviewer identity for the signoff record"
    ),
):
```

`"Demo Reviewer"` 硬编码 → `reviewer` 参数必填。

#### TD-4: `scenario_id` / `run_id` 关联

`signoff-demo` CLI 增加 `--scenario-id` 和 `--run-id` 参数。signoff 条目变为：

```yaml
- timestamp: '2026-04-04T21:00:00Z'
  reviewer: 'Alice Engineer'
  resolution: 'Priority conflict reviewed and accepted'
  scenario_id: 'SCENARIO-DEMO'
  run_id: 'RUN-3A7F1BC9D2E4'
  baseline_scope: 'demo-scale'
```

### 7.4 Signoff 与 baseline-local `.aplh` 的关系

| 规则 | Phase 3 承诺 |
|------|-------------|
| signoff 只写入 demo baseline 的 `.aplh/` | ✅ 保持 |
| formal baseline 拒绝 signoff | ✅ 保持 |
| unmanaged 目录拒绝 signoff | ✅ 保持 |
| signoff 不进入 artifact validation | ✅ `.aplh/` 排除规则不变 |
| signoff 不进入 graph/validator | ✅ signoff 从未被 ModeGraph 或 validators 使用 |

---

## 8. Gate 设计

### Gate P3-A: 2A/2B/2C Frozen Input Preserved

| 维度 | 内容 |
|------|------|
| **输入** | Phase 3 实现代码 + 2A/2B/2C 冻结合同列表 |
| **检查项** | (1) `ModeGraph` 无 `step/fire/evaluate/execute` <br>(2) `TRANS.actions` 不在 `_get_all_embedded_links` 提取范围 <br>(3) 无 `TRANS->FUNC` / `TRANS->IFACE` trace direction <br>(4) `predicate` 仍是唯一权威 <br>(5) `predicate_expression` 未出现 <br>(6) validators 无 evaluator/dispatcher 方法 |
| **通过条件** | 全部检查项通过，无冻结违规 |
| **失败模式** | Phase 3 实现意外修改了 2A/2B/2C 核心模块 |
| **Tier** | T1 — 自动化（grep + structure tests） |
| **边界** | 此 gate 在每个 Phase 3 sub-phase 完成时必须重新执行 |

### Gate P3-B: Enhanced Evaluator Boundary Preserved

| 维度 | 内容 |
|------|------|
| **输入** | `RicherEvaluator` 实现 + operator 枚举 |
| **检查项** | (1) 无 `eval()` / `exec()` / `compile()` 调用 <br>(2) 新 operator 仅在 `RicherEvaluator` adapter 中处理 <br>(3) `GuardEvaluator` 核心代码未修改 <br>(4) 新 operator 有 hard cap 限制（如 `duration_ticks <= 100`） <br>(5) 无跨信号算术表达式 <br>(6) 缺失信号仍 → EvaluationError |
| **通过条件** | 全部检查项通过 |
| **失败模式** | evaluator creep — 能力超出设计边界 |
| **Tier** | T1 — 自动化（structure tests + grep） |

### Gate P3-C: Scenario/Replay/Audit Correlation Integrity

| 维度 | 内容 |
|------|------|
| **输入** | replay 输出 + audit correlation 结果 |
| **检查项** | (1) replay 对同一 scenario 输出确定性一致 <br>(2) `run_id` 贯穿 trace → signoff <br>(3) `scenario_id` 贯穿 scenario → trace → signoff <br>(4) `AuditCorrelator.verify_correlation_integrity()` 无 issue <br>(5) trace 文件可反序列化 |
| **通过条件** | 全部检查项通过 |
| **失败模式** | trace、signoff、scenario 之间的关联断裂 |
| **Tier** | T1 — 自动化（pytest） |

### Gate P3-D: Signoff Audit Completeness

| 维度 | 内容 |
|------|------|
| **输入** | signoff schema + test coverage |
| **检查项** | (1) `SignoffEntry` Pydantic schema 通过 <br>(2) `test_signoff_formal_rejected` 有真实断言 <br>(3) `--reviewer` 参数生效 <br>(4) 每个 signoff 条目含 `scenario_id` + `run_id` <br>(5) 旧格式 signoff 仍可读取（向后兼容） |
| **通过条件** | 全部检查项通过 |
| **失败模式** | signoff schema 不完整或破坏向后兼容 |
| **Tier** | T1 — 自动化（pytest） |

### Gate P3-E: Demo-Scale Enhanced Readiness

| 维度 | 内容 |
|------|------|
| **输入** | 完整 Phase 3 实现 + demo-scale scenarios |
| **检查项** | (1) 至少 3 个不同 scenario 可成功执行 <br>(2) 每个 scenario 有对应的 replay 验证 <br>(3) signoff 链完整 <br>(4) `python -m pytest` 全绿 <br>(5) `validate-modes --coverage` 通过 <br>(6) README 已更新 |
| **通过条件** | 全部检查项通过 |
| **失败模式** | Phase 3 增强在 demo-scale 上不可用 |
| **Tier** | T1（自动化）+ T2（人工 scenario review） |

### Gate P3-F: Future Handoff Package Ready

| 维度 | 内容 |
|------|------|
| **输入** | Phase 3 全部交付物 + 文档 |
| **检查项** | (1) `PHASE3_IMPLEMENTATION_NOTES.md` 完成 <br>(2) Phase 3 → 4 boundary 明确定义 <br>(3) 技术债清单（如有新增）已记录 <br>(4) 无 formal readiness 声称 |
| **通过条件** | 文档完整 + 无误导性声称 |
| **失败模式** | Phase 3 完成但无法交接给 Phase 4 |
| **Tier** | T2（人工审查） |

---

## 9. 开发顺序与里程碑

### Phase 3-1: Technical Debt Closure + Audit Identity

**目标**: 清偿 2C 技术债 + 建立 run/session identity

**交付物**:
1. `test_signoff_formal_rejected` 补全真实断言
2. `README.md` Phase Status 更新到 2C Accepted
3. `signoff-demo` 增加 `--reviewer` 参数
4. `run_id` 生成 + `TransitionRecord` 增加 `run_id` 字段
5. `scenario_id` 贯穿到 signoff 条目
6. `models/signoff.py` 落地

**不做**:
- 不做 richer evaluator
- 不做 replay engine
- 不做 scenario validation

**通过标准**:
- 全部 4 项技术债关闭
- `python -m pytest` 全绿
- Gate P3-A + P3-D 通过

**进入 3-2 条件**: 3-1 Accepted（自审或独立审查）

---

### Phase 3-2: Scenario / Replay Strengthening

**目标**: 增强 scenario 生态系统能力

**交付物**:
1. `scenario_validator.py` — scenario 结构预检
2. `scenario.template.yml` — scenario 模板
3. `replay_engine.py` — deterministic replay
4. trace 持久化到 `.aplh/traces/`
5. `DecisionTrace` 增加 run_id / scenario_id
6. `validate-scenario` CLI 命令
7. `replay-scenario` CLI 命令
8. 至少 3 个新增 demo scenario（覆盖 normal/degraded/emergency 路径）

**不做**:
- 不做 richer evaluator
- 不做 audit correlator（3-3 做）

**通过标准**:
- scenario validation 通过 6 项检查
- replay 对同一 scenario + 同一 graph 输出确定性一致
- 3 个新 scenario 全部可执行
- `python -m pytest` 全绿
- Gate P3-A + P3-C 通过

**进入 3-3 条件**: 3-2 Accepted

---

### Phase 3-3: Evaluator Boundary Enhancement

**目标**: 建立 richer evaluator adapter

**交付物**:
1. `PredicateOperator` 枚举扩展（`DELTA_GT`, `DELTA_LT`, `IN_RANGE` 等）
2. `AtomicPredicate` 增加可选字段（`threshold_high`, `duration_ticks`）
3. `RicherEvaluator` adapter 模块
4. `RuntimeState` 扩展 `signal_history` / `previous_signal_snapshot`
5. 使用新 operator 的 demo scenario
6. 完整的 boundary tests

**不做**:
- 不做通用 DSL
- 不做跨信号算术
- 不做 PID 控制逻辑
- 不做 formal verification

**通过标准**:
- RicherEvaluator 通过 boundary tests
- 旧 scenario 仍正确（backward compatible）
- 无 `eval()` / `exec()` / `compile()`
- `python -m pytest` 全绿
- Gate P3-A + P3-B 通过

**进入 3-4 条件**: 3-3 Accepted

---

### Phase 3-4: Enhanced Demo-Scale Handoff

**Status:** Planning Revision Complete — Awaiting Re-Review (v1.1.0, 2026-04-05)

#### 9.4.1 Phase 3-4 定义

**目标**: 在 2A/2B/2C/3-1/3-2/3-3 已冻结的 schema、静态验证层、demo-scale execution 层、audit identity 层、scenario/replay strengthening 层、richer evaluator boundary 层之上，建立一个 **Enhanced Demo-Scale Handoff Layer**：

1. 把一次 demo-scale run 的输入（scenario source）、运行（execution trace）、判定（evaluator explainability）、回放（replay result）、签署（signoff entry）和验证（baseline validation summary）组织成一个**可交接、可复核的审查证据包 (Handoff Bundle)**
2. 清理 demo baseline 中的测试残留和历史噪音，使之达到**可审计的卫生状态**
3. 提供 **machine-readable index** 和 **human-readable summary**，让审查者不必手工翻找散乱文件
4. 正式纳入并关闭 3-3 审查端遗留的 4 项边界条件
5. 为后续 Phase 4+ (formal readiness) 提供更稳固的 demo-scale 中间层

**非目标 (Out of Scope)**:

| # | 非目标 | 为什么排除 |
|---|--------|-----------| 
| 1 | Formal Baseline Freeze | formal `artifacts/` 仍无 populate 的 Phase 2+ artifacts |
| 2 | Production Runtime / Cert Software | APLH 是开发辅助系统，不是飞控 |
| 3 | GUI / Web Dashboard / Report Platform | 保持 CLI-first + YAML-driven |
| 4 | 将 RicherEvaluator 拆成可扩展框架 | 3-3 硬约束，operator set 是有限封闭的 |
| 5 | 数据库持久化 | 继续使用 `.aplh/` 目录本地文件系统 |
| 6 | 自动化 destructive cleanup | cleanup 必须显式触发，不允许静默删除 |

**为什么 3-4 不是 formal freeze / production runtime / cert package / UI 平台**:
- Formal `artifacts/` 目录当前只包含 P0/P1 artifact 和 demo-set 子目录，无 populated Mode/Transition/Guard
- Demo-scale baseline 虽有 7 个 scenario，但其中 `test.yml` 仍使用废弃信号名
- ScenarioEngine 仍是 demo-level dispatcher，无 formal verification coverage
- Phase 3-4 的增强内容本身需要开发→审查→接受的流程，不能跳过
- handoff package 是审查证据快照，不是认证文件包

**为什么 3-4 必须建立在 2A/2B/2C/3-1/3-2/3-3 冻结输入之上**:
- 3-4 的 handoff bundle 消费的是 3-1 的 SignoffEntry schema、3-2 的 trace persistence / replay reader、3-3 的 evaluator explainability
- 如果回改这些上游 contract，整个 bundle 的关联链失效
- 3-4 是这条 contract chain 的最终消费者，不是重建者

#### 9.4.2 Phase 3-4 模块树

```
aero_prop_logic_harness/
├── services/
│   ├── audit_correlator.py     [核心 NEW]  — trace ↔ signoff ↔ scenario 交叉关联
│   ├── hygiene_manager.py      [核心 NEW]  — orphan trace / legacy signoff 受控清理
│   ├── handoff_builder.py      [核心 NEW]  — bundle assembly + index/summary generation
│   ├── replay_reader.py        [只读依赖]  — list_traces / load_trace / find_trace_by_run_id
│   ├── scenario_engine.py      [只读依赖]  — ScenarioEngine (不修改)
│   ├── richer_evaluator.py     [只读依赖]  — RicherEvaluator (不修改)
│   └── guard_evaluator.py      [冻结]      — GuardEvaluator (不触碰)
│
├── models/
│   └── signoff.py              [只读依赖]  — SignoffEntry schema (不修改)
│
├── cli.py                      [MODIFY]    — 新增 clean-baseline / build-handoff 命令
│
tests/
├── test_phase3_4.py            [NEW]       — 3-4 全部测试
│
docs/
├── PHASE3_IMPLEMENTATION_NOTES.md [MODIFY] — 新增 Phase 3-4 章节
└── README.md                   [MODIFY]    — Phase Status 更新
```

**模块职责矩阵**:

| 模块 | 职责 | 核心/附属 | 禁止延伸 |
|------|------|:---------:|---------|
| `audit_correlator.py` | 从 `.aplh/traces/` 和 `review_signoffs.yaml` 构建 `run_id → {trace_path, signoff_entries, scenario_id}` 映射；提供 `verify_correlation_integrity()` 检查 | 核心 | 不得生成 signoff；不得修改 trace |
| `hygiene_manager.py` | 识别 orphan traces / legacy signoffs / test residue；提供 dry-run + 显式 prune 动作 | 核心 | 不得自动删除；不得碰 formal baseline；不得删源 artifacts |
| `handoff_builder.py` | 读取 correlator 输出 + scenario sources + baseline validation results，组装 bundle 目录 + index.yaml + report.md | 核心 | 不得执行 scenario；不得修改 source traces |
| `cli.py` (extensions) | `clean-baseline` + `build-handoff` 命令入口 | 附属 | 必须继承 `_classify_directory()` 三路径检查 |
| `test_phase3_4.py` | 3-4 全部 gate 自动化测试 | 附属 | — |

**不在 3-4 范围的模块**:

| 模块/能力 | 为什么不在 3-4 |
|-----------|---------------|
| Formal FreezeGateStatus 更新 | formal freeze 不在 Phase 3 范围 |
| HTML/Web report generator | 保持 CLI-first |
| Bundle archive (zip/tar) | 可选能力，不是 MVP；如有时间可在 3-4-4 添加 |
| Scenario execution / replay | 3-2/3-3 已完成，3-4 只读消费 |
| RicherEvaluator 扩展 | 3-3 已冻结 operator set |

#### 9.4.3 2A/2B/2C/3-1/3-2/3-3 → 3-4 数据契约

**Phase 3-4 从上游读取的数据**:

| 数据源 | 读取字段 | 用途 | 写入? |
|--------|---------|------|:-----:|
| `.aplh/traces/run_*.yaml` | `run_id`, `scenario_id`, `records[].tick_id`, `records[].mode_before`, `records[].mode_after`, `records[].transition_selected`, `records[].block_reason`, `records[].applied_signals` | AuditCorrelator 关联索引 + Bundle 打包 | ❌ |
| `.aplh/review_signoffs.yaml` | `timestamp`, `reviewer`, `resolution`, `scenario_id`, `run_id`, `baseline_scope` | AuditCorrelator 关联索引 + Bundle signoff 快照 | ❌ (cleanup 时会从此文件移除 legacy 条目) |
| `scenarios/*.yml` | `scenario_id`, `title`, `version`, `expected_final_mode`, `expected_transitions`, `ticks` | Bundle scenario 快照 | ❌ |
| `ModeGraph.from_registry()` | graph topology (nodes, edges, guards) | baseline_report.txt 中记录 validate-modes 结果 | ❌ |
| `ModeValidator.validate_all()` | validation results | baseline_report.txt | ❌ |
| `CoverageValidator.validate_all()` | coverage results | baseline_report.txt | ❌ |
| `RicherEvaluationResult.steps[]` | `operator`, `signal_ref`, `threshold`, `result`, `reason` | 如果 trace 包含 richer 评估的 block_reason，原样记录到 bundle | ❌ |

**Phase 3-4 忽略的字段**:
- `TRANS.actions` — field-only, 不进入 handoff correlation
- `Function.related_transitions` — 不进入 trace scope
- `TRANS → FUNC` / `TRANS → IFACE` — 不存在，不引入
- `predicate_expression` — 不存在，不引入

**Source-of-Truth 层级**:
```
Level 0 (Ground Truth):   .aplh/traces/*.yaml, review_signoffs.yaml, scenarios/*.yml
Level 1 (Correlation):    AuditCorrelator 内存映射 (runtime only, no persistence)
Level 2 (Bundle Snapshot): .aplh/handoffs/BUNDLE_*/  (point-in-time copy)
Level 3 (Summary):        index.yaml, report.md (machine + human readable)
```
审查者如需验真，必须回到 Level 0。Level 2/3 是便利查看层，不替代 Level 0。

#### 9.4.4 Handoff Package 最小组成 (冻结契约)

一个合法的 handoff bundle 必须包含以下 **全部** 组成部分：

```
{baseline_dir}/.aplh/handoffs/BUNDLE_{YYYYMMDD}_{HHMMSSZ}/
├── index.yaml                          # [必须] Bundle metadata + correlation map
├── report.md                           # [必须] Human-readable summary
├── baseline_report.txt                 # [必须] validate-artifacts + check-trace 输出
├── scenarios/                          # [必须] 打包时的 scenario 快照
│   ├── normal_operation.yml
│   ├── degraded_entry.yml
│   └── ...
├── traces/                             # [必须] 被 correlator 关联的 trace 文件副本
│   ├── run_RUN-XXXX_SCENARIO-YYYY_ZZZZ.yaml
│   └── ...
└── signoffs.yaml                       # [必须] 只包含与本 bundle trace 关联的 signoff 条目
```

**最小骨架验证规则 (Gate P3D-B)**:
- `index.yaml` 存在且可被 `ruamel.yaml` safe-load
- `report.md` 存在且非空
- `baseline_report.txt` 存在
- `scenarios/` 至少包含 1 个 `.yml` 文件
- `traces/` 至少包含 1 个 `run_*.yaml` 文件
- `signoffs.yaml` 存在且至少包含 1 个合规 SignoffEntry
- 每个 `traces/` 中的 `run_id` 在 `signoffs.yaml` 中有对应条目

**Package 形式**: 目录式。不强制 zip/tar（可选 future enhancement）。

**快照与 Source-of-Truth 关系**:
- Bundle 是 **point-in-time snapshot**，不是活文档
- Bundle 生成后，原始 `.aplh/traces/` 和 `review_signoffs.yaml` 依然是 source of truth
- Bundle 内的 `index.yaml` 记录生成时间戳和被打包文件的路径，供审查者追溯

#### 9.4.5 Cleanup / Hygiene 核心契约 (冻结契约)

**定义**:

| 术语 | 定义 | 处理方式 |
|------|------|---------|
| **Orphan Trace** | `.aplh/traces/` 中的 `run_*.yaml` 文件，其 `run_id` 在 `review_signoffs.yaml` 中没有任何合规 SignoffEntry 引用 | 可被 `--prune` 删除 |
| **Legacy Signoff** | `review_signoffs.yaml` 中缺少 `run_id` **或** `scenario_id` 的条目（即 Phase 3-1 schema 升级前的旧格式记录） | 可被 `--prune` 移除 |
| **Test Residue** | 由 CI/pytest/手动测试产生的 trace 和 signoff，其 `reviewer` 为测试值（如 `"Demo Reviewer"`, `"Test"`, `"Review A"`），不代表真实审查 | 标记为 orphan 或 legacy 后同等处理 |

**可删什么**:
- Orphan traces（无对应 signoff 的 trace 文件）
- Legacy signoffs（缺少 run_id/scenario_id 的旧条目）
- 重复的 signoff 条目（同一 run_id 出现多次）

**不可删什么**:
- 被合规 SignoffEntry（含 `run_id` + `scenario_id` + `baseline_scope: "demo-scale"`）关联的 trace 文件
- `scenarios/*.yml` 源文件
- 静态 baseline artifacts（modes, transitions, guards, requirements, interfaces, functions）
- `freeze_gate_status.yaml`
- Formal baseline (`artifacts/`) 下的任何文件

**CLI 行为规范**:

```bash
# Dry-run（只报告，不删除）
python -m aero_prop_logic_harness clean-baseline --dir <demo_dir> --dry-run

# 实际清理（显式确认）
python -m aero_prop_logic_harness clean-baseline --dir <demo_dir> --prune
```

- `--dry-run` 输出: 列出将被删除的 orphan traces、legacy signoffs，以及统计
- `--prune` 输出: 执行删除，输出已删除文件列表和最终状态统计
- Formal baseline → exit 1 ("Cannot clean formal baseline")
- Unmanaged directory → exit 1 ("Unmanaged directory")
- 不支持 `--force` 或 `--yes` 标志（审计系统不允许跳过确认）

**Cleanup 后的最小审计痕迹**:
- `clean-baseline` 执行后，在 `.aplh/` 下写入 `cleanup_log.yaml` 记录：
  - 清理时间戳
  - 被删除的 orphan trace 文件路径列表
  - 被移除的 legacy signoff 条目数量
  - 清理后剩余 trace 数量和 signoff 数量
- `cleanup_log.yaml` 确保清理行为本身可审计

**必须在 3-4 中处理的 4 项技术债**:

**TD-4-1: `test.yml` 与 populated demo baseline 的 mismatch**
- 现状: `test.yml` 使用 `IFACE-0001.test_signal`，但 demo baseline GUARD-0001 引用 `IFACE-0001.N1_Speed`
- 为什么存在: 2C 时 `test.yml` 是最早的 demo scenario，先于 populated demo baseline 落地
- 为什么进入 3-4: 不阻塞 3-3 功能正确性，但阻塞 3-4 的 handoff 包完整性（test.yml 无法成功执行）
- 处理方式: 在 3-4-1 中更新 `test.yml` 信号名为 `IFACE-0001.N1_Speed` 并匹配 demo baseline 拓扑
- 归属: Phase 3-4-1 (baseline hygiene)

**TD-4-2: `.aplh/traces/` 的测试残留**
- 现状: 32 个 trace 文件，绝大多数由 pytest 运行和手动调试产生
- 为什么存在: 3-2/3-3 测试和 CLI 演示不断积累 trace 文件且从未清理
- 为什么进入 3-4: 不影响 3-3 功能，但使 handoff bundle 无法区分真实审查数据和测试噪音
- 处理方式: `hygiene_manager.py` 的 orphan trace detection + `clean-baseline --prune`
- 归属: Phase 3-4-1 (baseline hygiene)

**TD-4-3: `review_signoffs.yaml` 的历史残留**
- 现状: 9 个条目，其中前 2 条缺少 `run_id`/`scenario_id`（旧格式），后 7 条由测试反复生成（大量重复 `reviewer: "Review A"`, `run_id: "RUN-001"`）
- 为什么存在: 3-1 schema 升级后未回溯清理旧条目；CLI 测试不断追加新条目
- 为什么进入 3-4: 混合格式会导致 audit_correlator 的关联查询产生噪音
- 处理方式: `hygiene_manager.py` 的 legacy signoff detection + `clean-baseline --prune`
- 归属: Phase 3-4-1 (baseline hygiene)

**TD-4-4: `HYSTERESIS_BAND` 状态副作用**
- 现状: `RicherEvaluator._eval_hysteresis()` 直接修改 `state.hysteresis_state[sig]`（L400）
- 为什么存在: 3-3 设计决策——hysteresis 本质需要状态记忆，evaluator 是唯一知道何时更新的模块
- 为什么不阻塞 3-3: evaluator 正确性已通过 48 项测试验证，side effect 可控
- 为什么进入 3-4: handoff bundle 的 `report.md` 必须显式披露"哪些 scenario 使用了状态化算子"，否则审查者可能误以为所有评估都是纯函数
- 处理方式: `handoff_builder.py` 在生成 `report.md` 时检测 scenario 是否使用 `HYSTERESIS_BAND` 等状态化 operator，并在 summary 中以 advisory 形式标注
- 归属: Phase 3-4-3 (handoff builder) + 3-4-4 (report generation)

#### 9.4.6 Review Bundle / Summary / Index 结构 (冻结契约)

**Machine-Readable Index (`index.yaml`) 最小字段**:

```yaml
# index.yaml schema
bundle_id: "BUNDLE_20260405_120000Z"
generated_at: "2026-04-05T12:00:00Z"
baseline_dir: "artifacts/examples/minimal_demo_set"
baseline_scope: "demo-scale"

scenarios_included:
  - scenario_id: "SCENARIO-RICHER-DELTA-001"
    source_path: "scenarios/richer_delta_anomaly.yml"
    version: "1.0.0"

runs_included:
  - run_id: "RUN-7EACB8A2F5CF"
    scenario_id: "SCENARIO-RICHER-DELTA-001"
    trace_path: "traces/run_RUN-7EACB8A2F5CF_SCENARIO-RICHER-DELTA-001_20260405T031839Z.yaml"
    evaluator_mode: "richer"   # or "baseline"
    signoff_count: 1
    signoff_reviewers:
      - "Alice Engineer"

validation_summary:
  validate_artifacts: "pass"   # or "fail" with detail
  check_trace: "pass"
  mode_validator: "pass"
  coverage_validator: "pass"

stateful_operator_advisory:
  - scenario_id: "SCENARIO-RICHER-DELTA-001"
    operators_with_side_effects:
      - "hysteresis_band"
    note: "HYSTERESIS_BAND modifies RuntimeState.hysteresis_state during evaluation"
```

**Human-Readable Summary (`report.md`) 最小内容**:
1. Bundle ID 和生成时间
2. Baseline 目录和 scope
3. 包含的 scenario 列表（scenario_id, title, version）
4. 包含的 run 列表（run_id, scenario_id, evaluator_mode, signoff status）
5. Baseline validation 结果摘要
6. **Stateful operator advisory**（明确列出使用 HYSTERESIS_BAND 等有 side effect 的 scenario）
7. Correlation integrity 状态（所有 run 是否都有对应的 trace + signoff）
8. 声明: "本报告基于 Level 0 source-of-truth 生成，审查者如需验真请回到原始 trace/signoff 文件"

**Summary 与 Source-of-Truth 的关系**:
- `report.md` 不是 source-of-truth，只是 Level 3 便利层
- `report.md` 中所有数据均可通过 `index.yaml` 追溯到 Level 0 文件
- 如果 `report.md` 与原始文件不一致，以原始文件为准
- `report.md` 在生成后即为只读快照，不随后续变更更新

#### 9.4.7 Phase 3-4 Gate 设计

**Gate P3D-A: Frozen Input Preserved**

| 维度 | 内容 |
|------|------|
| **输入** | Phase 3-4 代码 + 2A/2B/2C/3-1/3-2/3-3 冻结合同 |
| **检查项** | (1) ModeGraph 无 `step/fire/evaluate/execute` 方法 (2) GuardEvaluator 核心代码未修改 (3) RicherEvaluator 未新增 operator (4) 无 TRANS→FUNC 或 TRANS→IFACE trace direction (5) VALID_TRACE_DIRECTIONS 数量不变 (=25) (6) `predicate_expression` 未出现 (7) Validators 无 evaluator/dispatcher 方法 (8) `TRANS.actions` 不在 consistency scope |
| **通过条件** | 全部检查项通过 |
| **失败模式** | 3-4 实施意外修改了上游冻结模块 |
| **Tier** | T1 — 自动化 (grep + structure tests) |

**Gate P3D-B: Handoff Bundle Completeness**

| 维度 | 内容 |
|------|------|
| **输入** | `build-handoff` 输出目录 |
| **检查项** | (1) `index.yaml` 存在且可 safe-load (2) `report.md` 存在且非空 (3) `baseline_report.txt` 存在 (4) `scenarios/` 至少 1 个 `.yml` (5) `traces/` 至少 1 个 `run_*.yaml` (6) `signoffs.yaml` 至少 1 个合规 entry (7) 每个 trace 的 run_id 在 signoffs 中有对应 |
| **通过条件** | 全部检查项通过 |
| **失败模式** | 生成空包、缺漏组件、关联断裂 |
| **Tier** | T1 — 自动化 (pytest) |

**Gate P3D-C: Trace/Signoff/Replay Correlation Integrity**

| 维度 | 内容 |
|------|------|
| **输入** | `audit_correlator.verify_correlation_integrity()` 返回结果 |
| **检查项** | (1) 每个进入 bundle 的 run_id 有对应 trace 文件存在 (2) 每个进入 bundle 的 run_id 有至少 1 个合规 signoff (3) 每个 signoff 的 scenario_id 与 trace 中的 scenario_id 一致 (4) 无 run_id 冲突或重复 (5) correlator 不存在 "dangling reference" |
| **通过条件** | `verify_correlation_integrity()` 返回空 issues 列表 |
| **失败模式** | trace/signoff 关联链断裂 |
| **Tier** | T1 — 自动化 (pytest) |

**Gate P3D-D: Baseline Hygiene Controlled**

| 维度 | 内容 |
|------|------|
| **输入** | `clean-baseline --dry-run` + `--prune` 输出 |
| **检查项** | (1) `--dry-run` 正确识别 orphan traces (2) `--dry-run` 正确识别 legacy signoffs (3) `--prune` 删除且仅删除 orphan/legacy (4) cleanup_log.yaml 已写入 (5) 合规 trace/signoff 未被误删 (6) formal baseline 运行 → exit 1 拒绝 |
| **通过条件** | dry-run + prune 均正确，无误删 |
| **失败模式** | 误删有效证据 / 未全部清理 / formal 越权 |
| **Tier** | T1 — 自动化 (pytest) |

**Gate P3D-E: Enhanced Demo-Scale Handoff Readiness**

| 维度 | 内容 |
|------|------|
| **输入** | 完整 3-4 实现 + demo baseline |
| **检查项** | (1) `test.yml` 信号名已修正 (2) clean-baseline 已清理残留 (3) 至少 1 个完整链路: run-scenario → signoff → build-handoff → bundle (4) bundle 通过 P3D-B 验证 (5) `python -m pytest` 全绿 (6) README 已更新 |
| **通过条件** | 全部通过 |
| **失败模式** | 3-4 增强在 demo-scale 上不可用 |
| **Tier** | T1 (自动化) + T2 (人工 bundle 内容 review) |

**Gate P3D-F: Formal Boundary Preserved**

| 维度 | 内容 |
|------|------|
| **输入** | `build-handoff --dir artifacts` + `clean-baseline --dir artifacts` |
| **检查项** | (1) `build-handoff --dir artifacts` → exit 1 (2) `clean-baseline --dir artifacts` → exit 1 (3) `build-handoff --dir /tmp` → exit 1 (4) `clean-baseline --dir /tmp` → exit 1 (5) formal baseline 下无 handoff 产物 |
| **通过条件** | formal + unmanaged 均被拒绝 |
| **失败模式** | 3-4 工具误操作 formal baseline |
| **Tier** | T1 — 自动化 (pytest) |

#### 9.4.8 Phase 3-4 开发顺序

**Phase 3-4-1: Baseline Hygiene + Legacy Cleanup**

| 维度 | 内容 |
|------|------|
| **交付物** | (1) `services/hygiene_manager.py` — orphan/legacy 识别 + prune 逻辑 (2) `clean-baseline` CLI 命令 (含 `--dry-run` / `--prune`) (3) 修正 `test.yml` 信号名 (`test_signal` → `N1_Speed`) (4) hygiene gate tests (P3D-D) |
| **不做** | 不做 handoff bundle 构建；不做 correlator；不做 index/report |
| **通过标准** | (1) P3D-D 全部通过 (2) `test.yml` 可被 `run-scenario` 在 demo baseline 上成功执行 (3) `clean-baseline --prune` 清除所有 orphan traces + legacy signoffs (4) cleanup_log.yaml 写入成功 (5) `python -m pytest` 全绿 |
| **进入 3-4-2 条件** | 3-4-1 自审或独立审查通过 |

**Phase 3-4-2: Audit Correlator**

| 维度 | 内容 |
|------|------|
| **交付物** | (1) `services/audit_correlator.py` — 关联查询 (2) correlator integrity tests (P3D-C) |
| **核心 API** | `find_signoffs_for_run(run_id) → List[SignoffEntry]` / `find_runs_for_scenario(scenario_id) → List[str]` / `find_trace_for_run(run_id) → Optional[Path]` / `verify_correlation_integrity() → List[CorrelationIssue]` |
| **不做** | 不做 bundle 构建；不做 index/report；不做 CLI 命令 |
| **通过标准** | (1) P3D-C 全部通过 (2) `verify_correlation_integrity()` 在清理后的 demo baseline 上返回空 issues (3) `python -m pytest` 全绿 |
| **进入 3-4-3 条件** | 3-4-2 自审通过 |

**Phase 3-4-3: Handoff Package Builder**

| 维度 | 内容 |
|------|------|
| **交付物** | (1) `services/handoff_builder.py` — bundle assembly + 目录结构创建 (2) `build-handoff` CLI 命令 (3) bundle completeness tests (P3D-B) |
| **不做** | 不做 index.yaml / report.md 生成（3-4-4 做） |
| **通过标准** | (1) P3D-B 除 index.yaml/report.md 外的检查项通过 (2) bundle 目录结构正确 (3) scenario/trace/signoff 快照完整 (4) `python -m pytest` 全绿 |
| **进入 3-4-4 条件** | 3-4-3 自审通过 |

**Phase 3-4-4: Index/Report Generation + Final Gate Alignment**

| 维度 | 内容 |
|------|------|
| **交付物** | (1) `index.yaml` 生成逻辑 (2) `report.md` 生成逻辑 (含 HYSTERESIS_BAND advisory) (3) `baseline_report.txt` 生成 (4) PHASE3_IMPLEMENTATION_NOTES.md 更新 Phase 3-4 章节 (5) README 最终更新 (6) P3D-A / P3D-E / P3D-F 完整测试 (7) Phase 3 → 4 boundary 明确定义 |
| **不做** | 不做 formal baseline freeze；不做 Phase 4 实施 |
| **通过标准** | (1) 全部 6 个 gate (P3D-A ~ P3D-F) 通过 (2) `python -m pytest` 全绿 (3) 文档完整 (4) 无 formal readiness 声称 (5) 至少 1 个完整 demo handoff bundle 可被生成并通过 correlation check |
| **最终交接条件** | Phase 3-4 Implemented — Pending Independent Review |

#### 9.4.9 仓库现实快照 (2026-04-05 Post-3-3)

本规划基于以下仓库真实状态（Phase 3-3 落地后实际读取）：

| 文件/目录 | 实际状态 | 3-4 影响 |
|-----------|---------|---------|
| `models/predicate.py` | 14 operators (8 baseline + 6 richer)；`_MAX_DURATION_TICKS = 100` | 3-4 不修改 |
| `services/richer_evaluator.py` | 486 行；RicherEvaluator adapter w/ 6 operators + explainability | 3-4 只读消费 explainability 输出 |
| `services/scenario_engine.py` | RuntimeState 含 `previous_signal_snapshot`, `signal_history`, `hysteresis_state`；evaluator injection | 3-4 不修改 |
| `services/guard_evaluator.py` | 8 operator evaluation；核心代码 3-3 期间零修改 | 3-4 不触碰 |
| `services/replay_reader.py` | save_trace / load_trace / list_traces / find_trace_by_run_id + ReplayReader | 3-4 通过 import 消费 |
| `services/decision_tracer.py` | TransitionRecord + DecisionTrace w/ run_id, scenario_id | 3-4 只读消费 |
| `models/signoff.py` | SignoffEntry: `baseline_scope: Literal["demo-scale"]`, ISO 8601 timestamp, `extra="forbid"` | 3-4 只读消费 (用于 legacy detection) |
| `cli.py` | 755 行；8 commands: version, validate-artifacts, check-trace, freeze-readiness, validate-modes, run-scenario, replay-scenario, inspect-run, signoff-demo, validate-scenario；`--richer` flag on run/replay | 3-4 新增 2 commands |
| `scenarios/` | 7 files: test.yml + 3 baseline + 3 richer | 3-4 修正 test.yml |
| `.aplh/traces/` | **32 files** (测试残留) | 3-4 cleanup target |
| `.aplh/review_signoffs.yaml` | **9 entries**: 2 legacy (无 run_id) + 7 test residue | 3-4 cleanup target |
| `artifacts/.aplh/freeze_gate_status.yaml` | `baseline_scope: "freeze-complete"`, all gates = false | 3-4 不触碰 |
| Tests | **278 passed** (162 P0-2C + 25 3-1 + 43 3-2 + 48 3-3) | 3-4 新增 ~30-50 tests |

#### 9.4.10 Phase 3-4 专属实施提示词骨架

```
==================================================
【会话名】
APLH-Phase3-4-Exec

【负责模型】
Opus 4.6
（不可用时平替：Gemini 3.1 Pro；再降级：GLM-5）

【职责类型】
主执行 / Phase 3-4 实施

【角色定义】
你是 APLH Phase 3-4 实施者。
你负责按照 `docs/PHASE3_ARCHITECTURE_PLAN.md` §9.4 规划，
分 4 个子阶段实现 Enhanced Demo-Scale Handoff Layer。

你不能修改 2A/2B/2C/3-1/3-2/3-3 冻结合同。
你不能宣布 formal readiness。
你不能扩展 RicherEvaluator operator set。
你不能做 Phase 4+ 功能。

【唯一目标】
按照 Phase 3-4 规划，分阶段实施：
- 3-4-1: Baseline Hygiene + Legacy Cleanup
- 3-4-2: Audit Correlator
- 3-4-3: Handoff Package Builder
- 3-4-4: Index/Report Generation + Final Gate

每个子阶段完成后，执行对应的 Gate 检查。

【输入上下文】
- docs/PHASE3_ARCHITECTURE_PLAN.md §9.4 (Phase 3-4 规划)
- docs/PHASE3_IMPLEMENTATION_NOTES.md (前置阶段实施记录)
- docs/RICHER_EVALUATOR.md (3-3 operator reference)
- 当前仓库全部 2A/2B/2C/3-1/3-2/3-3 实现

【3-4 专属交付物】
- services/audit_correlator.py  — trace↔signoff↔scenario 交叉关联
- services/hygiene_manager.py   — orphan trace / legacy signoff 受控清理
- services/handoff_builder.py   — bundle assembly + index/report generation
- cli.py extensions             — clean-baseline + build-handoff 命令
- tests/test_phase3_4.py        — 全部 3-4 gate 测试
- test.yml 修正                  — signal name fix
- PHASE3_IMPLEMENTATION_NOTES.md — Phase 3-4 章节
- README.md                     — Phase Status 更新

【3-4 专属技术债处理】
- TD-4-1: test.yml mismatch → 3-4-1 修正
- TD-4-2: 32 orphan traces → 3-4-1 清理
- TD-4-3: 9 legacy/重复 signoffs → 3-4-1 清理
- TD-4-4: HYSTERESIS_BAND side effect → 3-4-4 在 report.md 中标注

【3-4 专属 Gate】
- P3D-A: frozen input preserved
- P3D-B: handoff bundle completeness
- P3D-C: trace/signoff correlation integrity
- P3D-D: baseline hygiene controlled
- P3D-E: enhanced demo-scale handoff readiness
- P3D-F: formal boundary preserved

【3-4 专属开发顺序】
- 3-4-1: hygiene_manager + clean-baseline + test.yml fix
- 3-4-2: audit_correlator + correlation tests
- 3-4-3: handoff_builder + build-handoff + bundle structure
- 3-4-4: index.yaml + report.md + final gates + docs

【3-4 专属禁止事项】
- 不修改 mode_graph.py 的 public API
- 不修改 guard_evaluator.py
- 不修改 richer_evaluator.py（不新增 operator）
- 不引入 eval()/exec()/compile()
- 不引入 GUI / Web UI
- 不声称 formal readiness
- 不做自动 destructive cleanup（必须 explicit CLI）
- 不把 handoff builder 变成报告平台
- 不引入数据库持久化
- 不修改 replay_reader.py 或 scenario_engine.py 核心逻辑

【冻结边界】
- GUARD.predicate 是唯一机器权威字段
- 不引入 predicate_expression
- TRANS.actions field-only
- 不引入 TRANS → FUNC / IFACE trace
- baseline-local .aplh collocation 不变
- ModeGraph 不长出 step/fire/evaluate/execute
- Validators 不变成 evaluator / dispatcher
- RicherEvaluator 不得拆成可扩展框架
- signoff-demo 仍只作用于 demo-scale
- formal baseline 仍未 freeze-complete
==================================================
```

#### 9.4.11 Phase 3-4 风险清单

| 风险 | 描述 | 为什么真实 | 后果 | 缓解策略 |
|------|------|-----------|------|---------|
| **R4-1** | Cleanup 误删有效审计证据 | hygiene_manager 处理 `.aplh/` 目录的真实文件 | 合法 signoff 对应的 trace 丢失，审计链断裂 | orphan 定义严格锁定为"无 signoff 引用"；必须先 `--dry-run`；cleanup_log.yaml 审计痕迹 |
| **R4-2** | Handoff bundle 与源证据脱节 | bundle 是 point-in-time 快照，后续运行/签署不会自动更新 | 审查者看到过时的 bundle | `index.yaml` 记录生成时间戳；report.md 声明快照性质；审查者被引导回 Level 0 |
| **R4-3** | 3-4 回头污染上游 contract | audit_correlator 读取 trace/signoff，存在无意修改的可能 | 2A/2B/2C/3-1/3-2/3-3 审查链失效 | P3D-A 强制检查所有上游模块未修改；correlator/builder 只做 read + copy |
| **R4-4** | index.yaml / report.md 描述漂移 | 生成逻辑的 bug 导致 summary 与实际 trace 不一致 | 审查者基于错误 summary 做出决策 | P3D-C correlation check 验证 index 与源文件一致性 |
| **R4-5** | Formal boundary 被 3-4 工具突破 | 新 CLI 命令如忘记检查 `_classify_directory()` | formal baseline 被不当清理或打包 | P3D-F 专门测试 formal + unmanaged 拒绝路径 |
| **R4-6** | Legacy signoff 与新格式并存导致 correlator 混乱 | `review_signoffs.yaml` 中旧条目无 `run_id` | `find_signoffs_for_run()` 无法匹配 | 3-4-1 先清理 legacy → 3-4-2 correlator 只需处理合规格式 |

---

## 10. 风险清单

### Risk R1: Phase 3 回头污染 2A/2B/2C Contract

| 维度 | 内容 |
|------|------|
| **描述** | Phase 3 实施者修改了 `predicate.py` 核心语义、ModeGraph API、或 validator 逻辑 |
| **为什么真实** | `AtomicPredicate` 需要新增字段（`threshold_high`, `duration_ticks`），存在侵入核心模型的诱惑 |
| **后果** | 2A/2B/2C 已通过的审查结论失效，需要重新审查 |
| **缓解策略** | (1) 新增字段必须是 `Optional`，默认 `None` <br>(2) Gate P3-A 在每个 sub-phase 强制执行 <br>(3) 原有 tests 不允许修改 <br>(4) `GuardEvaluator` 核心代码不修改 |

### Risk R2: Evaluator Creep

| 维度 | 内容 |
|------|------|
| **描述** | RicherEvaluator 持续膨胀，逐步变成通用 DSL / eval 平台 |
| **为什么真实** | "just one more operator" 的诱惑总是存在 |
| **后果** | 审计不可控，安全边界模糊 |
| **缓解策略** | (1) Phase 3 明确规定最多新增 6 个 operator <br>(2) 每个 operator 必须在规划中列名 <br>(3) Gate P3-B 强制检查 <br>(4) 任何超出规划的 operator 需要重新走 planning review |

### Risk R3: Scenario Authoring 无序膨胀

| 维度 | 内容 |
|------|------|
| **描述** | scenario 模板和验证逻辑不断增长，变成 authoring studio |
| **为什么真实** | authoring 能力天然有无限扩展空间 |
| **后果** | 偏离 CLI-first 架构，引入过重的依赖 |
| **缓解策略** | (1) Phase 3 仅提供 YAML template + structural validation <br>(2) 不引入 GUI <br>(3) scenario 数量硬限认知：demo-scale 只需要 3~10 个 |

### Risk R4: Audit / Replay 失联

| 维度 | 内容 |
|------|------|
| **描述** | run_id / scenario_id 传播链断裂，trace 和 signoff 无法关联 |
| **为什么真实** | 多个服务传播 ID，任一环节遗漏就断链 |
| **后果** | 审计能力名存实亡 |
| **缓解策略** | (1) Gate P3-C 自动化检查关联完整性 <br>(2) `AuditCorrelator.verify_correlation_integrity()` 程序化验证 <br>(3) 每个新 scenario 的 CI 必须包含 correlation check |

### Risk R5: Signoff Schema 继续漂移

| 维度 | 内容 |
|------|------|
| **描述** | `review_signoffs.yaml` 格式无 Pydantic schema 约束，持续不受控漂移 |
| **为什么真实** | 当前 signoff 条目是 ad-hoc dict，无 schema 验证 |
| **后果** | 旧条目与新条目格式不一致，correlation 查询失败 |
| **缓解策略** | (1) `SignoffEntry` Pydantic schema 强制落地 <br>(2) CLI 写入时通过 schema 验证 <br>(3) 读取旧条目时容错处理（backward compat） |

### Risk R6: Demo/Formal Boundary 再次污染

| 维度 | 内容 |
|------|------|
| **描述** | Phase 3 增强能力被误用于 formal baseline |
| **为什么真实** | Phase 3 增加了更多 CLI 命令，每个都需要 demo/formal 检查 |
| **后果** | formal baseline 被无保护地执行或 signoff |
| **缓解策略** | (1) 所有新 CLI 命令必须继承 `_classify_directory()` 三路径检查 <br>(2) formal 目录拒绝执行 scenario / signoff / replay <br>(3) tests 覆盖每个新命令的 formal rejection |

---

## 11. 技术债清单与优先级

| # | 技术债 | 来源 | 为什么存在 | 为什么不阻塞 2C | 优先级 | Phase 3 归属 | 子阶段 |
|---|--------|------|-----------|---------------|--------|-------------|--------|
| TD-1 | `test_signoff_formal_rejected` 空 pass | 2C 实施 | formal root spoofing 技术难度导致跳过 | CLI 行为经手动验证正确 | **P0 (最高)** | `tests/test_phase3_signoff.py` | 3-1 |
| TD-2 | README Phase Status 过时 | 2C 实施 | 实施者忘记更新 | 文档不影响代码正确性 | **P1** | `README.md` | 3-1 |
| TD-3 | `reviewer` 硬编码 | 2C 设计决策 | demo-scale 下 reviewer 不关键 | single-reviewer demo 可接受 | **P0** | `cli.py` / `models/signoff.py` | 3-1 |
| TD-4 | `scenario_id` / `run_id` 缺失 | 2C scope 限制 | 2C 只做 demo-scale execution readiness | signoff 初始功能正确 | **P0** | `cli.py` / `models/signoff.py` / `decision_tracer.py` | 3-1 |

**优先级说明**:
- **P0**: 必须在 Phase 3-1 第一轮解决，阻塞后续子阶段
- **P1**: 必须在 Phase 3-1 解决，但不阻塞其他 P0 项

---

## 12. Phase 3 实施提示词骨架

```
==================================================
【会话名】
APLH-Phase3-Exec

【负责模型】
Opus 4.6
（不可用时平替：Gemini 3.1 Pro；再降级：GLM-5）

【职责类型】
主执行 / Phase 3 实施

【角色定义】
你是 APLH Phase 3 实施者。
你负责按照 `docs/PHASE3_ARCHITECTURE_PLAN.md` 规划，
分 4 个子阶段实现 Phase 3 增强层。

你不能修改 2A/2B/2C 冻结合同。
你不能宣布 formal readiness。
你不能实现 Phase 4+ 功能。

【唯一目标】
按照 Phase 3 架构规划包，分阶段实施：
- Phase 3-1: Technical Debt Closure + Audit Identity
- Phase 3-2: Scenario / Replay Strengthening
- Phase 3-3: Evaluator Boundary Enhancement
- Phase 3-4: Enhanced Demo-Scale Handoff

每个子阶段完成后，执行对应的 Gate 检查。

【输入上下文】
- docs/PHASE3_ARCHITECTURE_PLAN.md (本文档)
- docs/PHASE2C_REVIEW_REPORT.md (技术债来源)
- 当前仓库全部 2A/2B/2C 实现

【冻结边界】(复制自本文档 §4.4)
- GUARD.predicate 是唯一机器权威字段
- 不引入 predicate_expression
- TRANS.actions field-only, 不进入 consistency scope
- 不引入 TRANS -> FUNC / IFACE trace
- baseline-local .aplh collocation 不变
- ModeGraph 不长出 step/fire/evaluate/execute
- Validators 不变成 evaluator / dispatcher

【交付物】
- Phase 3-1: TD closure, SignoffEntry schema, run_id
- Phase 3-2: scenario_validator, replay_engine, 3+ scenarios
- Phase 3-3: RicherEvaluator, new operators, boundary tests
- Phase 3-4: audit_correlator, PHASE3_IMPLEMENTATION_NOTES.md

【Gate】
- P3-A through P3-F (详见规划包 §8)

【禁止事项】
- 不修改 mode_graph.py 的 public API
- 不修改 guard_evaluator.py 的核心逻辑
- 不引入 eval()/exec()/compile()
- 不引入 GUI / Web UI
- 不声称 formal readiness
- 不实现 Physics Simulator / PID
- 不引入跨信号算术表达式
==================================================
```

---

## 13. 最终建议

### 13.1 下一轮最适合由哪个会话负责

**建议**: `APLH-Phase3-Exec / Opus 4.6`

**理由**:
1. Phase 3 实施需要对 2A/2B/2C 全部代码有深入理解——Opus 4.6 已在 2B/2C 实施中建立了这个上下文
2. Phase 3-1 是技术债清偿，风险低但需要精确代码修改
3. Phase 3-3 (evaluator) 是技术复杂度最高的部分，需要强推理能力
4. 四个子阶段应在同一个上下文中连续完成，避免上下文切换成本

### 13.2 是否需要中间审查

**建议**: Phase 3-1 完成后进行一次轻量级独立审查（可由 GPT-5.4 执行），验证技术债已正确清偿且无冻结违规。

Phase 3-3 (evaluator) 完成后进行一次独立审查，验证 evaluator boundary 未被突破。

Phase 3-4 完成后进行完整的独立审查。

### 13.3 审查方案

```
APLH-Phase3-Exec (Opus 4.6)
    │
    ├── Phase 3-1 完成 ──→ 轻量审查 (GPT-5.4 或自审)
    ├── Phase 3-2 完成 ──→ 继续 (自审)
    ├── Phase 3-3 完成 ──→ 独立审查 (GPT-5.4)
    └── Phase 3-4 完成 ──→ 完整独立审查 (APLH-Phase3-Review)
```

---

## 附录 A: 参考的仓库真实结构

本规划基于以下仓库内容（2026-04-04 实际读取）：

| 文件 | 行数 | 关键发现 |
|------|:---:|---------|
| `models/scenario.py` | 29 | Scenario/ScenarioTick, extra=forbid, 无 run_id/version |
| `services/guard_evaluator.py` | 86 | 8 operator, AND/OR/NOT, 纯 stateless lookup |
| `services/scenario_engine.py` | 146 | RuntimeState + tick loop + T2 block + 无 run_id |
| `services/decision_tracer.py` | 42 | TransitionRecord + human-readable, 无 run_id/scenario_id |
| `services/mode_graph.py` | 118 | 只读图, 无 step/fire/evaluate/execute |
| `validators/mode_validator.py` | 280 | 12 项结构检查, T1/T3 分层 |
| `validators/coverage_validator.py` | 165 | ABN coverage + degraded recovery + emergency |
| `validators/consistency_validator.py` | 201 | embedded links + governance rules + reverse loop |
| `cli.py` | 483 | 6 commands, _classify_directory, reviewer 硬编码 |
| `models/predicate.py` | 192 | 8 operators, SIGNAL_REF_PATTERN, 注释 "Phase 3+" |
| `models/trace.py` | 144 | 25 trace directions, 无 TRANS->FUNC/IFACE |
| `tests/test_phase2c.py` | 123 | 7 tests, test_signoff_formal_rejected = pass |
| `review_signoffs.yaml` | 7 | 2 entries, 无 scenario_id/run_id |
| `scenarios/test.yml` | 9 | 1 scenario, 1 tick, minimal |
| `README.md` | 86 | Phase Status = "Phase 2A" (过时) |
| `docs/PHASE2C_REVIEW_REPORT.md` | 446 | 4 项技术债, Phase 2C Accepted |
| `docs/REVIEW_GATES.md` | 192 | Gate A-E, demo/formal 两级治理 |
| `docs/ARTIFACT_MODEL.md` | 116 | 9 types, Phase 3+ extension points 列出 |

所有判断均基于上述实际代码，无推测成分。

## 附录 B: 不确定性声明

| 不确定性 | 假设 | 风险 |
|---------|------|------|
| `AtomicPredicate` 新增 Optional 字段是否破坏 JSON Schema 导出 | 假设 Pydantic Optional field 向后兼容 | 需要实施时验证 schema export |
| `review_signoffs.yaml` 旧格式读取兼容性 | 假设可通过 try/except 容错 | 可能需要迁移脚本 |
| `RicherEvaluator` adapter 模式在性能上是否可接受 | 假设 demo-scale 下性能不是问题 | formal-scale 可能需要优化 |
| `replay_engine` 确定性取决于 float 精度 | 假设 Pydantic float 序列化/反序列化一致 | 可能需要 tolerance 参数 |

---

*本文档为 Phase 3 架构规划，不构成 Phase 3 实现。任何实施须经主控会话批准后启动。*
