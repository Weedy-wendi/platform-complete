# Feature Specification: jobs（M07）

**Feature**: `008-jobs` | **Phase**: P0b | **Status**: Implemented

**任务**: JOB-01 ~ JOB-06（`docs/planning/tasks/02-evaluation.md`）

---

## 1. 模块职责

任务状态机、队列、重试、幂等、调度、死信。业务模块只注册 Handler，不直接操作 Celery。

## 2. 为什么做

评测、接入、索引、功能测试都是长任务；必须有可靠异步执行、幂等、重试、取消、恢复。

## 3. 功能需求

- **FR-001** `job`/`job_event` 状态机；事件 append-only；合法迁移。
- **FR-002** `TaskRunner` SPI + Celery；业务不依赖 Celery。
- **FR-003** 重试/幂等/DLQ：`acks_late`、`visibility_timeout=6h`、幂等键唯一索引；最多 3 次指数退避；DLQ 可重放/忽略。
- **FR-004** 调度器单例：MySQL `GET_LOCK()` leader election。
- **FR-005** 进度与 SSE：断线可回放；进度准确。
- **FR-006** 故障恢复：Worker 崩溃后可恢复/重放，不重复副作用。
- **FR-007** Redis 不可用时任务不丢失（持久化 + 告警）。

## 4. 验收场景

1. **Given** 同一任务投递两次，**When** 执行，**Then** 只产生一次副作用。
2. **Given** Worker 在事务中崩溃，**When** 重启，**Then** 任务重投且幂等。
3. **Given** 超过重试上限，**When** 失败，**Then** DLQ 有记录。
4. **Given** 取消请求，**When** 执行中，**Then** 停止取新 item。
5. **Given** 多副本，**When** 启动，**Then** 只有一个调度器。

## 5. 关键实体

`job`、`job_event`、`dead_letter_task`、`idempotency_key`。

## 6. 边界与异常

- 重复投递、Worker 崩溃、超时重投、取消、Redis 不可用、DLQ 重放。

## 7. 不在范围

- 业务 Handler 实现（由各模块提供）。

## 8. 依赖

`002-core`。
