# 《APLH Phase 3-2 独立实施审查报告》

**Document ID:** APLH-REV-P32
**Version:** 1.0.0
**Date:** 2026-04-05
**Reviewer:** Phase 3-2 Independent Review Agent
**Conclusion:** Phase 3-2 Accepted

---

## 1. 总体结论

**Phase 3-2 Accepted。**

当前仓库已正确、克制、无越界地完成"Phase 3-2：Scenario / Replay / Audit Strengthening"。所有核心交付物已落地，冻结边界完整保留，CLI 行为符合 demo/formal/unmanaged 合同，测试全绿（230 passed），文档更新正确。

**是否支持进入 Phase 3-3 准备阶段：是**（附带边界条件，见第 6 节）。

---

## 2. 审查范围

### 2.1 读取的文件

| 文件 | 用途 |
|------|------|
| `docs/PHASE3_IMPLEMENTATION_NOTES.md` | 3-2 执行自报 |
| `docs/SCENARIO_FORMAT.md` | Scenario 格式文档 |
| `README.md` | 项目状态与 CLI 文档 |
| `aero_prop_logic_harness/models/scenario.py` | Scenario/ScenarioTick 模型 |
| `aero_prop_logic_harness/models/signoff.py` | SignoffEntry schema |
| `aero_prop_logic_harness/services/scenario_validator.py` | SV-1~SV-6 结构化检查 |
| `aero_prop_logic_harness/services/replay_reader.py` | Trace 持久化 + ReplayReader |
| `aero_prop_logic_harness/services/decision_tracer.py` | DecisionTrace/TransitionRecord |
| `aero_prop_logic_harness/services/scenario_engine.py` | ScenarioEngine + RuntimeState |
| `aero_prop_logic_harness/services/mode_graph.py` | 只读图视图（冻结边界验证） |
| `aero_prop_logic_harness/services/guard_evaluator.py` | 安全谓词评估器（冻结边界验证） |
| `aero_prop_logic_harness/validators/consistency_validator.py` | 一致性验证器（冻结边界验证） |
| `aero_prop_logic_harness/validators/mode_validator.py` | 模式验证器（冻结边界验证） |
| `aero_prop_logic_harness/validators/coverage_validator.py` | 覆盖率验证器（冻结边界验证） |
| `aero_prop_logic_harness/models/trace.py` | TraceLink / VALID_TRACE_DIRECTIONS |
| `aero_prop_logic_harness/cli.py` | 全部 CLI 命令 |
| `aero_prop_logic_harness/path_constants.py` | 路径常量与 artifact scanning 规则 |
| `tests/test_phase3_2.py` | 3-2 测试套件（43 项） |
| `templates/scenario.template.yml` | Scenario 模板 |
| `artifacts/examples/minimal_demo_set/scenarios/test.yml` | 原有 demo scenario |
| `artifacts/examples/minimal_demo_set/scenarios/normal_operation.yml` | 新增 demo scenario |
| `artifacts/examples/minimal_demo_set/scenarios/degraded_entry.yml` | 新增 demo scenario |
| `artifacts/examples/minimal_demo_set/scenarios/emergency_shutdown.yml` | 新增 demo scenario |
| `artifacts/examples/minimal_demo_set/.aplh/review_signoffs.yaml` | signoff 关联验证 |

### 2.2 执行的命令（全部通过 venv Python 3.11.15）

| # | 命令 | 返回码 | 结果 |
|---|------|--------|------|
| 1 | `.venv/bin/python -m pytest` | **0** | 230 passed |
| 2 | `.venv/bin/python -m pytest tests/test_phase3_2.py -v` | **0** | 43 passed（SV-1~6、Replay、Trace Persistence、Audit Correlation、CLI、Gate P3-A、Demo Scenarios） |
| 3 | `.venv/bin/python -m pytest tests/test_phase3_signoff.py -v` | **0** | 26 passed |
| 4 | `.venv/bin/python -m pytest tests/test_phase2c.py -v` | **0** | 6 passed |
| 5 | `run-scenario --dir minimal_demo_set --scenario test.yml` | **0** | 场景执行成功，trace 持久化到 `.aplh/traces/` |
| 6 | `signoff-demo --dir minimal_demo_set --reviewer "Review A" --resolution "Looks good" --scenario-id "SCENARIO-001" --run-id "RUN-001"` | **0** | signoff 写入成功 |
| 7 | `signoff-demo --dir artifacts --resolution "Looks good"` | **1** | "Cannot sign off in Formal baseline" ✅ |
| 8 | `signoff-demo --dir /tmp --resolution "Looks good"` | **1** | "Unmanaged Environment Error" ✅ |
| 9 | `validate-scenario --dir minimal_demo_set --scenario test.yml` | **1** | SV-1 fail（空 ModeGraph，正确行为） |
| 10 | `replay-scenario --dir minimal_demo_set --scenario test.yml --trace <latest>` | **0** | "Replay matched — deterministic consistency confirmed" |
| 11 | `inspect-run --dir minimal_demo_set --run-id RUN-445CA019F978` | **0** | 显示 tick-by-tick readback + signoff 关联查询 |

### 2.3 反证攻击

| # | 攻击 | 结果 |
|---|------|------|
| 1 | 冻结边界污染：ModeGraph 无 step/fire/evaluate/execute，validators 无变化 | ✅ 通过 |
| 2 | Replay 第二引擎：`replay_and_compare` 委托 `ScenarioEngine(graph)`，无独立 transition resolution | ✅ 通过 |
| 3 | Scenario .yml 防撞：`iter_artifact_yamls` 只 glob `*.yaml`，`.yml` 不被扫描 | ✅ 通过 |
| 4 | CLI 作用域：validate-scenario / replay-scenario / inspect-run 全部拒绝 Formal 目录（exit 1） | ✅ 通过 |
| 5 | Audit 关联失联：run_id 贯通 trace → inspect → signoff；inspect-run 查询 review_signoffs.yaml 中匹配条目 | ✅ 通过 |
| 6 | Demo baseline 现实错位：validate-scenario 因空 ModeGraph 返回 SV-1 fail = 正确行为（如实反映仓库状态） | ✅ 通过 |

---

## 3. 十二项审查结果

### 3.1 是否严格停留在 Phase 3-2 — **通过**

**证据：**
- `PHASE3_IMPLEMENTATION_NOTES.md` 明确列出 Scope Exclusions（3-3 richer evaluator boundary、3-4 enhanced handoff、formal baseline freeze）
- Phase 3-3 和 3-4 标记为"Not started — awaiting 3-2 acceptance"
- 未发现任何 evaluator boundary / formal freeze / production runtime 痕迹
- `grep "evaluator\|simulator\|freeze.complete\|Phase.?3\|authoring"` 在 services 目录仅命中注释和文档

### 3.2 Scenario authoring / validation 是否正确落地 — **通过**

**证据：**
- `scenario.py` 增加 3 个 Optional 字段（`version` / `expected_final_mode` / `expected_transitions`），全部默认 `None`，向后兼容
- `ScenarioValidator` 实现 6 项检查（SV-1~SV-6），全部是**结构化只读检查**
- SV-1: initial_mode_id ∈ ModeGraph.nodes
- SV-2: signal_updates keys 匹配 `IFACE-[0-9]{4}\.\w+`
- SV-3: tick_id 严格递增
- SV-4: baseline_scope == "demo-scale"
- SV-5: 空 tick 为 advisory warning
- SV-6: expected_final_mode（若存在）∈ ModeGraph.nodes
- validation 和 execution 严格分离——ScenarioValidator 不调用 ScenarioEngine

**代码位置：** `scenario_validator.py:68-88`（`validate` 方法调用 6 个 `_check_svN` 方法）

### 3.3 ReplayReader 是否真的是 readback — **通过**

**证据：**
- `ReplayReader.readback` 仅遍历 `trace.records` 提取字段到 dict 列表——纯读取
- `ReplayReader.replay_and_compare` 第 168-169 行：`engine = ScenarioEngine(graph); actual_trace = engine.run_scenario(scenario)`——委托 ScenarioEngine，无独立 transition resolution
- 比较逻辑逐 tick 比较 tick_id / mode_before / mode_after / transition_selected / block_reason（presence）

**代码位置：** `replay_reader.py:132-261`

### 3.4 Trace 持久化是否正确落地 — **通过**

**证据：**
- `save_trace` 写入 `{baseline_dir}/.aplh/traces/run_{run_id}_{scenario_id}_{timestamp}.yaml`
- `load_trace` 使用 `ruamel.yaml.YAML(typ="safe")` 安全加载
- `list_traces` 返回 `.aplh/traces/run_*.yaml` 列表
- `find_trace_by_run_id` 先匹配文件名、再降级读取文件内容
- YAML round-trip 测试 `test_save_and_load_roundtrip` 验证了完整序列化/反序列化
- 命令 5 实际运行后确认 4 个 trace 文件已落地

**代码位置：** `replay_reader.py:34-105`

### 3.5 Audit correlation 是否闭环 — **通过**

**证据：**
- `run_id` 生成于 `ScenarioEngine.generate_run_id()`（`RUN-{uuid.hex[:12].upper()}`）
- `run_id` / `scenario_id` 贯穿 `DecisionTrace` → `TransitionRecord` → `save_trace` → `load_trace`
- `SignoffEntry` 通过 `--scenario-id` / `--run-id` CLI 参数写入 `.aplh/review_signoffs.yaml`
- `inspect-run` CLI 读取 `review_signoffs.yaml` 查找匹配 `run_id` 的 signoff 条目
- 测试 `test_signoff_and_trace_share_run_id` 验证了 trace → signoff 关联
- 命令 11 实际运行确认 inspect-run 输出 "No signoffs found for run_id RUN-445CA019F978"（该 run 确无 signoff，正确）

**代码位置：** `cli.py:623-641`（inspect-run signoff correlation）

### 3.6 CLI strengthening 是否按合同实现 — **通过**

**证据：**
- `validate-scenario`（cli.py:429-483）：加载 scenario + ModeGraph → ScenarioValidator.validate → 输出 report
- `replay-scenario`（cli.py:486-566）：加载 scenario + expected trace → ReplayReader.replay_and_compare → 输出结果
- `inspect-run`（cli.py:569-641）：find_trace_by_run_id → load_trace → ReplayReader.readback → signoff correlation
- `run-scenario`（cli.py:352-425）：增加 Phase 3-2 trace 持久化（仅 demo-scale）
- 原有 `validate-modes` / `signoff-demo` / `validate-artifacts` 未被修改
- 所有新增命令在 Formal 目录返回 exit 1

### 3.7 demo/formal/unmanaged 边界 — **通过**

**证据：**
- `_classify_directory` 对 Formal / Demo-scale / Unmanaged 的判定逻辑未变
- `validate-scenario --dir artifacts` → "Formal directory scenario validation is not allowed" (exit 1) ✅
- `replay-scenario --dir artifacts` → "Formal directory replay is not allowed" (exit 1) ✅
- `inspect-run --dir artifacts` → "Formal directory inspection is not allowed" (exit 1) ✅
- `signoff-demo --dir artifacts` → "Cannot sign off in Formal baseline" (exit 1) ✅
- `signoff-demo --dir /tmp` → "Unmanaged Environment Error" (exit 1) ✅

### 3.8 测试是否真实、充分、无越界 — **通过**

**证据：**
- `test_phase3_2.py`：43 项测试，覆盖 ScenarioValidator (13)、ReplayReader (3)、TracePersistence (5)、AuditCorrelation (4)、ScenarioModelCompat (2)、CLI (7)、GateP3A (6)、DemoScenarios (4)
- `test_phase3_signoff.py`：26 项测试（3-1 交付）
- `test_phase2c.py`：6 项测试（2C 回归）
- 全量 230 passed，0 failed
- Gate P3-A 测试明确检查：ModeGraph 无 execute 方法、GuardEvaluator 未变、无 TRANS→FUNC/IFACE、VALID_TRACE_DIRECTIONS 仍为 25

### 3.9 docs / handoff 是否正确更新 — **通过**

**证据：**
- `README.md` Phase Status 已更新为 "Phase 3-2 Implemented, pending review"
- `docs/PHASE3_IMPLEMENTATION_NOTES.md` 记录了全部新增/修改文件、架构决策、Scope Exclusions
- `docs/SCENARIO_FORMAT.md` 提供 scenario 格式完整说明（字段表、SV-1~SV-6 检查说明）
- `templates/scenario.template.yml` 提供了带注释的 authoring 模板
- 文档没有偷换为"Phase 3 已完成"

### 3.10 demo scenarios 与仓库现实 — **部分通过**（非阻断）

**证据：**
- 4 个 demo scenario（test.yml + 3 个新增）全部可正确解析为 Scenario 对象（测试验证）
- 所有 scenario 引用 `MODE-0001`，但 demo baseline 当前无 Phase 2 artifacts（空 ModeGraph）
- `validate-scenario` 返回 SV-1 fail（initial_mode_id not in ModeGraph）——这是**正确行为**，如实反映仓库状态
- 3 个新增 scenario 使用了 Phase 3-2 optional 字段（version、tags、notes），验证了向后兼容性

**风险判断：** 当前 demo set 无法展示完整的 scenario validation 全流程（需要 populated ModeGraph）。这不构成 3-2 阻断，但 Phase 3-3 应补充有 Phase 2 artifacts 的 demo baseline。

### 3.11 环境说明是否构成阻断 — **通过**

**证据：**
- `.venv/bin/python` 为 Python 3.11.15，项目要求 3.11+
- 全部 11 条命令通过 `.venv/bin/python` 执行，返回码全部符合预期
- 不存在环境阻断问题

### 3.12 是否足以支持 Phase 3-2 Accepted — **通过**

基于以上 11 项审查结果，当前仓库已满足 Phase 3-2 Accepted 的全部判定标准。

---

## 4. 关键优点

1. **ReplayReader 架构克制**：`replay_and_compare` 明确委托 ScenarioEngine 而非重建执行逻辑，代码注释清晰标注"NOT a second engine"，成功避免了执行引擎膨胀。

2. **Audit correlation 最小闭环成立**：`run_id` 从 ScenarioEngine 生成，贯穿 DecisionTrace → TransitionRecord → trace persistence → inspect-run → signoff entry，形成了可复核的 machine-readable 审计链。

3. **ScenarioValidator 严格分离**：6 项结构化检查（SV-1~SV-6）完全不涉及执行或 guard evaluation，保持了 validator 的静态判断器纯度。

4. **冻结边界完整保留**：Gate P3-A 测试（6 项）明确验证了 ModeGraph 无 execute 方法、GuardEvaluator 未变、TRANS→FUNC/IFACE 不存在、VALID_TRACE_DIRECTIONS 仍为 25。

5. **Scenario 模型向后兼容**：3 个新增 Optional 字段全部默认 None，`extra="forbid"` 继续生效，现有 scenario 文件无需修改。

---

## 5. 关键问题

1. **Demo baseline 空 ModeGraph 导致 validate-scenario 必然失败**（SV-1）。这是正确的"如实失败"，但意味着当前无法端到端演示完整的 scenario validation → execution → replay 流程。建议 Phase 3-3 补充一个含 Phase 2 artifacts 的 demo baseline。

2. **inspect-run 对未配对 run_id 的处理**：当 signoff 存在但 trace 不存在时（如 RUN-001 有 signoff 但无 trace），inspect-run 仅报告"No trace found"，不会反向查询 signoff。这是可接受的最小实现，但未来可考虑增强。

3. **signoff 文件累积了多条测试遗留记录**（7 条，其中前 2 条无 run_id/scenario_id）。这是多次审查命令的副作用，不影响功能正确性，但建议在正式交付前清理。

4. **.yml 防撞方案仍是结构性妥协**：`iter_artifact_yamls` 只 glob `*.yaml`，scenario 文件使用 `.yml` 绕过 artifact scanning。在当前阶段可接受，但长期应考虑正式注册 scenario 文件类型或增加独立的扫描规则。

---

## 6. 最终判定

### 是否接受 Phase 3-2：**是 — Phase 3-2 Accepted**

### 是否支持进入 Phase 3-3 准备阶段：**是**

### 必须附带的边界条件：

1. **Phase 3-3 必须补充含 Phase 2 artifacts 的 demo baseline**：当前 demo set 的空 ModeGraph 导致 validate-scenario 和 run-scenario 无法展示完整的 scenario → transition resolution → replay 流程。这不是 3-2 的阻断，但 3-3 必须解决。

2. **formal baseline 仍不得写入任何 trace / signoff 产物**：已验证 `artifacts/.aplh/` 下无 review_signoffs.yaml 和 traces/ 目录。此约束在 3-3/3-4 期间继续成立。

3. **.yml 防撞方案的技术债务应在 Phase 3 的某个后续阶段正式解决**：当前方案是合理的保守实现，但不应永久化。

4. **signoff 文件应在正式交付前清理测试遗留记录**。

### 不需要先修什么：

当前实现无阻断性问题。上述边界条件均为 Phase 3-3 及后续阶段的技术债务，不影响 3-2 的 Accept 判定。

---

*Report generated 2026-04-05T01:30Z*
