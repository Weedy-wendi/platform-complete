# Implementation Plan: jobs（M07）

**Feature**: `008-jobs` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- Celery + Redis broker；`acks_late=True`、`task_reject_on_worker_lost=True`、`prefetch_multiplier=1`。
- `visibility_timeout=6h`；幂等键唯一索引；重试 3 次指数退避 + 抖动。
- DLQ 表 + `pingce job replay` CLI；调度器 `GET_LOCK()`。
- 进度快照 + SSE；取消信号。

## 2. 数据模型

`job`、`job_event`、`dead_letter_task`、`idempotency_key`（唯一索引）。

## 3. 公开接口

`TaskRunner`、`JobHandler`、`JobSpec`、`JobView`。

## 4. 测试策略

- 集成：重复投递、崩溃、超时、取消、DLQ 重放。
- 契约：fake runner。
- 故障：Redis 不可用、Worker kill。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 重复副作用 | 幂等键唯一索引 |
| 任务丢失 | 持久化 + DLQ + 告警 |
| 多调度器 | `GET_LOCK()` |
| 无限重试 | 上限 + DLQ |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | job_event 可回放 |
| II 五原语 | Run 执行基础 |
| III API/CLI First | CLI replay |
| IV Boring Tech | Celery/Redis |
| V 控制/执行分离 | Worker 执行 |
| VI 证据驱动 | 故障注入测试 |
| VII 模块化单体 | 独立模块 |
