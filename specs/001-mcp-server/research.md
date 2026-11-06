# Research: MCP Server（HTTP 只读接入）

**Feature**: `001-mcp-server` | **Date**: 2026-11-05

本文件记录技术选型与协议事实，供实现阶段引用。结论均已固化到 `plan.md` 与 `ADR-005`。

---

## 1. MCP 协议基线

| 项目 | 结论 |
|---|---|
| 协议基线 | `2025-06-18` 修订版（含 `structuredContent`、resource links、elicitation） |
| 消息格式 | JSON-RPC 2.0 |
| 传输 | Streamable HTTP（单端点；`application/json` 或 `text/event-stream`） |
| 旧传输 | HTTP+SSE 已废弃，不实现 |
| 版本协商 | `MCP-Protocol-Version` 请求头；不支持则返回明确错误 |
| 会话 | 官方支持 `Mcp-Session-Id`，但本方案选择无状态，不依赖会话粘滞 |
| 服务端原语 | tools、resources、prompts；首期只实现 tools + resources |
| 客户端原语 | sampling、roots、elicitation；首期不使用 |
| 工具注解 | `readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint` |
| 错误表示 | 工具级错误用 `isError: true`；协议级错误用 JSON-RPC error |

**结论**：选择 Streamable HTTP + 无状态 + tools/resources。理由见 ADR-005。

---

## 2. SDK 选择

| 方案 | 优势 | 劣势 | 结论 |
|---|---|---|---|
| 官方 Python SDK `mcp` | 与规范同步、维护稳定、支持低层 Server 与 FastMCP | 版本迭代快，需锁定 | **采用** |
| FastMCP 2.x（独立项目） | 功能多、开发体验好 | 与官方 SDK 存在版本/API 差异，长期一致性风险 | 不采用 |
| 自研 JSON-RPC 层 | 完全可控 | 重复实现协议、易漏边界 | 不采用 |

**实现约束**：

- 锁定 `mcp` 版本；升级必须跑完整契约测试。
- 用低层 `Server` 显式注册工具，避免依赖装饰器隐式扫描（便于 allowlist 快照）。
- `tools/list` 输出必须与 `contracts/tools.yaml` 一致。

---

## 3. 无状态 vs 有状态

| 方案 | 优势 | 劣势 | 结论 |
|---|---|---|---|
| 无状态 | 任意副本可服务、无粘滞、扩缩容简单 | 无法保存跨请求上下文 | **采用** |
| 有状态 + `Mcp-Session-Id` | 支持会话级上下文 | 需要共享存储/粘滞，故障转移复杂 | 首期不用 |

只读工具均为「请求-响应」，无跨调用状态，无状态足够。

---

## 4. API Key 存储与校验

**关键结论：API Key 是高熵随机串，不需要 Argon2/bcrypt 这类慢哈希。**

| 方案 | 校验成本 | 适用 | 结论 |
|---|---|---|---|
| Argon2id | ~50–100ms/次 | 低熵密码 | 不采用（会拖垮 P95） |
| bcrypt | ~50ms/次 | 低熵密码 | 不采用 |
| **HMAC-SHA256(pepper, secret)** | 微秒级 | 高熵令牌 | **采用** |
| 明文存储 | 0 | 禁止 | 不采用 |

**格式**：`pk_<env>_<key_id>_<secret>`，其中 `secret` 为 32 字节随机值（base64url）。

**存储**：`key_id`（索引）、`secret_hmac`、`tenant_id`、`scopes`、`expires_at`、`revoked_at`、`last_used_at`。

**校验**：按 `key_id` 查找 → 常量时间比较 HMAC → 检查过期/吊销 → 缓存 Principal ≤ 60s。

**轮换**：新 Key 与旧 Key 并存 7 天 → 吊销旧 Key。吊销后 ≤ 60s 生效。

---

## 5. 游标分页

| 方案 | 问题 |
|---|---|
| offset/limit | 深分页慢；数据变动导致重复/漏项 |
| 自增 ID 游标 | 暴露内部 ID；跨租户可猜测 |
| **签名不透明游标** | **采用** |

**结构**：

```json
{"v":1,"t":"tenant_a","tool":"search_datasets","q":"<query_hash>","k":{"updated_at":"...","id":"..."},"exp":1730000000}
```

- `base64url(payload) + "." + base64url(HMAC-SHA256(secret, payload))`
- TTL 15 分钟
- 校验 `tenant_id`、`tool`、`query_hash`；任一不匹配 → `INVALID_CURSOR`

---

## 6. 限流算法

| 算法 | 优势 | 劣势 | 结论 |
|---|---|---|---|
| 固定窗口 | 实现最简单 | 窗口边界突刺 | 不用 |
| 滑动窗口（Redis ZSET） | 精确、可观测 | 内存随请求数增长 | 小流量可用 |
| **令牌桶（Redis Lua）** | 支持 burst、内存恒定 | Lua 脚本需维护 | **采用** |
| 本地令牌桶 | 无依赖 | 多副本不共享 | 仅作 Redis 故障兜底 |

**阈值**：Key 120 req/min（burst 20）；Tenant 600 req/min；重工具 30 req/min。

---

## 7. 结果限额

MCP 协议本身不限制结果大小；限制来自客户端上下文窗口与内存。

- 64KB 是经验值：足够返回 20–100 条摘要，又不会撑爆上下文。
- 超出：列表截断 + `next_cursor`；单对象 → `RESULT_TOO_LARGE` + resource link。
- 字符串字段 > 4KB 截断并标注 `truncated: true`。

---

## 8. 脱敏与 Prompt 注入

| 风险 | 处理 |
|---|---|
| 样本含手机号/邮箱/密钥 | 复用平台 PII 规则，正则 + 字段白名单 |
| 样本含指令文本 | 作为数据返回；响应中明确 `source: "dataset_sample"`，不执行 |
| `include_io` 泄露敏感内容 | 独立 scope `mcp:eval:read_content` + 脱敏 |
| 日志泄露 | 只记录长度/hash/`trace_id` |

---

## 9. OAuth 2.1 预留（不实现）

按规范，HTTP 传输的 MCP Server 应作为 **Resource Server**：

- 客户端从 IdP 获取 access token（PKCE）
- Token 携带 `aud` = MCP Server 的 canonical URI
- Server 通过 JWKS 验签，校验 `iss` / `aud` / `exp` / `scope`
- 401 返回 `WWW-Authenticate: Bearer resource_metadata="..."`
- `/.well-known/oauth-protected-resource` 返回 RFC 9728 元数据

**预留清单**见 ADR-005 决策点 3。首期只实现 `ApiKeyAuthProvider`；`OAuthResourceServerProvider` 保留接口与配置位。

---

## 10. 未决问题（已收敛）

| 问题 | 结论 |
|---|---|
| 是否支持 stdio？ | 否，仅 HTTP |
| 是否开放写工具？ | 否，首期只读 |
| 是否自建 OAuth？ | 否，未来复用 IdP |
| 是否需要会话？ | 否，无状态 |
| 是否直连 DB？ | 是，但使用受限账号；对外暴露时切 internal API |
| 是否需要 Prompts？ | 首期不需要，P2 再评估 |
| 是否需要 Sampling？ | 否，P3 再评估 |

---

## 参考

- MCP Specification `2025-06-18`
- RFC 8707 Resource Indicators
- RFC 9728 OAuth 2.0 Protected Resource Metadata
- OAuth 2.1 draft
