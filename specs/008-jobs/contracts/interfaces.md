# jobs 公开契约

**模块**: M07 jobs | **Owner**: agent-eval

## DTO / 协议

```python
@dataclass(frozen=True)
class JobSpec:
    job_type: str
    payload: dict
    idempotency_key: str
    timeout_seconds: int

class TaskRunner(Protocol):
    def enqueue(self, spec: JobSpec) -> str: ...
    def cancel(self, job_id: str, ctx: TenantContext) -> None: ...

class JobHandler(Protocol):
    def handle(self, job: JobView) -> None: ...
```

## 状态机

`queued → running → succeeded | failed | cancelled | timed_out`

- 非法迁移拒绝；`job_event` append-only。
- 重试最多 3 次，指数退避 + 抖动；不可重试错误直接 DLQ。
- 幂等键 `hash(job_id, item_id, attempt)` 唯一索引。
- DLQ 可查询、可重放、可忽略。
- 调度器单例：MySQL `GET_LOCK()`。
- 进度：快照 + SSE，断线可回放。
