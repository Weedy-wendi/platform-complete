# identity 公开契约

**模块**: M01 identity | **Owner**: agent-identity

## DTO / 协议

```python
@dataclass(frozen=True)
class Principal:
    tenant_id: str
    subject_id: str
    scopes: frozenset[str]
    auth_method: Literal["api_key", "jwt"]
    expires_at: datetime | None = None
    client_id: str | None = None

class IdentityService(Protocol):
    def create_tenant(self, ctx: TenantContext, name: str, slug: str) -> TenantView: ...
    def create_user(self, ctx: TenantContext, email: str, roles: list[str]) -> UserView: ...
    def assign_role(self, ctx: TenantContext, user_id: str, role: str) -> None: ...

class ApiKeyVerifier(Protocol):
    def verify(self, raw_key: str) -> Principal: ...
```

## 权限与 Scope

- 默认拒绝；RBAC 由角色/权限组合。
- API Key scope 白名单：`mcp:projects:read`、`mcp:datasets:read`、`mcp:eval:read`、`mcp:eval:read_content`、`mcp:badcases:read`、`mcp:gate:read`；REST scope 在 `017-rest-api` 定义。
- 跨租户访问统一返回 `NotFound` / 403，不泄露存在性。

## API Key 格式

`pk_<env>_<key_id>_<secret>`

- 数据库只存 `HMAC-SHA256(pepper, secret)`。
- 明文只在签发响应出现一次。
- 吊销后 ≤60s 生效；缓存 TTL ≤60s。
- 未知 scope 拒绝签发。

## 事件

`identity.key.issued`、`identity.key.revoked`、`identity.role.changed`，写入审计。
