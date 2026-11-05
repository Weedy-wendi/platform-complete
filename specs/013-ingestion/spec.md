# Feature Specification: ingestion（M05）

**Feature**: `013-ingestion` | **Phase**: P1 | **Status**: Implemented

**任务**: ING-01 ~ ING-08（`docs/planning/tasks/01-data.md`）

---

## 1. 模块职责

连接器、同步任务、Schema 推断/漂移、清洗、质检。把外部数据变成 catalog 的版本。

## 2. 为什么做

平台需要持续接入 CSV/JSONL/REST 数据；同步必须可中断、可续传、可重试、不重复。

## 3. 功能需求

- **FR-001** Connector SPI：`discover`/`read`/`cursor`；可插拔。
- **FR-002** CSV/JSONL：本地/OSS；UTF-8/GBK；分隔符；大文件流式。
- **FR-003** REST：分页、鉴权、超时、重试。
- **FR-004** 同步任务与水位：`sync_cursor` 断点续传；幂等；取消 5 秒内生效；失败入 DLQ。
- **FR-005** Schema 推断/漂移：新/删/改字段分别告警。
- **FR-006** 清洗：去重、脱敏、格式转换；可配置、可预览。
- **FR-007** 质检：规则可配；结果可追溯。

## 4. 验收场景

1. **Given** 同步中断，**When** 恢复，**Then** 从水位续传、行数正确。
2. **Given** 重复投递，**When** 执行，**Then** 不重复写入。
3. **Given** 取消，**When** 执行中，**Then** 5 秒内停止，水位不推进。
4. **Given** Schema 漂移，**When** 下次同步，**Then** 告警并记录。
5. **Given** 质检规则，**When** 运行，**Then** 结果可追溯。

## 5. 关键实体

`connector`、`ingestion_job`、`sync_cursor`、`quality_rule`、`quality_result`。

## 6. 边界与异常

- 大文件/编码错误/分页中断/取消、重复投递、DLQ、Schema 漂移、跨租户。

## 7. 不在范围

- 浏览器/API 功能测试（`015-functional`）。
- 语义检索（`014-search`）。

## 8. 依赖

`007-catalog`、`008-jobs`、`005-assets`、`004-audit`。
