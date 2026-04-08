# 《APLH Phase 2C 独立实施审查报告》

**Document ID:** APLH-REVIEW-2C
**Version:** 1.0.0
**Date:** 2026-04-04
**Reviewer:** Independent Phase 2C Review Officer (GPT-5.4 / GLM-5-Turbo)
**Status:** FINAL

---

## 1. 总体结论

### Phase 2C Accepted

当前仓库已正确、克制、无越界地完成了 Phase 2C：Scenario Engine / 调度层 / demo-scale execution readiness layer。

**支持进入 Phase 3 准备阶段。**

### 附带边界条件

1. `test_signoff_formal_rejected` 测试为空 `pass` 占位符，须在 Phase 3 准备阶段补全实际断言
2. `signoff-demo` 的 `reviewer` 字段硬编码为 `"Demo Reviewer"`，Phase 3 须参数化
3. `review_signoffs.yaml` 条目无 `scenario_id` 关联，须在后续 phase 补充
4. `README.md` Phase Status 仍停留在 "Phase 2A" 描述，须更新以反映 2C Accepted 状态

以上 4 项均为 **非阻塞项**，不构成本次 Acceptance 的否决理由，但须作为 Phase 3 的技术债务记录。

---

## 2. 审查范围

### 2.1 读取的文件（25 个）

| # | 文件路径 | 审查目的 |
|---|---------|---------|
| 1 | `docs/PHASE2C_IMPLEMENTATION_NOTES.md` | 2C 实施说明 |
| 2 | `docs/PHASE2B_IMPLEMENTATION_NOTES.md` | 2B 实施说明（冻结输入） |
| 3 | `docs/PHASE2A_IMPLEMENTATION_NOTES.md` | 2A 实施说明（冻结输入） |
| 4 | `docs/REVIEW_GATES.md` | Review Gate 定义 |
| 5 | `docs/ARTIFACT_MODEL.md` | Artifact 模型定义 |
| 6 | `README.md` | 项目总览与 Phase Status |
| 7 | `aero_prop_logic_harness/models/scenario.py` | Scenario / ScenarioTick 模型 |
| 8 | `aero_prop_logic_harness/models/predicate.py` | 谓词语法模型 |
| 9 | `aero_prop_logic_harness/models/transition.py` | Transition 模型 |
| 10 | `aero_prop_logic_harness/models/trace.py` | TraceLink 模型与方向定义 |
| 11 | `aero_prop_logic_harness/models/guard.py` | Guard 模型 |
| 12 | `aero_prop_logic_harness/services/guard_evaluator.py` | GuardEvaluator 谓词评估器 |
| 13 | `aero_prop_logic_harness/services/decision_tracer.py` | 决策追踪与格式化 |
| 14 | `aero_prop_logic_harness/services/scenario_engine.py` | ScenarioEngine + RuntimeState |
| 15 | `aero_prop_logic_harness/services/mode_graph.py` | ModeGraph 只读图视图 |
| 16 | `aero_prop_logic_harness/validators/consistency_validator.py` | 一致性校验器 |
| 17 | `aero_prop_logic_harness/validators/mode_validator.py` | 模式结构校验器 |
| 18 | `aero_prop_logic_harness/validators/coverage_validator.py` | 覆盖度校验器 |
| 19 | `aero_prop_logic_harness/cli.py` | CLI 命令（含 run-scenario / signoff-demo） |
| 20 | `aero_prop_logic_harness/path_constants.py` | 路径常量与目录扫描规则 |
| 21 | `pyproject.toml` | 项目配置与 Python 版本要求 |
| 22 | `tests/test_phase2c.py` | Phase 2C 测试套件 |
| 23 | `tests/test_phase2b.py` | Phase 2B 测试套件（回归参考） |
| 24 | `artifacts/.aplh/freeze_gate_status.yaml` | Formal baseline gate status |
| 25 | `artifacts/examples/minimal_demo_set/.aplh/freeze_gate_status.yaml` | Demo baseline gate status |
| 26 | `artifacts/examples/minimal_demo_set/scenarios/test.yml` | Demo scenario 文件 |

### 2.2 执行的命令（8 条）

| # | 命令 | 返回码 | 结果 |
|---|------|--------|------|
| 1 | `.venv/bin/python -m pytest` | **0** | 162 passed in 4.59s |
| 2 | `validate-artifacts --dir artifacts/examples/minimal_demo_set` | **0** | "No schema validation issues found" |
| 3 | `validate-modes --dir artifacts` | **0** | "[Formal] 0 modes, 0 transitions, 0 guards" — 无 Phase 2 artifacts |
| 4 | `validate-modes --dir artifacts/examples/minimal_demo_set` | **0** | "[Demo-scale] 0 modes, 0 transitions, 0 guards" |
| 5 | `run-scenario --dir minimal_demo_set --scenario test.yml` | **0** | "Scenario execution completed successfully" |
| 6 | `signoff-demo --dir minimal_demo_set --resolution "Looks good"` | **0** | "Successfully recorded T2 signoff" |
| 7 | `signoff-demo --dir artifacts --resolution "Looks good"` | **1** | "Cannot sign off in Formal baseline" |
| 8 | `signoff-demo --dir /tmp --resolution "Looks good"` | **1** | "Unmanaged Environment Error" |

**环境：** Python 3.11.15, macOS darwin, pytest 9.0.2, venv at `.venv/bin/python3.11`

### 2.3 执行的反证攻击（6 类）

| # | 反证类型 | 结果 |
|---|---------|------|
| 1 | 图污染攻击 | **通过** — ModeGraph 无 `step/fire/evaluate/execute` 方法 |
| 2 | Evaluator creep 攻击 | **通过** — GuardEvaluator 无 `eval()/exec()/compile()` 调用 |
| 3 | TRANS.actions 污染攻击 | **通过** — actions 仍为 field-only，未进入 consistency scope |
| 4 | CLI 作用域攻击 | **通过** — demo/formal/unmanaged 三路径正确分离 |
| 5 | Scenario 文件防撞攻击 | **通过（附条件）** — `.yml` 不被 `iter_artifact_yamls` 扫描，当前可接受 |
| 6 | 2C 越界攻击 | **通过** — 无 evaluator/simulator/formal freeze/Phase 3 痕迹 |

---

## 3. 十三项审查结果

### 【1. 是否严格停留在 Phase 2C】

**通过**

- 未实现通用 evaluator / simulator / formal baseline freeze
- Scenario Engine 严格服务于 demo-scale execution readiness
- 无 Phase 3 authoring 痕迹
- `predicate.py` 注释明确标注 "Phase 3+" 不在本 scope
- `PHASE2C_IMPLEMENTATION_NOTES.md` §5 明确列出 exclusions

**关键证据：**
- `scenario_engine.py` L18-22: docstring 明确 "Demo-scale scenario runtime dispatcher"
- `guard_evaluator.py`: 纯 operator lookup，无通用公式引擎
- 全仓库 grep `evaluator|simulator|Phase.?3` 无越界代码

---

### 【2. Scenario schema 是否正确落地】

**通过**

- `Scenario` 模型使用 `extra="forbid"` 严格封闭
- `ScenarioTick` 模型使用 `extra="forbid"` 严格封闭
- 输入 contract 清晰：`scenario_id`, `title`, `baseline_scope`, `initial_mode_id`, `ticks`
- `signal_updates` 使用 `Dict[str, Any]` 结构化信号注入
- 未污染 core artifact schema（Scenario 不是 ArtifactBase 子类）
- 未使用自由文本凑逻辑

**关键证据：**
- `scenario.py` L4-28: 全部字段严格类型化，`extra="forbid"`
- 测试 `test_schema_valid` 验证 YAML 反序列化正确

---

### 【3. Runtime State Container 是否真正独立】

**通过**

- `RuntimeState` 是独立 `BaseModel`，不是 `Mode`/`Transition`/`Guard` 的子类或扩展
- 包含 `current_mode_id`, `signal_snapshot`, `current_tick`, `halt_reason`, `blocked_by_t2`
- 使用 `extra="forbid"` 防止状态泄漏
- 运行时状态 **未写回** `Mode`/`Transition`/`Guard` 任何实例
- `ScenarioEngine.run_scenario()` 每次创建新的 `RuntimeState` 实例

**关键证据：**
- `scenario_engine.py` L8-16: `RuntimeState` 定义，`extra="forbid"`
- `scenario_engine.py` L31: `self.state = RuntimeState(...)` 每次新建
- `scenario_engine.py` L130: 仅更新 `self.state.current_mode_id`，未写回 graph

---

### 【4. GuardEvaluator 是否受限且安全】

**通过**

- 仅支持冻结的 operator 枚举：`EQ, NE, GT, GE, LT, LE, BOOL_TRUE, BOOL_FALSE`
- 不支持 `eval()` / `exec()` / `compile()` / 任何字符串公式解析
- 不支持函数调用、算术表达式、时间窗口、滞后、变化率
- 缺失 signal 时 **显式失败**（抛出 `EvaluationError`），而非自动补零
- CompoundPredicate 仅支持 `AND/OR/NOT`，操作数由 Pydantic 严格校验

**关键证据：**
- `guard_evaluator.py` L31-62: 纯 operator lookup 分支，无任何动态求值
- L32: `if atomic.signal_ref not in snapshot: raise EvaluationError(...)` — 显式失败
- 反证搜索：grep `eval\(|exec\(|compile\(` 仅命中注释行 "No string eval()"

---

### 【5. Scenario Engine 是否清晰且克制】

**通过**

- Tick loop 清晰：遍历 `scenario.ticks`，T2 blocked 时 break
- Candidate collection：通过 `ModeGraph.transitions_from()` 只读查询
- Guard evaluation：委托给 `GuardEvaluator.evaluate()`
- Priority / arbitration：`min(priority)` 取最高优先级，等优先冲突则 T2 block
- Transition selection：单胜者通过，记录 `mode_after`
- Runtime state update：仅更新 `self.state`，不写回 graph
- Action emission record：`winner.actions` 仅为 string list，**无函数调用**
- Blocked-by-T2 路径：priority conflict / degraded recovery / guard evaluation error 三条阻断路径

- 仍只是 demo-scale execution engine，未膨胀为 production runtime

**关键证据：**
- `scenario_engine.py` L42-145: 完整 `_step_tick` 方法
- L87-97: 等优先冲突阻断
- L104-115: degraded recovery 阻断
- L118: `emitted_actions = list(winner.actions)` — 纯记录，无执行

---

### 【6. 是否正确保持了 2A/2B exclusion 边界】

**通过**

- `TRANS.actions` 仍只是 log emit / record（string list），未变成函数调用
- `actions` 未进入 `ConsistencyValidator._get_all_embedded_links()` 的提取范围
- `Function.related_transitions` 未进入提取范围（`consistency_validator.py` L67 注释）
- `TRANS -> FUNC` trace 方向在 `VALID_TRACE_DIRECTIONS` 中不存在
- `TRANS -> IFACE` trace 方向在 `VALID_TRACE_DIRECTIONS` 中不存在
- `ModeGraph` 保持只读图视图纯度
- `ConsistencyValidator` / `ModeValidator` / `CoverageValidator` 保持静态判断器纯度

**关键证据：**
- `trace.py` L73-74: 显式注释 `NOTE: No (TRANS, FUNC, ...) / No (TRANS, IFACE, ...)`
- `consistency_validator.py` L96: `# NOTE: artifact.actions NOT extracted`
- `mode_graph.py` L10: `No step() / fire() / execute() / evaluate() methods.`

---

### 【7. Decision trace / audit layer 是否真正可审计】

**通过**

- `TransitionRecord` 包含：`tick_id`, `applied_signals`, `mode_before`, `candidates_considered`, `transition_selected`, `actions_emitted`, `mode_after`, `block_reason`
- Machine-readable: `TransitionRecord` 是 Pydantic `BaseModel`，可序列化
- Human-readable: `DecisionTrace.to_human_readable()` 格式化输出
- T2 block 时记录 `block_reason`
- 无 transition 时记录 `(No valid transition)`
- 同时覆盖正向路径和阻断路径

**关键证据：**
- `decision_tracer.py` L4-15: `TransitionRecord` 字段定义，`extra="forbid"`
- `decision_tracer.py` L25-41: `to_human_readable()` 格式化输出
- CLI 输出：`run-scenario` 实际打印完整 trace

---

### 【8. T2 signoff hooks 是否真正落地】

**通过**

- Equal-priority conflict: engine 阻断，halt_reason 包含 `"Priority conflict [T2 Blocked]"`
- Degraded recovery: engine 阻断，halt_reason 包含 `"Degraded recovery conflict [T2 Blocked]"`
- Signoff 输入产物: `--dir` + `--resolution` 参数
- Signoff 输出产物: `review_signoffs.yaml` 条目含 `timestamp`, `reviewer`, `resolution`
- 写入位置: `baseline-local .aplh/review_signoffs.yaml`
- Demo/formal/unmanaged 差异:
  - Demo-scale: 放行，写入 signoff
  - Formal: exit 1, "Cannot sign off in Formal baseline"
  - Unmanaged: exit 1, "Unmanaged Environment Error"
- 未在 2C 阶段创建错误位置的 signoff（验证：formal `.aplh/` 无 `review_signoffs.yaml`）

**关键证据：**
- `cli.py` L435-437: Formal 拒绝
- `cli.py` L439-441: Unmanaged 拒绝
- `cli.py` L444-476: Demo-scale 写入逻辑
- 实际执行：signoff 正确写入 `minimal_demo_set/.aplh/review_signoffs.yaml`
- Formal `.aplh/` 目录确认无 `review_signoffs.yaml`

---

### 【9. run-scenario / signoff-demo CLI 是否真正按合同实现】

**通过**

- `run-scenario`:
  - Demo-scale 运行: 放行，exit 0
  - Formal 目录: 拒绝，exit 1, "Formal directory execution is not allowed in 2C"
  - Unmanaged: 正常加载（如无 artifact 则空图），不拒绝执行本身
  - Scenario file 加载: Pydantic 严格校验
  - 输出语义: trace + 最终状态清晰
- `signoff-demo`:
  - Demo-scale: 放行，写入 signoff，exit 0
  - Formal: 拒绝，exit 1
  - Unmanaged: 拒绝，exit 1
  - 未污染原有 CLI 行为（validate-artifacts / check-trace / freeze-readiness / validate-modes 均未受影响）

**关键证据：**
- 命令 #5: run-scenario demo-scale, exit 0 ✅
- 命令 #6: signoff-demo demo-scale, exit 0 ✅
- 命令 #7: signoff-demo formal, exit 1 ✅
- 命令 #8: signoff-demo unmanaged, exit 1 ✅
- 补充反证: `run-scenario --dir artifacts` 对 formal 正确拒绝 (exit 1)

---

### 【10. tests 是否真实、充分、无越界】

**部分通过**

- **真实性确认**: `162 passed` 经实际执行验证（Python 3.11.15 venv）
- **覆盖分析**:
  - Scenario schema: ✅ `test_schema_valid`
  - Guard evaluator: ✅ `test_guard_evaluator_missing_signal`, `test_guard_evaluator_success`
  - Scenario engine 正向/阻断路径: ✅ `test_engine_priority_conflict`, `test_engine_degraded_recovery`
  - Priority conflict: ✅ `test_engine_priority_conflict`
  - T2 block: ✅ 两个 engine 测试均验证 `blocked_by_t2`
  - CLI integration: ✅ `test_signoff_unmanaged_rejected`
  - Signoff path rules: ⚠️ `test_signoff_formal_rejected` **为空 `pass` 占位符**
  - 2A/2B 回归: ✅ test_phase2a_models (65) + test_phase2b (44) 全绿
- **未偷偷实现 3 期逻辑**: 确认通过

**覆盖缺口（非阻塞）：**
1. `test_signoff_formal_rejected` (L36-38) 为 `pass` 占位符，无实际断言
2. 无 compound predicate (AND/OR/NOT) 的 evaluator 测试
3. 无 `run-scenario` 正式 CLI 集成测试（仅通过 engine 直接测试）
4. 无 `review_signoffs.yaml` 写入后的内容验证测试

**关键证据：**
- `test_phase2c.py` L36-38: `def test_signoff_formal_rejected(tmp_path): pass`
- 7 个测试函数，覆盖核心路径但不完整

---

### 【11. docs / handoff 是否正确更新】

**部分通过**

- ✅ `docs/PHASE2C_IMPLEMENTATION_NOTES.md`: 完整记录 2C 做了什么、没做什么
- ✅ `docs/REVIEW_GATES.md`: 未被 2C 修改，保持原有 gate 定义
- ✅ `docs/ARTIFACT_MODEL.md`: 未被 2C 修改，Phase 2B+ extension points 正确描述
- ⚠️ `README.md`: Phase Status 仍显示 "Phase 2A (Schema Extension)" 和 "Pending independent review"，**未更新以反映 2C Accepted 状态**
- ✅ 未出现 "Phase 2 已完成" 的偷换表述

**关键证据：**
- `README.md` L12: `Currently at **Phase 0 + Phase 1 + Phase 2A**` — 未反映 2B/2C
- `PHASE2C_IMPLEMENTATION_NOTES.md` §5: exclusion list 完整且克制

---

### 【12. 是否继续接得住当前仓库现实】

**通过**

- **ModeGraph**: 保持只读图视图，2C 仅读取不写入
- **Validators**: 三个 validator 保持静态判断器纯度，未被 2C 修改
- **baseline-local `.aplh`**: signoff 正确写入 demo `.aplh/`，未泄漏到 formal
- **demo/formal boundary**: `_classify_directory()` 三路径分类继续正确工作
- **formal baselines 无 Phase 2 artifacts**: `validate-modes --dir artifacts` 返回 0 modes, 0 transitions, 0 guards — 这是正确的现实
- **`.yml` 取巧方案**:
  - `iter_artifact_yamls` 只 glob `*.yaml`，`.yml` 文件自然绕过 artifact scanning
  - Scenario 文件存放在 `scenarios/` 子目录，不是 artifact 标准目录
  - **判断**: 当前阶段可接受。Scenario 不是 artifact type，不参与 artifact schema 验证，用 `.yml` 是合理的命名空间隔离。但须在后续 phase 注意：如果引入 `.yml` 作为 artifact 格式，须同步修改 `iter_artifact_yamls`

**关键证据：**
- `path_constants.py` L64: `root.glob("**/*.yaml")` — 只扫 `.yaml`
- `artifacts/examples/minimal_demo_set/scenarios/test.yml`: 独立子目录，不影响 artifact scanning

---

### 【13. 是否足以支持进入 Phase 2C Accepted 状态】

**通过**

当前仓库已满足 Phase 2C Accepted 的全部必要条件：

- ✅ 没有越界到 Phase 3
- ✅ Scenario schema / runtime container 正确落地
- ✅ GuardEvaluator 受限且安全
- ✅ Scenario Engine 清晰且克制
- ✅ 2A/2B exclusion 边界继续成立
- ✅ Decision trace / audit layer 可审计
- ✅ T2 signoff hooks 真正落地
- ✅ CLI 行为符合 demo/formal/unmanaged 合同
- ✅ tests 全绿（162 passed）且覆盖关键边界
- ✅ docs / handoff 基本更新正确（README 有非阻塞缺陷）
- ✅ demo/formal boundary 继续严格继承
- ✅ 没有发现可重复复现的结构性绕过路径

---

## 4. 关键优点

### 优点 1: GuardEvaluator 的安全设计典范

GuardEvaluator 采用纯 operator lookup，无任何动态求值能力。缺失 signal 时显式抛出 `EvaluationError` 而非静默补零。这体现了航空工程软件 "fail explicitly" 的正确原则。

### 优点 2: RuntimeState 的严格隔离

`RuntimeState` 使用 `extra="forbid"` 完全封闭，且每次 `run_scenario()` 创建新实例。运行时状态与静态 artifact 实体之间不存在任何写回路径。这是 scenario engine 不污染 ModeGraph 的根本保障。

### 优点 3: 三路径 CLI 边界分离

`_classify_directory()` 配合 `_formal/demo/unmanaged` 三级拒绝逻辑，确保 signoff 不会泄漏到错误位置。8 条命令全部返回预期退出码，无绕过路径。

### 优点 4: T2 block 机制完整

Priority conflict 和 degraded recovery 两条 T2 阻断路径均有代码实现、测试覆盖、trace 输出和 signoff 对接。这是 2C "execution readiness" 层面的核心安全阀。

### 优点 5: 冻结边界的持续守护

从 2A 到 2C，`TRANS.actions` field-only、无 `TRANS->FUNC/IFACE` trace、`GUARD.predicate` 为唯一权威、`ModeGraph` 只读等冻结决策全部持续成立，未被任何后续实现侵蚀。

---

## 5. 关键问题

### 问题 1: `test_signoff_formal_rejected` 为空占位符

**严重度**: 中（非阻塞）
**位置**: `tests/test_phase2c.py` L36-38
**现状**: 测试函数体仅 `pass`，无任何断言
**风险**: formal signoff 拒绝路径无测试覆盖，虽然 CLI 实际行为经手动验证正确
**建议**: Phase 3 准备阶段补全实际断言

```python
# 当前（test_phase2c.py L36-38）
def test_signoff_formal_rejected(tmp_path):
    # Spoof formal root somehow? 
    pass
```

### 问题 2: README.md Phase Status 过时

**严重度**: 低（非阻塞）
**位置**: `README.md` L12-15
**现状**: Phase Status 仍显示 "Phase 2A (Schema Extension). Pending independent review."，未反映 2B Accepted / 2C Accepted
**风险**: 误导后续审查者对当前仓库状态的判断
**建议**: 2C Accepted 后更新为反映完整 Phase 2 状态

### 问题 3: `signoff-demo` reviewer 硬编码

**严重度**: 低（非阻塞）
**位置**: `cli.py` L451
**现状**: `entry["reviewer"] = "Demo Reviewer"` 硬编码
**风险**: 多人审查场景下无法区分审查者身份
**建议**: Phase 3 增加 `--reviewer` CLI 参数

### 问题 4: `review_signoffs.yaml` 无 scenario 关联

**严重度**: 低（非阻塞）
**位置**: `cli.py` L449-453
**现状**: signoff 条目仅含 `timestamp/reviewer/resolution`，无 `scenario_id` 或 `run_id`
**风险**: 多 scenario 运行时无法将 signoff 关联到具体场景执行
**建议**: Phase 3 在 signoff 条目中增加 `scenario_id` 字段

---

## 6. 最终判定

### 判定：Phase 2C Accepted

**是否接受 Phase 2C：是**

当前仓库已正确实现 Phase 2C demo-scale Scenario Engine / Execution Readiness Layer 的全部合同要求，且未越界到 Phase 3 范围。所有冻结边界持续成立。8 条标准命令全部返回预期退出码。6 类反证攻击全部通过。

**是否支持进入 Phase 3 准备阶段：是**

**附带边界条件：**

| # | 边界条件 | 性质 | 建议时机 |
|---|---------|------|---------|
| BC-1 | 补全 `test_signoff_formal_rejected` 实际断言 | 测试完整性 | Phase 3 准备阶段 |
| BC-2 | 更新 `README.md` Phase Status 反映 2C Accepted | 文档准确性 | 2C 正式 Accepted 后 |
| BC-3 | `signoff-demo` 增加 `--reviewer` 参数 | 审计完整性 | Phase 3 |
| BC-4 | `review_signoffs.yaml` 增加 `scenario_id` 字段 | 审计关联性 | Phase 3 |

以上 4 项边界条件均为 **非阻塞项**。它们的缺失不影响 Phase 2C 的核心功能正确性和边界安全性，但须在 Phase 3 作为技术债务处理。

---

*Phase 2C 独立实施审查完成。本报告基于 2026-04-04 仓库实际状态。*
