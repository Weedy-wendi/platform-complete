# Implementation Plan: MCP Server（HTTP 只读接入）

**Branch**: `001-mcp-server` | **Date**: 2026-11-05 | **Spec**: [spec.md](./spec.md)

**Input**: `specs/001-mcp-server/spec.md`

---

## Summary

新增独立 `mcp-server` 进程，通过 Streamable HTTP 暴露 10 个只读工具，覆盖「数据集探索、评测结果查询、Badcase 检索、门禁查询」。认证使用 API Key，鉴权通过 `AuthProvider` 抽象，OAuth 2.1 仅预留接口。业务数据通过同仓 Application Service 读取，数据库使用受限账号（业务表只读 + 审计表写入）。不提供 stdio，不提供任何写工具。

---

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**:
- `mcp`（官方 Python SDK，锁定版本）
- `starlette` + `uvicorn`（独立 ASGI 进程）
- `pydantic` v2（工具 I/O Schema）
- `SQLAlchemy` 2.0（同步）+ `PyMySQL`
- `redis`（限流）
- `hmac` + `hashlib`（API Key 哈希、游标签名）
- `opentelemetry-sdk` / `prometheus-client`

**Storage**:
- MySQL 8.0：业务表只读；`mcp_tool_call` 仅 INSERT
- Redis：限流计数器、API Key 校验缓存（TTL ≤ 60s）

**Testing**: `pytest`、`pytest-asyncio`、`testcontainers`（MySQL/Redis）、自建 MCP 契约测试夹具

**Target Platform**: Linux 容器（Docker），部署于内网 / VPN 后

**Project Type**: Web service（协议适配层）

**Performance Goals**:
- 元数据类工具 P95 < 300ms
- 样本/明细类工具 P95 < 1s
- 单实例 50 QPS，水平扩展至 3 副本

**Constraints**:
- 只读；单次结果 ≤ 64KB；工具调用 ≤ 25s
- 无状态；不依赖会话粘滞
- MCP 协议基线 `2025-06-18`
- 数据库账号无业务写权限

**Scale/Scope**:
- 首期 10 个租户、100 个并发 IDE 会话
- 10 个只读工具、3 个 Resource

---

## Constitution Check

*GATE: 必须通过；实现后复检。*

| 宪法条款 | 本方案落实 | 结论 |
|---|---|---|
| I. 可复现优先 | MCP 只读，不产生新的 Run；返回的 Run 结果附带 `manifest_hash` 与版本 | ✅ |
| II. 五原语内核 | 工具映射到既有 Asset/Run/Evidence/Gate，不新增业务实体 | ✅ |
| III. API/CLI First | MCP 是第 5 接入层；底层复用既有 API 能力 | ✅ |
| IV. 稳定优先 | 无状态、LTS 依赖、超时/限流/降级齐备、无新技术栈 | ✅ |
| V. 控制面/执行面分离 | 独立进程；不执行长任务；不承载写操作 | ✅ |
| VI. 证据驱动 | 契约测试、越权测试、DB 授权验证、压测基线 | ✅ |
| VII. 模块化单体 | 同仓 `app/mcp` 模块 + 独立 entrypoint，不拆微服务 | ✅ |
| MCP 接入约束 §1 | 工具只调用 Service；生产形态不直连业务写 | ✅（受限账号，见 ADR-005 决策点 4） |
| MCP 接入约束 §3 | 10 个只读工具；无 SQL/URL/代码执行；结果 ≤ 64KB | ✅ |
| MCP 接入约束 §5 | API Key + OAuth 预留；scope + 租户绑定 | ✅ |

**唯一偏离**：MCP 进程持有数据库凭证（方案 B'）。已用「业务表只读 + 审计表仅 INSERT + `MAX_EXECUTION_TIME`」缓解；对外暴露时切换 internal API（方案 C）。记录于 ADR-005，撤销条件明确。

---

## Project Structure

### Documentation (this feature)

```text
specs/001-mcp-server/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── tools.yaml
│   └── errors.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── services/                 # 既有：框架无关的应用服务（本特性复用）
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── server.py             # MCP 协议装配（transport-agnostic）
│   │   ├── registry.py           # 工具 allowlist + 版本 + scope 映射
│   │   ├── context.py            # Principal / TenantContext
│   │   ├── auth/
│   │   │   ├── base.py           # AuthProvider 协议
│   │   │   ├── api_key.py        # 首期实现
│   │   │   └── oauth_stub.py     # OAuth 预留（未启用）
│   │   ├── tools/
│   │   │   ├── projects.py
│   │   │   ├── datasets.py
│   │   │   ├── evaluation.py
│   │   │   └── badcases.py
│   │   ├── resources/
│   │   │   ├── datasets.py
│   │   │   └── reports.py
│   │   ├── limits.py             # 结果大小、分页、脱敏
│   │   ├── cursor.py             # 签名游标
│   │   ├── errors.py             # 错误码与映射
│   │   ├── audit.py              # mcp_tool_call 写入
│   │   └── observability.py      # OTel / Prometheus
│   └── cli/
│       └── mcp.py                # pingce mcp serve --http
├── migrations/                   # api_key 扩列、mcp_tool_call 建表
└── tests/
    ├── contract/
    ├── integration/
    ├── security/
    └── load/
```

**Structure Decision**: 复用既有 `backend/app/services`，新增 `app/mcp` 模块与独立 entrypoint；不引入新仓库、不拆微服务。

---

## Design

### 1. 进程与传输

```text
Client (IDE / Agent)
   │  POST /mcp  (JSON-RPC 2.0, Bearer)
   ▼
Ingress (TLS, WAF, IP allowlist)
   ▼
mcp-server (uvicorn + Starlette)
   ├── AuthProvider → Principal
   ├── RateLimiter (Redis)
   ├── ToolRegistry (allowlist)
   └── Application Services (in-process)
          ├── MySQL (受限账号)
          └── Redis (限流/缓存)
```

- 单端点 `/mcp`；无状态；不签发 `Mcp-Session-Id`。
- 同时支持 `application/json` 与 `text/event-stream` 响应；首期只读工具均为短请求，默认 JSON。
- 优雅停机：收到 SIGTERM 后停止接受新连接，等待 in-flight ≤ 30s。

### 2. AuthProvider 抽象

```python
class Principal(BaseModel):
    tenant_id: str
    subject: str
    scopes: frozenset[str]
    auth_method: Literal["api_key", "oauth"]
    expires_at: datetime | None
    client_id: str | None = None

class AuthProvider(Protocol):
    async def authenticate(self, request: Request) -> Principal: ...
```

- `ApiKeyAuthProvider`：解析 Bearer → 取 `key_id` → 查缓存/DB → 常量时间比对 HMAC → 返回 Principal。
- `OAuthResourceServerProvider`：预留，校验 JWT 签名（JWKS）、`iss`、`aud`、`exp`、`scope`；拒绝 token passthrough（受众非本服务的 token）。
- 工厂：`build_auth_provider(settings)`；`MCP_AUTH_MODE=oauth` 且配置缺失时启动失败。
- 业务代码只依赖 `Principal`，不感知认证方式。

### 3. 工具注册表（只读 allowlist）

```python
READ_ONLY_TOOLS = {
    "list_projects", "search_datasets", "get_dataset_schema",
    "preview_samples", "list_evaluators", "get_run", "get_run_items",
    "compare_runs", "search_badcases", "check_gate",
}
```

- 启动时断言：注册表 ⊆ `READ_ONLY_TOOLS`；发现未知工具直接启动失败。
- 每个工具声明：`name`、`version`、`scopes`、`input_model`、`output_model`、`handler`。
- CI 快照测试比对 `tools/list` 输出与 `contracts/tools.yaml`。

### 4. 只读保障（三层）

| 层 | 机制 |
|---|---|
| 注册表 | 只允许 allowlist；写工具无法注册 |
| Service | 复用只读查询方法；不存在写路径 |
| 数据库 | `pingce_mcp_ro` 仅 `SELECT`；`pingce_mcp_audit` 仅 `INSERT mcp_tool_call`；`MAX_EXECUTION_TIME=5000` |

**工具实现边界**：`search_badcases` 必须调用 `search.SemanticSearch`，`check_gate` 必须调用 `gate.GateReader`；MCP 模块不得实现检索、降级或门禁判定逻辑。依赖未就绪时返回 `UPSTREAM_UNAVAILABLE`，不得从 allowlist 移除。

### 5. 请求生命周期

```text
POST /mcp
 → 解析 JSON-RPC（大小上限 256KB）
 → AuthProvider.authenticate
 → 限流（Key + Tenant）
 → 路由 t_method
 → tools/call: 校验 scope → Pydantic 校验入参
 → 调用 Service（注入 TenantContext；Repository 基类自动追加 tenant_id）
 → 结果裁剪/脱敏/分页
 → 审计（异步，不阻塞）
 → JSON-RPC 响应
```

### 6. 游标设计

- 内容：`{v, tenant_id, tool, query_hash, last_key, exp}`。
- 编码：`base64url(payload) + "." + base64url(HMAC-SHA256(secret, payload))`。
- TTL 15 分钟；租户或查询指纹不匹配 → `INVALID_CURSOR`。
- 禁止使用 offset；所有列表按稳定键排序（`updated_at DESC, id DESC`）。

### 7. 结果限额与脱敏

- 序列化后 > 64KB：列表截断 + `truncated=true` + `next_cursor`；单对象超限 → `RESULT_TOO_LARGE`。
- 字符串字段 > 4KB 截断并标注。
- 样本预览：按平台 PII 规则脱敏；`include_io` 需要 `mcp:eval:read_content` scope。

### 8. 限流

- Redis 滑动窗口：Key 维度 120 req/min（burst 20）；Tenant 600 req/min。
- 重工具（`preview_samples`、`get_run_items`）单独 30 req/min。
- Redis 不可用：本地令牌桶兜底（保守值），并告警；宁可拒绝，不可放大。

### 9. 错误模型

- HTTP 层：401 / 403 / 429 / 503。
- JSON-RPC：`-32700`、`-32600`、`-32601`、`-32602`、`-32603`、`-32000`。
- 业务错误码见 `contracts/errors.md`；响应含 `trace_id`。

### 10. 可观测

- Span：`mcp.request`、`mcp.tool.call`；属性含 tool、version、tenant、auth_method、transport。
- Metrics：`mcp_tool_calls_total`、`mcp_tool_duration_seconds`、`mcp_tool_result_bytes`、`mcp_auth_failures_total`、`mcp_rate_limited_total`、`mcp_cursor_invalid_total`。
- 日志：结构化 JSON，含 `trace_id` / `tenant_id` / `tool` / `status`；不记录完整参数。

### 11. 部署

```yaml
mcp-server:
  command: ["pingce", "mcp", "serve", "--http", "--host", "0.0.0.0", "--port", "8765"]
  env:
    MCP_AUTH_MODE: api_key
    MCP_MAX_RESULT_BYTES: "65536"
    MCP_CURSOR_SECRET: <secret>
    MCP_API_KEY_PEPPER: <secret>
    MCP_DB_DSN: <read-only-account>
    MCP_AUDIT_DSN: <audit-insert-account>
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8765/readyz"]
```

- Ingress：`/mcp` → `mcp-server:8765`；TLS；请求体上限 256KB；连接超时 30s。
- 默认仅内网/VPN 可达；公网暴露需 WAF + IP allowlist + 独立安全评审。

---

## Phase Plan

| 阶段 | 内容 | 产出 |
|---|---|---|
| Phase 0 | 协议与依赖验证 | `research.md`；最小 `initialize` + `tools/list` 可跑通 |
| Phase 1 | 认证、注册表、限额、审计、错误模型 | 基础设施完成 |
| Phase 2 | US1 连接与发现 | MCP 客户端可连接 |
| Phase 3 | US2 数据集工具 | 4 个数据集工具 |
| Phase 4 | US3 评测工具 | 4 个评测工具 |
| Phase 5 | US4 Badcase / Gate | 2 个工具 |
| Phase 6 | 安全、压测、文档 | 上线就绪 |

---

## Complexity Tracking

| 偏离 | 原因 | 更简单的替代为何不够 |
|---|---|---|
| MCP 进程持有 DB 凭证（B'） | 避免 P0 建设 internal API 与服务间认证 | Internal API 方案安全边界更好，但 P0 成本高、交付慢；已用受限账号把写风险降到数据库层 |

---

## Risks

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| MCP SDK 版本破坏性变更 | 中 | 中 | 锁定版本；协议层薄封装；契约测试 |
| API Key 泄露 | 中 | 高 | 最小 scope、可吊销、异常告警、IP allowlist |
| 跨租户越权 | 低 | 极高 | Service 层强制过滤 + 自动化越权测试 + DB 行数断言 |
| 大结果拖垮内存 | 中 | 中 | 流式裁剪 + 64KB 上限 + 分页 |
| 只读副本延迟导致结果不一致 | 中 | 低 | 响应标注 `as_of`；写后读场景回主库 |
| 限流误伤正常用户 | 中 | 低 | 分工具阈值 + 429 带 `Retry-After` + 监控调整 |
