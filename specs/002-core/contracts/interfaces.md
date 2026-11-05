# core 公开契约

**模块**: M00 core | **Owner**: agent-core

## DTO / 协议

```python
@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    subject_id: str
    scopes: frozenset[str]
    trace_id: str

class UnitOfWork(Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...

@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None = None
```

## 错误模型

```python
class AppError(Exception):
    code: str
    message: str
    http_status: int
    retryable: bool
    details: dict
```

- 领域错误不得包含堆栈、SQL、文件路径。
- HTTP 与 MCP 适配器负责映射；业务模块不得构造协议错误。

## 规则

1. Repository 必须自动注入 `tenant_id`；缺失 `TenantContext` 抛 `TenantRequiredError`。
2. 只读查询默认走只读会话；写操作显式 `write_session()`。
3. 所有 SQL 日志含 `trace_id`/`tenant_id`，不含参数值。
4. 架构测试禁止跨模块内部 import 与循环依赖。
