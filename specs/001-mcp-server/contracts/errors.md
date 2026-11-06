# MCP Error Contracts

**Feature**: `001-mcp-server` | **Version**: 1.0.0

错误分为三层：HTTP 状态、JSON-RPC 错误、工具级错误。三层必须一致，不得出现「HTTP 200 + 静默失败」。

---

## 1. HTTP 层

| 状态 | 场景 | 响应头 |
|---|---|---|
| 200 | 请求已处理（含工具级错误） | `Content-Type: application/json` |
| 400 | 请求体非法 / 非 JSON-RPC | — |
| 401 | 缺失、无效、过期、吊销的 API Key | `WWW-Authenticate: Bearer` |
| 403 | scope 不足 / 租户不匹配 | — |
| 404 | 端点不存在 | — |
| 413 | 请求体超过 256KB | — |
| 429 | 触发限流 | `Retry-After: <seconds>` |
| 503 | 服务级依赖不可用（DB/Redis 整体不可用） | `Retry-After: <seconds>` |

> 业务资源的「不存在」在工具层返回 `NOT_FOUND`（HTTP 200 + JSON-RPC error），不返回 HTTP 404，避免与协议错误混淆。

---

## 2. JSON-RPC 错误

| Code | 名称 | 说明 |
|---|---|---|
| -32700 | Parse error | JSON 解析失败 |
| -32600 | Invalid Request | 非法 JSON-RPC 对象 |
| -32601 | Method not found | 未实现的方法 |
| -32602 | Invalid params | 入参 Schema 校验失败 |
| -32603 | Internal error | 未预期异常 |
| -32000 | Server error | 业务错误（见下表） |

标准结构：

```json
{
  "jsonrpc": "2.0",
  "id": "req_123",
  "error": {
    "code": -32000,
    "message": "Run not found",
    "data": {
      "code": "NOT_FOUND",
      "retryable": false,
      "trace_id": "4f2a9c1e8b7d4a6f9e0c3b2a1d5f8e7c"
    }
  }
}
```

---

## 3. 业务错误码

| code | HTTP | retryable | 说明 |
|---|---|---|---|
| `UNAUTHORIZED` | 401 | false | 缺失/无效/过期/吊销的 Key |
| `FORBIDDEN` | 403 | false | scope 不足或租户不匹配 |
| `NOT_FOUND` | 200 | false | 资源不存在或不可见（不区分） |
| `INVALID_CURSOR` | 200 | false | 游标篡改/过期/跨查询复用 |
| `INVALID_ARGUMENT` | 200 | false | 参数语义非法（非 Schema 层） |
| `RATE_LIMITED` | 429 | true | 超限；按 `Retry-After` 重试 |
| `RESULT_TOO_LARGE` | 200 | false | 单对象超 64KB；改用 Resource |
| `UPSTREAM_UNAVAILABLE` | 200 | true | 工具级依赖不可用（Qdrant/Gate 未就绪） |
| `SERVICE_UNAVAILABLE` | 503 | true | 服务级依赖不可用（DB/Redis 整体不可用） |
| `DEGRADED` | 200 | true | 已降级返回（如关键词检索），结果可用 |
| `INTERNAL` | 200 | true | 未预期异常；带 `trace_id` |

---

## 4. 安全约束

- 错误响应 MUST NOT 包含：堆栈、SQL、文件路径、内部主机名、完整 API Key、完整样本内容。
- `NOT_FOUND` 与 `FORBIDDEN` 的响应时间必须接近，避免通过时序判断资源是否存在。
- `trace_id` 必须返回，便于用户报障与日志检索。
- 鉴权失败不返回「Key 是否存在」「租户是否存在」等细节。

---

## 5. 示例

### 401

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="pingce-mcp"

{"jsonrpc":"2.0","id":null,"error":{"code":-32000,"message":"Unauthorized","data":{"code":"UNAUTHORIZED","retryable":false,"trace_id":"..."}}}
```

### 403

```json
{"jsonrpc":"2.0","id":"req_2","error":{"code":-32000,"message":"Insufficient scope","data":{"code":"FORBIDDEN","required_scope":"mcp:eval:read_content","retryable":false,"trace_id":"..."}}}
```

### 429

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 7
```

```json
{"jsonrpc":"2.0","id":"req_3","error":{"code":-32000,"message":"Rate limited","data":{"code":"RATE_LIMITED","limit":120,"window_seconds":60,"retryable":true,"trace_id":"..."}}}
```

### 工具级错误（HTTP 200）

```json
{
  "jsonrpc": "2.0",
  "id": "req_4",
  "result": {
    "isError": true,
    "content": [{"type": "text", "text": "Run not found"}],
    "structuredContent": {
      "code": "NOT_FOUND",
      "retryable": false,
      "trace_id": "..."
    }
  }
}
```

---

## 6. 错误码与工具映射

| 工具 | 可能错误 |
|---|---|
| `list_projects` | UNAUTHORIZED, FORBIDDEN, RATE_LIMITED, INVALID_CURSOR |
| `search_datasets` | UNAUTHORIZED, FORBIDDEN, RATE_LIMITED, INVALID_CURSOR |
| `get_dataset_schema` | UNAUTHORIZED, FORBIDDEN, NOT_FOUND, RATE_LIMITED, RESULT_TOO_LARGE |
| `preview_samples` | UNAUTHORIZED, FORBIDDEN, NOT_FOUND, RATE_LIMITED, INVALID_CURSOR, RESULT_TOO_LARGE |
| `list_evaluators` | UNAUTHORIZED, FORBIDDEN, RATE_LIMITED |
| `get_run` | UNAUTHORIZED, FORBIDDEN, NOT_FOUND, RATE_LIMITED |
| `get_run_items` | UNAUTHORIZED, FORBIDDEN, NOT_FOUND, RATE_LIMITED, INVALID_CURSOR, RESULT_TOO_LARGE |
| `compare_runs` | UNAUTHORIZED, FORBIDDEN, NOT_FOUND, RATE_LIMITED |
| `search_badcases` | UNAUTHORIZED, FORBIDDEN, RATE_LIMITED, INVALID_CURSOR, UPSTREAM_UNAVAILABLE（降级通过 `degraded=true` 表达，不是错误） |
| `check_gate` | UNAUTHORIZED, FORBIDDEN, NOT_FOUND, RATE_LIMITED, UPSTREAM_UNAVAILABLE |
