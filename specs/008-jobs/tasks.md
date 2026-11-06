# Tasks: jobs（M07）

**Source of truth**: `docs/planning/task-index.md`；明细见 `docs/planning/tasks/02-evaluation.md`。

- [X] JOB-01 `job`/`job_event` 模型与状态机
- [X] JOB-02 `TaskRunner` SPI + Celery
- [X] JOB-03 重试/幂等/DLQ
- [X] JOB-04 调度器单例
- [X] JOB-05 进度与 SSE
- [X] JOB-06 故障与恢复测试

## 交付检查

- [X] 重复投递只执行一次
- [X] 崩溃后可恢复
- [X] DLQ 可重放
- [X] 取消 5 秒内生效
