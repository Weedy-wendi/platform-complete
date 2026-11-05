# assets 公开契约

**模块**: M03 assets | **Owner**: agent-data

## DTO / 协议

```python
@dataclass(frozen=True)
class ArtifactRef:
    tenant_id: str
    artifact_id: str
    s3_key: str
    size_bytes: int
    sha256: str
    mime_type: str

class Storage(Protocol):
    def put(self, key: str, data: bytes, *, content_type: str) -> str: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def presign_get(self, key: str, *, ttl_seconds: int = 900) -> str: ...
    def presign_put(self, key: str, *, ttl_seconds: int = 900) -> str: ...

class ArtifactService(Protocol):
    def create(self, ctx: TenantContext, *, key: str, data: bytes, mime_type: str) -> ArtifactRef: ...
    def get(self, ctx: TenantContext, artifact_id: str) -> ArtifactRef: ...
```

## Key 规范

`tenant/{tenant_id}/{asset_type}/{asset_id}/{version}/{filename}`

## 规则

1. 业务代码只 import `Storage`，禁止直接依赖 `oss2` / `boto3`。
2. 禁止 public bucket；读取一律预签名，TTL ≤15 分钟。
3. 写入计算 `sha256`；读取校验 checksum。
4. 4xx 不重试；网络/5xx 可重试。
5. 二进制不入 MySQL；只存 `artifact` 元数据。
