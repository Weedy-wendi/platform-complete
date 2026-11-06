# functional 公开契约

**模块**: M12 functional | **Owner**: agent-functional

```python
@dataclass(frozen=True)
class TestStepResult:
    step_id: str
    status: Literal["passed", "failed", "skipped", "error"]
    duration_ms: int
    assertion: str | None
    evidence_ref: str | None

@dataclass(frozen=True)
class TestRunView:
    run_id: str
    suite_id: str
    suite_version: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    steps: list[TestStepResult]

class FunctionalTestService(Protocol):
    def start_run(self, ctx: TenantContext, suite_id: str) -> str: ...
    def get_run(self, ctx: TenantContext, run_id: str) -> TestRunView: ...
```

## 规则

1. 用例/套件版本化；租户隔离。
2. 浏览器在独立容器/进程执行；资源受限；网络白名单；超时强杀。
3. 证据（截图/录屏/console/network）存 artifact，不存 MySQL。
4. 视觉差异阈值可配；差异图可下钻。
5. 与 evaluation 共享 Evidence 展示，不共享表。
