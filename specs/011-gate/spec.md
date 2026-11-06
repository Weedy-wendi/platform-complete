# Feature Specification: gate（M09）

**Feature**: `011-gate` | **Phase**: P0c | **Status**: Implemented

**任务**: GAT-01 ~ GAT-05（`docs/planning/tasks/02-evaluation.md`）

---

## 1. 模块职责

门禁规则、基线对比、判定与证据。只读评测结果，不修改。

## 2. 为什么做

把「指标是否劣化」变成可解释、可复现、可审计的判定；MCP 的 `check_gate` 依赖本模块（GAT-04）。

## 3. 功能需求

- **FR-001** Gate/Rule 模型：规则可组合、版本化。
- **FR-002** 判定引擎：绝对阈值、相对基线、统计显著性、样本量下限。
- **FR-003** 样本量不足返回 `insufficient_data`，不判定通过。
- **FR-004** 每条规则输出 `expected`/`actual`/`passed`/`evidence_ref`。
- **FR-005** 判定绑定 `manifest_hash`；Manifest 不可复现则拒绝判定。
- **FR-006** 基线选择与冻结：不可变、可追溯。
- **FR-007** 误拦率可观测；漏拦告警；阈值边界测试。

## 4. 验收场景

1. **Given** 一个 Run + Suite，**When** 判定，**Then** 返回 `passed` 与逐规则证据。
2. **Given** 样本量不足，**When** 判定，**Then** `insufficient_data`，不通过。
3. **Given** 指标劣化，**When** 判定，**Then** 对应规则 `passed=false` 且 evidence 可下钻。
4. **Given** 跨租户 Gate，**When** 访问，**Then** NotFound。

## 5. 关键实体

`gate`、`gate_rule`、`gate_result`。

## 6. 边界与异常

- Manifest 不可复现、样本量不足、指标缺失、基线版本不一致、阈值边界、跨租户。

## 7. 不在范围

- Run 执行/评分（`010-evaluation`）。
- 报告渲染（`012-reporting`）。

## 8. 依赖

`010-evaluation`（EVL-04/05/09）。
