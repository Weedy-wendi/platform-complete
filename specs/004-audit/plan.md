# Implementation Plan: audit（M02）

**Feature**: `004-audit` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- SQLAlchemy + Alembic；`audit_log` 按月 RANGE COLUMNS 分区。
- 写入：同步短事务或异步批量；失败告警。
- 权限：专用审计账号仅 `INSERT`；查询走只读账号。
- 保留：月度维护脚本预建/删除分区。

## 2. 数据模型

`audit_log(id, tenant_id, actor_id, action, resource_type, resource_id, status, trace_id, created_at, detail_json)`；分区键 `created_at`。

## 3. 公开接口

`AuditWriter`、`AuditReader`；`AuditEvent` DTO；分页 `Page[AuditEvent]`。

## 4. 测试策略

- 集成：写入/查询/分页；分区维护；保留策略。
- 安全：UPDATE/DELETE 拒绝；跨租户；PII 不落库。
- 故障：审计库不可用时主请求成功且指标递增。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 审计写阻塞主请求 | 异步/批量 + 失败告警 |
| 保留策略误删 | dry-run + 审批 |
| PII 泄露 | 字段白名单 + 脱敏测试 |
| 审计账号越权 | 仅 INSERT + 权限验证 |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | 审计不可变 |
| II 五原语 | Evidence/审计 |
| III API/CLI First | 查询接口供 REST |
| IV Boring Tech | MySQL 分区 |
| V 控制/执行分离 | 审计不承载业务 |
| VI 证据驱动 | 权限/保留/故障测试 |
| VII 模块化单体 | 独立模块 |
