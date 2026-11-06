# Quickstart: 连接 Pingce MCP Server

**Feature**: `001-mcp-server` | **Audience**: 使用 IDE / Agent 的程序员

本指南假设服务已部署在 `https://pingce.example.com/mcp`，且你已获得只读 API Key。

---

## 1. 前置条件

- 服务地址（内网/VPN 可达）
- 一个只读 API Key：`pk_live_xxxxxxxxxxxxxxxx`
- Key 至少包含以下 scope 之一：
  - `mcp:projects:read`
  - `mcp:datasets:read`
  - `mcp:eval:read`
  - `mcp:eval:read_content`（可选，允许查看脱敏后的输入/输出）
  - `mcp:badcases:read`
  - `mcp:gate:read`

> API Key 只显示一次；丢失请重新签发。吊销后 ≤ 60 秒生效。

---

## 2. 配置 IDE

### 通用 HTTP 配置

```json
{
  "mcpServers": {
    "pingce": {
      "type": "http",
      "url": "https://pingce.example.com/mcp",
      "headers": {
        "Authorization": "Bearer pk_live_xxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add --transport http pingce https://pingce.example.com/mcp \
  --header "Authorization: Bearer pk_live_xxxxxxxxxxxxxxxx"
```

### Cursor

在 `.cursor/mcp.json` 中使用上面的通用配置。

> 不同客户端字段名可能略有差异，以客户端官方文档为准。

---

## 3. 手工验证

### 3.1 initialize

```bash
curl -sS https://pingce.example.com/mcp \
  -H "Authorization: Bearer pk_live_xxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: 2025-06-18" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-06-18",
      "capabilities": {},
      "clientInfo": {"name": "curl", "version": "0.0.1"}
    }
  }'
```

期望：HTTP 200，返回 `serverInfo` 与 `capabilities.tools`。

### 3.2 完成初始化通知

```bash
curl -sS https://pingce.example.com/mcp \
  -H "Authorization: Bearer pk_live_xxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'
```

### 3.3 列出工具

```bash
curl -sS https://pingce.example.com/mcp \
  -H "Authorization: Bearer pk_live_xxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

期望：返回 10 个工具，全部 `readOnlyHint: true`。

### 3.4 检索数据集

```bash
curl -sS https://pingce.example.com/mcp \
  -H "Authorization: Bearer pk_live_xxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "search_datasets",
      "arguments": {"query": "客服", "limit": 5}
    }
  }'
```

### 3.5 查询一次 Run

```bash
curl -sS https://pingce.example.com/mcp \
  -H "Authorization: Bearer pk_live_xxxxxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "get_run",
      "arguments": {"run_id": "run_01JABCDEF"}
    }
  }'
```

---

## 4. 推荐提问方式

连接成功后，可以直接对 Agent 说：

- 「列出最近更新的三个数据集，并说明字段结构。」
- 「run_01JABCDEF 为什么失败？给我失败最多的 10 条样本。」
- 「对比 run_A 和 run_B，哪些指标变差了？是否显著？」
- 「找一下和『退款流程』相关的 Badcase。」
- 「这个 Suite 在 run_01JABCDEF 上过门禁了吗？哪条规则没过？」

---

## 5. 只读验证

确认平台没有开放写能力：

1. `tools/list` 返回的 10 个工具全部带 `readOnlyHint: true`。
2. 尝试调用不存在的工具名（如 `start_eval_run`），应返回「工具不存在」，而不是执行。
3. 用只读 Key 调用任何写接口，应返回 403。

---

## 6. 故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 401 | Key 缺失/错误/过期/吊销 | 检查 `Authorization` 头；重新签发 |
| 403 | scope 不足 | 让管理员补 scope |
| 404 | 地址错误 | 确认是 `/mcp`，不是 `/mcp/` |
| 429 | 触发限流 | 按 `Retry-After` 等待；降低并发 |
| 406 / 协议错误 | `MCP-Protocol-Version` 不支持 | 使用 `2025-06-18` |
| 503 | DB/Redis 不可用 | 稍后重试；联系平台方 |
| 结果为空 | 租户不匹配或无数据 | 确认 Key 所属租户 |
| `INVALID_CURSOR` | 游标过期/被篡改 | 重新发起第一页请求 |
| `RESULT_TOO_LARGE` | 单对象超 64KB | 改用 Resource 或分页 |
| `degraded: true` | 语义检索不可用 | 结果仍可用，已降级为关键词 |

---

## 7. 安全注意事项

- 不要把 API Key 提交到 Git；使用环境变量或客户端密钥管理。
- 只申请需要的 scope；不要为了方便申请全部权限。
- Key 泄露立即吊销并重新签发。
- 平台永远不会通过 MCP 返回完整密钥、完整 Prompt 或未脱敏样本。
- 平台不会提供任何写工具；如看到写工具，说明配置被篡改，请立即报障。
