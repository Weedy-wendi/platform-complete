# gate 公开契约

**模块**: M09 gate | **Owner**: agent-eval

```python
@dataclass(frozen=True)
class GateRule:
    name: str
    kind: Literal["absolute", "relative", "significance", "min_samples"]
    expected: str
    actual: str
    passed: bool
    evidence_ref: str | None

@dataclass(frozen=True)
class GateResult:
    tenant_id: str
    suite_id: str
    run_id: str
    manifest_hash: str
    passed: bool
    status: Literal["passed", "failed", "insufficient_data"]
    rules: list[GateRule]
    evaluated_at: datetime

class GateReader(Protocol):
    def read_gate(self, ctx: TenantContext, suite_id: str, run_id: str) -> GateResult | None: ...
```

## 不变量

1. 只读评测结果；不修改 Run/Score。
2. 样本量不足 → `insufficient_data`，不通过。
3. 结果绑定 `manifest_hash`；不可复现拒绝判定。
4. 每条规则有 expected/actual/passed/evidence。
5. 跨租户 NotFound。
