# Implementation Plan: search（M11）

**Feature**: `014-search` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- VectorIndex SPI + Qdrant；Embedding 版本表；索引 Job。
- `SemanticSearch` + MySQL 关键词降级；超时/熔断；`degraded=true`。
- payload 只存 `tenant_id`/`badcase_id`/`dataset_id`/`sample_id`/`tags`。

## 2. 数据模型

无 MySQL 业务表；Qdrant collection；Embedding 元数据表。

## 3. 公开接口

`VectorIndex`、`SemanticSearch`、`SearchHit`、`BadcaseSearchResult`。

## 4. 测试策略

- 集成：语义检索、降级、索引重建。
- 安全：跨租户、payload PII。
- 性能：降级 P95 ≤1s。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| Qdrant 不可用 | 关键词降级 |
| 跨租户 | 强制 tenant 过滤 |
| payload 泄露 | 只存引用 ID |
| 换模型不可重建 | 版本表 + 双写 |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | Embedding 版本 |
| II 五原语 | Badcase/Evidence |
| III API/CLI First | Service/REST/MCP |
| IV Boring Tech | Qdrant + MySQL 降级 |
| V 控制/执行分离 | 索引 Worker |
| VI 证据驱动 | 降级/隔离测试 |
| VII 模块化单体 | 独立模块 |
