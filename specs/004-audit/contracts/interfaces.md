# audit 公开契约

**模块**: M02 audit | **Owner**: agent-identity

## DTO / 协议

```python
@dataclass(frozen=True)
class AuditEvent:
    tenant_id: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    trace_id: str
    status: str
    created_at: datetime
    detail: dict = field(default_factory=dict)  # 不含 PII/密钥/正文

class AuditWriter(Protocol):
    def write(self, event: AuditEvent) -> None: ...

class AuditReader(Protocol):
    def query(self, ctx: TenantContext, *, actor: str | None = None,
              resource_type: str | None = None, since: datetime | None = None,
              cursor: str | None = None, limit: int = 20) -> Page[AuditEvent]: ...
```

## 保留与权限

- `audit_log`：append-only；按月分区；保留 180 天；过期 `DROP PARTITION`。
- 审计账号只有 `INSERT`；无 `UPDATE`/`DELETE`。
- 写入失败不得阻塞主请求，但必须告警（`audit_write_failed_total`）。
- 查询强制租户过滤；只读。

## MCP 复用

`mcp_tool_call` 继续由 `001-mcp-server` 使用；平台审计使用 `audit_log`，两者独立。
