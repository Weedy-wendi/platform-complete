# evaluation 公开契约

**模块**: M06 evaluation | **Owner**: agent-eval

## DTO / 协议

```python
@dataclass(frozen=True)
class RunManifest:
    run_id: str
    dataset_hash: str
    evaluator_versions: list[dict]
    metric_configs: list[dict]
    target_config: dict
    sampling: dict
    code_version: str
    adapter_version: str
    target_config_version: str
    mode: Literal["record", "replay"]
    env: str

class EvaluationService(Protocol):
    def start_run(self, ctx: TenantContext, request: StartRunRequest) -> RunView: ...
    def compare(self, ctx: TenantContext, run_a: str, run_b: str) -> ComparisonView: ...

class RunReader(Protocol):
    def get_run(self, ctx: TenantContext, run_id: str) -> RunView: ...
    def list_items(self, ctx: TenantContext, run_id: str, query: RunItemQuery) -> Page[RunItemView]: ...

class TargetAdapter(Protocol):
    def invoke(self, ctx: TenantContext, request: AgentRequest) -> AgentResponse: ...

class TraceSource(Protocol):
    def fetch(self, ctx: TenantContext, trace_id: str) -> list[TraceSpan]: ...
```

## 不变量

1. Manifest 创建后不可修改；`manifest_hash` 稳定；重复 `client_request_id` 返回同一 `run_id`。
2. 单条失败不拖垮整 Run；取消保留已完成项。
3. 统计对比必须带置信信息；不把噪声当提升。
4. Replay 不调用 Agent；结果标注 `mode=replay`。
5. 适配器不写业务表；配置版本写入 Manifest。
6. 跨租户 Run/Item 一律 NotFound。
