# Feature Specification: audit（M02）

**Feature**: `004-audit` | **Phase**: P0a | **Status**: Implemented

**任务**: AUD-01 ~ AUD-03（`docs/planning/tasks/00-foundation.md`）

---

## 1. 模块职责

append-only 审计日志，覆盖安全事件与 MCP 工具调用。只写不改。

## 2. 为什么做

MCP 已有 `mcp_tool_call`；平台需要统一的 `audit_log`，记录身份、数据、评测、门禁等敏感操作，并支持保留策略与查询。

## 3. 功能需求

- **FR-001** `audit_log` 表与 `AuditWriter`：append-only；含 actor/action/resource/trace_id；不含 PII。
- **FR-002** 审计账号无 `UPDATE`/`DELETE`；保留 180 天；按月分区，可 `DROP PARTITION`。
- **FR-003** `AuditReader`：按时间/actor/resource 过滤；租户隔离；分页只读。
- **FR-004** 写入失败不阻塞主请求，但必须告警（`audit_write_failed_total`）。
- **FR-005** `mcp_tool_call` 与 `audit_log` 独立；MCP 继续使用前者。

## 4. 验收场景

1. **Given** 一次敏感操作，**When** 完成，**Then** `audit_log` 有完整字段且无 PII。
2. **Given** 审计账号，**When** `UPDATE`/`DELETE`，**Then** 数据库拒绝。
3. **Given** 过期分区，**When** 维护任务运行，**Then** 按月 `DROP PARTITION`。
4. **Given** 审计库不可用，**When** 工具调用，**Then** 主请求成功且告警。

## 5. 关键实体

`audit_log`、`mcp_tool_call`（MCP 所有）。

## 6. 边界与异常

- 审计写入失败、分区保留、跨租户查询、PII 泄露、审计库不可用。

## 7. 不在范围

- 业务事件定义（由各模块提供 action/resource）。
- 日志平台/归档到对象存储。

## 8. 依赖

`002-core`（DB/上下文）、`003-identity`（actor）。
