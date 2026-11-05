# Feature Specification: search（M11）

**Feature**: `014-search` | **Phase**: P1 | **Status**: Implemented

**任务**: SRC-01 ~ SRC-06（`docs/planning/tasks/01-data.md`）

---

## 1. 模块职责

Qdrant 向量索引、Embedding 版本管理、语义检索、关键词降级。MySQL 不存向量。

## 2. 为什么做

Badcase 检索需要语义能力；Qdrant 不可用时必须降级为关键词，不阻塞主流程。MCP 的 `search_badcases` 依赖 SRC-05。

## 3. 功能需求

- **FR-001** `VectorIndex` SPI：upsert/search/delete；可替换。
- **FR-002** Qdrant 适配：collection/payload 索引；租户过滤。
- **FR-003** Embedding 版本：模型/版本/维度；换模型可重建；双写切换。
- **FR-004** 索引任务：全量/增量；失败可重试。
- **FR-005** `SemanticSearch`：top-k（默认 10，最大 50）、score；payload 只存引用 ID。
- **FR-006** 降级：Qdrant 超时/不可用 → MySQL 关键词检索，`degraded=true`，不返回 5xx；P95 ≤1s。
- **FR-007** 租户隔离：跨租户结果恒为空；payload 不含 PII/正文。

## 4. 验收场景

1. **Given** 语义查询，**When** 检索，**Then** 返回相关结果与 score。
2. **Given** 租户 A，**When** 查询，**Then** 不返回租户 B。
3. **Given** Qdrant 停止，**When** 检索，**Then** 降级成功、`degraded=true`。
4. **Given** payload，**When** 检查，**Then** 不含正文/PII。
5. **Given** 换 Embedding，**When** 重建，**Then** 可切换/双写。

## 5. 关键实体

Qdrant collection；`embedding_model`/`embedding_version`/`embedding_dim`（元数据）。

## 6. 边界与异常

- Qdrant 超时/不可用、Embedding 版本切换、跨租户、payload 泄露、降级延迟。

## 7. 不在范围

- MySQL 向量存储（禁止）。
- 向量集群运维。

## 8. 依赖

`007-catalog`、`009-model-gateway`、`008-jobs`。
