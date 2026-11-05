# model_gateway 公开契约

**模块**: M10 model_gateway | **Owner**: agent-eval

## DTO / 协议

```python
@dataclass(frozen=True)
class ModelRequest:
    provider: str
    model: str
    messages: list[dict]
    temperature: float = 0.0
    seed: int | None = None
    timeout_seconds: float = 30.0

@dataclass(frozen=True)
class ModelResponse:
    text: str
    usage: dict
    cost_usd: float
    raw_ref: str | None = None
    finish_reason: str | None = None

class ModelGateway(Protocol):
    def complete(self, ctx: TenantContext, request: ModelRequest) -> ModelResponse: ...
```

## 规则

1. Provider 密钥使用 `secret_ref`；不落明文。
2. connect/read/total 三层超时；429/5xx 可重试；4xx 不重试。
3. 熔断可恢复；半开探测。
4. 每次调用写 `model_call`（token/成本/延迟/状态）。
5. 原始响应可存 artifact（`raw_ref`），供 Replay。
