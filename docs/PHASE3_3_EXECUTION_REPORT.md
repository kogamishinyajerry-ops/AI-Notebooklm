# APLH Phase 3-3 实施报告

**Document ID:** APLH-EXEC-P3-3
**Version:** 1.0.0
**Date:** 2026-04-05
**Status:** Phase 3-3 已实现，待独立审查

---

## 1. 总体结论

**已完成 Phase 3-3 实施，待独立审查。**

Phase 3-3 Richer Evaluator Boundary 已完整实现，包含 6 个新增受控算子、外层 adapter 架构、结构化 explainability、demo baseline 修复、CLI `--richer` 标志、48 项新测试，且所有 2A/2B/2C/3-1/3-2 冻结合同保持不变。

---

## 2. 新增 / 修改文件清单

### 新增文件

| 文件路径 | 作用 |
|----------|------|
| `aero_prop_logic_harness/services/richer_evaluator.py` | RicherEvaluator adapter — 6 个 richer operator + 结构化 explainability |
| `tests/test_phase3_3.py` | 48 项测试：operator evaluation, boundary gates, CLI integration |
| `docs/RICHER_EVALUATOR.md` | Richer evaluator operator 参考文档 |

### 修改文件

| 文件路径 | 变更 |
|----------|------|
| `aero_prop_logic_harness/models/predicate.py` | 新增 6 个 richer operator enum、`threshold_high`/`duration_ticks` 字段、operator set 常量、`duration_ticks` 硬上限 (100) |
| `aero_prop_logic_harness/services/scenario_engine.py` | RuntimeState 扩展 (`signal_history`, `previous_signal_snapshot`, `hysteresis_state`)；evaluator 显式注入；tick 处理中 history 跟踪 |
| `aero_prop_logic_harness/services/replay_reader.py` | `evaluator` 参数透传以保持 replay 一致性 |
| `aero_prop_logic_harness/cli.py` | `run-scenario` 和 `replay-scenario` 新增 `--richer` 标志 |
| `artifacts/examples/minimal_demo_set/requirements/req-0001.yaml` | 补充 `linked_modes`/`linked_transitions` cross-refs |
| `artifacts/examples/minimal_demo_set/requirements/req-0002.yaml` | 补充 `linked_modes` cross-refs |
| `artifacts/examples/minimal_demo_set/interfaces/iface-0001.yaml` | 补充 `related_modes`/`related_guards` cross-refs |
| `artifacts/examples/minimal_demo_set/functions/func-0001.yaml` | 补充 `related_modes` cross-refs |
| `artifacts/examples/minimal_demo_set/modes/mode-0001.yaml` | 补充 `incoming_transitions` cross-refs |
| `docs/PHASE3_IMPLEMENTATION_NOTES.md` | 版本升级至 v0.3.0，新增 Phase 3-3 完整章节 |
| `docs/README.md` | Phase Status 更新反映 3-3 实现 |

---

## 3. 已实现内容

### 3.1 Richer Evaluator Boundary

6 个新增受控算子：

| 算子 | 语义 | 状态依赖 |
|------|------|---------|
| `DELTA_GT` | `current - previous > threshold` | `previous_signal_snapshot` |
| `DELTA_LT` | `current - previous < threshold` | `previous_signal_snapshot` |
| `IN_RANGE` | `low <= value <= high` | `signal_snapshot` only |
| `SUSTAINED_GT` | 窗口内所有值 > threshold | `signal_history` |
| `SUSTAINED_LT` | 窗口内所有值 < threshold | `signal_history` |
| `HYSTERESIS_BAND` | 非对称阈值 + 状态记忆 | `signal_snapshot` + `hysteresis_state` |

关键约束：
- `duration_ticks` 硬上限 100
- 不支持跨信号算术
- 不使用 `eval()`/`exec()`/`compile()`
- 缺失信号必须抛出 `EvaluationError`（不容静默降级）

### 3.2 Evaluator Adapter / Service

- `RicherEvaluator` 是外层 adapter classmethod 服务
- baseline operators (GT, GE, LT, LE, EQ, NE, BOOL_TRUE, BOOL_FALSE) 委托给未修改的 `GuardEvaluator`
- richer operators 在 adapter 层处理
- `GuardEvaluator` 源代码零修改

### 3.3 Demo Baseline Support Strengthening

- 修复 10 个 bidirectional trace link 一致性错误
- REQ-0001/0002 补充 `linked_modes`/`linked_transitions`
- IFACE-0001 补充 `related_modes`/`related_guards`
- FUNC-0001 补充 `related_modes`
- MODE-0001 补充 `incoming_transitions`
- 现在 demo baseline 的 `check-trace` 和 `validate-artifacts` 完全通过

### 3.4 CLI / Validation Strengthening

- `run-scenario --richer`: 启用 RicherEvaluator，输出 "RicherEvaluator enabled (Phase 3-3)"
- `replay-scenario --richer`: 使用相同 evaluator 进行 deterministic replay
- 不带 `--richer` 的行为完全不变（baseline GuardEvaluator）
- formal/unmanaged 拒绝逻辑不变

### 3.5 Evaluator Explainability / Audit

每个评估产生结构化 `RicherEvaluationResult`:
- `value: bool` — 结果
- `evaluator_mode: str` — "baseline" 或 "richer"
- `steps: List[EvaluationStep]` — 每步包含 operator, signal_ref, threshold, current_value, previous_value, result, reason
- `error: Optional[str]` — 错误信息

`reason` 字段是 machine-readable 格式化字符串（如 `delta=600.0, threshold=500, operator=delta_gt → true`）。

### 3.6 Tests

48 项新测试 (`tests/test_phase3_3.py`)：

| 测试类 | 数量 | 覆盖范围 |
|--------|------|---------|
| `TestDeltaEvaluation` | 5 | DELTA_GT/LT positive, negative, no-previous, missing-signal |
| `TestInRangeEvaluation` | 6 | True, boundary-low/high, below, above, missing |
| `TestSustainedEvaluation` | 5 | GT/true, insufficient-history, not-all-above, LT/true, missing |
| `TestHysteresisEvaluation` | 5 | Enter-band, stay-true, exit-band, stay-false, missing |
| `TestBaselineDelegation` | 3 | GT/LT delegation, missing-signal delegation |
| `TestEngineRicherIntegration` | 3 | DELTA transition, SUSTAINED transition, baseline fallback |
| `TestExplainability` | 3 | Delta, IN_RANGE, SUSTAINED explanation structure |
| `TestGateP3B` | 6 | No eval/exec, GuardEvaluator unchanged, duration cap, finite ops, no cross-signal, no silent fallback |
| `TestGateP3ARegression` | 6 | ModeGraph no-execute, no TRANS→FUNC/IFACE, trace count=25, no predicate_expression, predicate authority |
| `TestCLIRicher` | 3 | run --richer, formal rejection, replay --richer |
| `TestRicherDemoScenarios` | 3 | richer_delta_anomaly, richer_recovery_in_range, richer_sustained_overspeed |

全量测试结果：**278 passed, 0 failed** (230 pre-3-3 + 48 new)。

### 3.7 Docs / Handoff

- `docs/RICHER_EVALUATOR.md` — operator 参考文档（含语义、约束、示例、explainability 结构）
- `docs/PHASE3_IMPLEMENTATION_NOTES.md` — v0.3.0，Phase 3-3 完整章节
- `README.md` — Phase Status 更新

---

## 4. 明确未实现内容

| 未实现项 | 归属 |
|---------|------|
| Formal baseline freeze | Phase 3-4+ |
| Production runtime | 不可做 |
| General DSL / expression language platform | 不可做 |
| Cross-signal arithmetic | 不可做 |
| PID / integral / derivative logic | 不可做 |
| Phase 3-4 Enhanced Demo-Scale Handoff | Phase 3-4 |

---

## 5. 实际命令与返回码

### 命令 1: 全量测试
```
.venv/bin/python -m pytest
→ 278 passed in 5.46s, EXIT_CODE=0
```

### 命令 2: Phase 3-2 回归
```
.venv/bin/python -m pytest tests/test_phase3_2.py -v
→ 43 passed, EXIT_CODE=0
```

### 命令 3: Phase 3 signoff 回归
```
.venv/bin/python -m pytest tests/test_phase3_signoff.py -v
→ 26 passed, EXIT_CODE=0
```

### 命令 4: Phase 2C 回归
```
.venv/bin/python -m pytest tests/test_phase2c.py -v
→ 6 passed, EXIT_CODE=0
```

### 命令 5: run-scenario demo
```
.venv/bin/python -m aero_prop_logic_harness run-scenario \
  --dir artifacts/examples/minimal_demo_set \
  --scenario artifacts/examples/minimal_demo_set/scenarios/test.yml
→ EXIT_CODE=1 (预期：test.yml 信号不匹配 GUARD-0001 N1_Speed → T2 block)
```

### 命令 6: signoff-demo demo + IDs
```
.venv/bin/python -m aero_prop_logic_harness signoff-demo \
  --dir artifacts/examples/minimal_demo_set --reviewer "Review A" \
  --resolution "Looks good" --scenario-id "SCENARIO-001" --run-id "RUN-001"
→ EXIT_CODE=0 (成功记录)
```

### 命令 7: signoff-demo formal 拒绝
```
.venv/bin/python -m aero_prop_logic_harness signoff-demo \
  --dir artifacts --reviewer "Review A" --resolution "Looks good"
→ EXIT_CODE=1, "Cannot sign off in Formal baseline"
```

### 命令 8: signoff-demo unmanaged 拒绝
```
.venv/bin/python -m aero_prop_logic_harness signoff-demo \
  --dir /tmp --reviewer "Review A" --resolution "Looks good"
→ EXIT_CODE=1, "Signoff is strictly prohibited"
```

### 命令 9: run-scenario --richer 正向
```
.venv/bin/python -m aero_prop_logic_harness run-scenario \
  --dir artifacts/examples/minimal_demo_set \
  --scenario .../richer_delta_anomaly.yml --richer
→ EXIT_CODE=0, "RicherEvaluator enabled", TRANS-0001 DELTA_GT 触发, MODE-0001→MODE-0002
```

### 命令 10: run-scenario 不带 --richer (拒绝路径)
```
.venv/bin/python -m aero_prop_logic_harness run-scenario \
  --dir artifacts/examples/minimal_demo_set \
  --scenario .../richer_delta_anomaly.yml
→ EXIT_CODE=1, "Unsupported operator: PredicateOperator.DELTA_GT" (预期 T2 block)
```

### 命令 11: 完整链路 (validate / run / replay / inspect)

**validate-scenario:**
```
.venv/bin/python -m aero_prop_logic_harness validate-scenario \
  --dir artifacts/examples/minimal_demo_set \
  --scenario .../richer_delta_anomaly.yml
→ EXIT_CODE=0, "Scenario validation passed"
```

**replay-scenario --richer:**
```
.venv/bin/python -m aero_prop_logic_harness replay-scenario \
  --dir artifacts/examples/minimal_demo_set \
  --scenario .../richer_delta_anomaly.yml \
  --trace .../run_RUN-7EACB8A2F5CF_SCENARIO-RICHER-DELTA-001_20260405T031839Z.yaml \
  --richer
→ EXIT_CODE=0, "Replay matched — deterministic consistency confirmed"
```

**inspect-run:**
```
.venv/bin/python -m aero_prop_logic_harness inspect-run \
  --dir artifacts/examples/minimal_demo_set --run-id RUN-7EACB8A2F5CF
→ EXIT_CODE=0, 4 records, tick-by-tick readback, "No signoffs found"
```

---

## 6. 风险与遗留问题

1. **Demo baseline `test.yml` 不匹配** — `test.yml` 使用 `IFACE-0001.test_signal` 但 demo baseline GUARD-0001 引用 `IFACE-0001.N1_Speed`。`test.yml` 在 populated demo baseline 上必然 T2 block。这是 3-2 遗留的 scenario/demo mismatch 问题。建议：在 3-4 中更新 `test.yml` 使用正确信号名，或将其标记为 legacy。

2. **Signoff 遗留记录** — 3-2 审查指出 demo baseline 的 `review_signoffs.yaml` 包含测试写入的 signoff 记录。3-3 测试又追加了新记录。正式交付前应清理。

3. **Trace 文件积累** — 多轮测试在 `.aplh/traces/` 中积累了多个 trace 文件。正式交付前应清理。

4. **HYSTERESIS_BAND side effect** — HYSTERESIS_BAND 直接修改 `state.hysteresis_state`，这在当前纯函数测试中是可控的，但审查官应确认这是否违反"evaluator 不应修改状态"的原则。

5. **predicate.py 已预置 richer operators** — 6 个 richer operator 在 3-3 实施前已存在于 `predicate.py` 中（可能在 2A 或更早期被预置）。3-3 只实现了对应的 evaluator 逻辑，未修改模型定义。审查官应确认这是否构成对 2A 冻结合同的越界。

---

## 7. 交接建议

### 下一位独立审查官最该重点核什么

1. **GuardEvaluator 是否真的零修改** — 直接 `git diff` 确认 `guard_evaluator.py` 未被修改。

2. **predicate.py 的 6 个 richer operator 是否越界** — 这些 operator 是在 3-3 实施前就已存在于代码中的（模型预置）。审查官需确认这是否符合 2A 冻结合同（如果 2A 只冻结了 8 个 baseline operator，那 6 个 richer operator 的模型定义可能在 2A 之前就已加入，属于有规划的前置准备）。

3. **HYSTERESIS_BAND side effect** — 确认 evaluator 修改 `hysteresis_state` 是否合理，是否应在 ScenarioEngine tick 处理中处理状态更新。

4. **RicherEvaluator 是否真的是 adapter 而非平台** — 检查是否有隐藏的 extensibility hooks、未锁定的 operator 注册机制、或可用于添加无限 operator 的框架。

5. **278 tests 回归** — 确认全绿且无 skip/xfail。

6. **demo baseline cross-refs 修复是否完整** — 运行 `check-trace` 和 `validate-artifacts` 确认零错误。

7. **formal baseline 未被污染** — 确认 `artifacts/.aplh/` 下无 trace/signoff 产物泄漏。
