# reporting 公开契约

**模块**: M08 reporting | **Owner**: agent-eval

```python
@dataclass(frozen=True)
class RunReport:
    run_id: str
    manifest_hash: str
    format: Literal["markdown", "json"]
    content: str  # 或 artifact ref
    generated_at: datetime

@dataclass(frozen=True)
class ComparisonReport:
    run_a: str
    run_b: str
    metrics: list[dict]
    regressions: list[dict]
    improvements: list[dict]
    warnings: list[str]

class ReportReader(Protocol):
    def get_run_report(self, ctx: TenantContext, run_id: str, fmt: str) -> RunReport: ...
    def compare_report(self, ctx: TenantContext, run_a: str, run_b: str) -> ComparisonReport: ...
    def export(self, ctx: TenantContext, run_id: str, fmt: Literal["json", "csv", "junit"]) -> bytes: ...
```

## 规则

1. 只读；不写业务表。
2. 报告绑定 `manifest_hash`；快照不可变。
3. 读模型查询 P95 <300ms；不跨模块 JOIN。
4. 导出流式；大数据不一次性加载。
5. 分享链接签名 + TTL；不可枚举；越权拒绝。
