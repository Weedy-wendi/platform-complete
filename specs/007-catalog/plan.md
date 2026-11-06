# Implementation Plan: catalog（M04）

**Feature**: `007-catalog` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- SQLAlchemy + Alembic；`(tenant_id, dataset_id, version)` 唯一。
- 内容规范化后计算 `sha256`；同内容返回已有版本。
- 批量写入 `executemany`（1000–5000/批）；事务边界整批回滚。
- 大 payload/文件走 `artifact`。

## 2. 数据模型

`project`、`datasource`、`dataset`、`dataset_version`、`sample`、`lineage_edge`；`sample` 去重键 `(dataset_version_id, sample_key)`。

## 3. 公开接口

`CatalogReader`、`DatasetVersionRef`、`ProjectView`/`DatasetView`/`SampleView`。

## 4. 测试策略

- 单元：哈希稳定性、版本号、去重。
- 集成：不可变、批量/回滚、行数、血缘、分页。
- 安全：跨租户。
- 性能：10 万样本基准。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 版本可变 | 数据库约束 + 服务拒绝 |
| 批量失败残留 | 事务回滚 |
| 大 payload OOM | artifact/流式 |
| 跨租户 | Repository 过滤 + 测试 |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | 不可变版本 + content_hash |
| II 五原语 | Asset/Version |
| III API/CLI First | CatalogReader 供 REST/MCP |
| IV Boring Tech | MySQL 批量写入 |
| V 控制/执行分离 | 导入在 Worker |
| VI 证据驱动 | 基准/不可变/隔离测试 |
| VII 模块化单体 | 独立模块 |
