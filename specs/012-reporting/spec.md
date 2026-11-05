# Feature Specification: reporting（M08）

**Feature**: `012-reporting` | **Phase**: P0c | **Status**: Implemented

**任务**: REP-01 ~ REP-05（`docs/planning/tasks/02-evaluation.md`）

---

## 1. 模块职责

读模型、报告生成、对比报告、导出、快照。只读，不写业务表。

## 2. 为什么做

评测结果需要可分享、可导出、可归档；MCP 的 run report 资源与前端报告页依赖本模块（REP-02）。

## 3. 功能需求

- **FR-001** 读模型/物化视图：查询 P95 <300ms；不跨模块 JOIN。
- **FR-002** Run 报告：Markdown/JSON；内容与 Run 一致；快照不可变。
- **FR-003** 对比报告：逐指标差值、劣化 Top N、置信信息。
- **FR-004** 导出：JSON/CSV/JUnit；大数据流式导出。
- **FR-005** 快照与分享链接：TTL 可控；不可枚举；越权拒绝。
- **FR-006** 报告绑定 `manifest_hash`；只读。

## 4. 验收场景

1. **Given** 一个 Run，**When** 生成报告，**Then** Markdown/JSON 内容与 Run 一致。
2. **Given** 两个 Run，**When** 对比报告，**Then** 差值/劣化 Top N/置信信息完整。
3. **Given** 大数据导出，**When** 导出 CSV/JUnit，**Then** 流式完成、格式正确。
4. **Given** 分享链接过期/越权，**When** 访问，**Then** 拒绝。

## 5. 关键实体

`report_snapshot`、`read_model_*`。

## 6. 边界与异常

- Run 数据缺失、超大报告、导出中断、快照过期、跨租户、链接越权。

## 7. 不在范围

- Run 执行/评分；Gate 判定。

## 8. 依赖

`010-evaluation`（EVL-08/09）、`005-assets`（快照）。
