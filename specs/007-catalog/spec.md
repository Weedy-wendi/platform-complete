# Feature Specification: catalog（M04）

**Feature**: `007-catalog` | **Phase**: P0b | **Status**: Implemented

**任务**: CAT-01 ~ CAT-07（`docs/planning/tasks/01-data.md`）

---

## 1. 模块职责

项目、数据源、数据集、不可变版本、样本、血缘。是评测与 MCP 的数据入口。

## 2. 为什么做

评测必须有可复现的数据集版本；MCP 的 `list_projects`/`search_datasets`/`get_dataset_schema`/`preview_samples` 依赖本模块。

## 3. 功能需求

- **FR-001** 项目 CRUD：租户隔离、软删除、名称租户内唯一。
- **FR-002** 数据源模型与 `secret_ref`：不存明文密钥；连接测试。
- **FR-003** 数据集与不可变版本：发布后禁止 UPDATE；`content_hash` 可复现；同内容重复发布返回已有版本。
- **FR-004** 版本号单调递增、无空洞；大文件走 artifact。
- **FR-005** 样本批量写入：10 万条可批量写入；整批回滚；`(version, sample_key)` 去重；行数一致。
- **FR-006** `CatalogReader`：检索、分页、Schema、样本预览；只读。
- **FR-007** 数据血缘：`lineage_edge` 记录上游/下游。

## 4. 验收场景

1. **Given** 已发布版本，**When** UPDATE，**Then** 拒绝。
2. **Given** 相同内容重复发布，**When** 发布，**Then** 返回已有版本。
3. **Given** 10 万样本，**When** 批量写入，**Then** 5 分钟内完成、行数一致。
4. **Given** 中途 schema 失败，**When** 写入，**Then** 整批回滚。
5. **Given** 租户 A，**When** 读取租户 B 版本，**Then** NotFound。

## 5. 关键实体

`project`、`datasource`、`dataset`、`dataset_version`、`sample`、`lineage_edge`。

## 6. 边界与异常

- 并发发布、哈希冲突、批量部分失败、大 payload、跨租户、血缘断链。

## 7. 不在范围

- 外部数据接入（`013-ingestion`）。
- 评测/门禁。

## 8. 依赖

`002-core`、`005-assets`、`004-audit`。
