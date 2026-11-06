# REST 错误码

**范围**: `017-rest-api`

## 响应格式

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Insufficient scope",
    "trace_id": "tr_...",
    "details": {"required_scope": "datasets:write"}
  }
}
```

- 不返回堆栈、SQL、文件路径。
- `trace_id` 必含，可跨 API/Worker 关联。

## 错误码

| HTTP | code | 说明 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 请求体/参数不合法 |
| 401 | `UNAUTHORIZED` | 缺失/无效/过期/吊销凭据 |
| 403 | `FORBIDDEN` | scope/角色不足 |
| 404 | `NOT_FOUND` | 资源不存在；跨租户也返回此码 |
| 409 | `CONFLICT` | 状态冲突、版本冲突、幂等冲突 |
| 409 | `INVALID_CURSOR` | 游标被篡改/过期/跨查询 |
| 422 | `UNPROCESSABLE` | 语义校验失败（如版本不可变） |
| 429 | `RATE_LIMITED` | 超限；带 `Retry-After` |
| 503 | `SERVICE_UNAVAILABLE` | DB/Redis/Qdrant 等依赖不可用 |
| 500 | `INTERNAL` | 未预期错误；不泄露内部细节 |

## 一致性

- API 错误码与 MCP 错误码保持语义一致；协议映射不同。
- `NOT_FOUND` 覆盖跨租户，避免存在性泄露。
- `Idempotency-Key` 冲突返回 `409 CONFLICT`，或返回首次结果（由实现选择并写入契约）。
