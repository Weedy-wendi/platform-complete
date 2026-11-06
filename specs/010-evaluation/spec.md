# Feature Specification: evaluation（M06）

**Feature**: `010-evaluation` | **Phase**: P0b | **Status**: Implemented

**任务**: EVL-01 ~ EVL-16（`docs/planning/tasks/02-evaluation.md`）

---

## 1. 模块职责

评分器、指标、套件、目标、Run、样本结果、基线。平台的核心域。

## 2. 为什么做

平台的核心价值是**可复现的评测**。MCP 的 `list_evaluators`/`get_run`/`get_run_items`/`compare_runs` 与门禁/报告都依赖本模块。

## 3. 功能需求

- **FR-001** 评分器/指标模型：版本不可变；指标方向明确。
- **FR-002** 规则评分器：精确匹配/F1/正则；结果确定。
- **FR-003** Judge 评分器：Rubric、结构化输出、Schema 校验、调用留痕。
- **FR-004** Suite/Target/Baseline：版本绑定；基线冻结。
- **FR-005** Run 创建与 Manifest：必含 `dataset_hash`、`evaluator_versions[]`、`metric_configs`、`target_config`、采样/seed、`code_version`、`env`；`manifest_hash` 稳定；重复请求幂等；创建后不可修改。
- **FR-006** Run 执行器：并发可控；单条失败不拖垮整 Run；写 `run_item`/`score`/`judge_call`；进度/成本/失败数实时可查；取消保留已完成项。
- **FR-007** 状态机/重试/幂等/取消。
- **FR-008** `RunReader`：状态/进度/明细/分页；租户隔离。
- **FR-009** 对比与统计：差值、置信区间、显著性；不把噪声当提升。
- **FR-010** 复现：同 Manifest 重放 5 次结果一致。
- **FR-011** Judge 校准：κ ≥0.7 才能用于门禁。
- **FR-012** 成本预算与熔断：超预算暂停并告警，可恢复。
- **FR-013** `TargetAdapter` SPI/注册表：可插拔；配置版本化；不写业务表。
- **FR-014** 声明式 HTTP / OpenAI 兼容适配器：A/B 模式零代码；模板白名单；原始响应存 artifact。
- **FR-015** `TraceSource`（OTLP/OpenInference）：Span 归一化、去重、缺失降级、租户隔离。
- **FR-016** 适配器一致性 + Record/Replay：Replay 不调用 Agent；版本不一致标记 `not_comparable`。

## 4. 验收场景

1. **Given** 完整 Manifest，**When** 创建 Run，**Then** 返回 `run_id` 与稳定 `manifest_hash`；重复请求同一 `run_id`。
2. **Given** 单条样本超时，**When** 执行，**Then** 该条 `error`，其余继续。
3. **Given** 同一 Manifest，**When** 重放 5 次，**Then** 结果一致。
4. **Given** 超预算，**When** 继续执行，**Then** 暂停并告警。
5. **Given** 自定义 Adapter，**When** 未通过 conformance，**Then** 不允许上线。
6. **Given** Replay，**When** 重新打分，**Then** 不调用 Agent，`mode=replay`。

## 5. 关键实体

`evaluator`、`evaluator_version`、`metric`、`eval_suite`、`suite_version`、`target`、`run`、`run_item`、`score`、`judge_call`、`baseline`。

## 6. 边界与异常

- 单条失败、Worker 崩溃、重复计费、Judge 不合 Schema、κ 不足、Trace 缺失/重复、跨租户、大样本 OOM。

## 7. 不在范围

- Gate/报告（`011-gate`、`012-reporting`）。
- 数据集存储（`007-catalog`）。

## 8. 依赖

`002-core`、`005-assets`、`007-catalog`、`008-jobs`、`009-model-gateway`、`006-observability`。
