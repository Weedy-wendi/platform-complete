# Implementation Plan: ingestion（M05）

**Feature**: `013-ingestion` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- Connector SPI + JobHandler；`sync_cursor` 水位；幂等键；DLQ。
- CSV/JSONL 流式；REST 分页/重试。
- Schema 推断/漂移；清洗/质检规则引擎。

## 2. 数据模型

`connector`、`ingestion_job`、`sync_cursor`、`quality_rule`、`quality_result`。

## 3. 公开接口

`Connector`、`ConnectorCursor`、`SyncResult`、`IngestionService`。

## 4. 测试策略

- 集成：续传、幂等、取消、DLQ、Schema 漂移、清洗、质检。
- 契约：fake connector。
- 安全：跨租户、密钥、PII。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 水位先推进 | 批次成功后推进 |
| 重复写入 | 幂等键 |
| 大文件 OOM | 流式 |
| 编码错误 | 明确报错 |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | 水位/幂等/版本 |
| II 五原语 | Asset/Version |
| III API/CLI First | Service/REST |
| IV Boring Tech | 标准连接器 |
| V 控制/执行分离 | Worker 执行 |
| VI 证据驱动 | 续传/幂等测试 |
| VII 模块化单体 | 独立模块 |
