# ADR-005: MCP 接入层（HTTP 只读 + API Key + OAuth 预留）

- **状态**: Accepted
- **日期**: 2026-11-05
- **决策者**: 产品负责人 + 架构
- **关联**: `constitution.md` v1.2.0、`specs/001-mcp-server/`

---

## 1. 背景

平台需要把「数据集检索、评测结果查询、Badcase 检索、门禁判定」等能力开放给 IDE 与 Agent（Claude Code、Cursor、自研 Agent）。MCP（Model Context Protocol）是这类集成的标准协议。

当前约束：

- 后端 FastAPI + MySQL 8.0 + Redis + 云 OSS + Qdrant
- 团队规模小，优先稳定与可维护
- 暂无企业 IdP（OIDC / SAML）
- 首期只需要「让 Agent 看懂平台数据」，不需要「让 Agent 改平台数据」

---

## 2. 决策

| 决策点 | 选择 |
|---|---|
| 传输 | **仅 Streamable HTTP**（不提供 stdio） |
| 读写范围 | **只读**，注册 10 个只读工具，不注册任何写工具 |
| 认证 | **API Key（Bearer）**；OAuth 2.1 通过 `AuthProvider` 抽象预留 |
| 进程形态 | 独立 `mcp-server` 进程，调用同仓 Application Service |
| 数据权限 | 专用数据库账号：业务表 `SELECT` + 审计表 `INSERT`，无 `UPDATE/DELETE/DDL` |
| 部署 | `https://<host>/mcp`，TLS 终止于 Ingress，网关 + 应用双层限流 |
| 协议基线 | MCP `2025-06-18` 修订版 |

---

## 3. 候选方案与反选论证

### 决策点 1：传输方式

| 方案 | 优势 | 劣势 | 适用场景 |
|---|---|---|---|
| A. stdio | 零部署、无网络攻击面、延迟最低 | 单机单人、无法集中审计、每人装 CLI | 个人本地工具 |
| B. Streamable HTTP | 团队共享、集中鉴权/审计/配额、远程 Agent 可用 | 有网络攻击面、需要 TLS/限流/多租户 | **本项目** |
| C. 两者都做 | 覆盖全部场景 | 双传输维护、双份测试、认证模型分裂 | 已有明确本地需求 |

**选择：B。**

**反选论证**：

- 不选 A：目标包含「团队/远程 Agent」，stdio 无法共享；且凭据散落在开发者电脑上，无法集中吊销与审计。
- 不选 C：当前没有离线/本地强需求；双传输会让认证、限流、审计出现两套语义，违反「减少组件与分支」原则。未来若出现本地需求，可在同一 `tool registry` 上增加 stdio entrypoint，不需要重写工具。

**接受的代价**：公网/内网攻击面扩大；必须做 TLS、鉴权、限流、审计；需要独立进程与部署单元。

**撤销条件**：出现明确的离线/本地 IDE 需求，且 HTTP 无法满足（如客户禁止出网）。

---

### 决策点 2：读写范围

| 方案 | 优势 | 劣势 | 适用场景 |
|---|---|---|---|
| A. 只读 | 无副作用、天然幂等、风险低、客户端可自动批准 | Agent 不能触发评测 | **首期** |
| B. 只读 + 写 | Agent 可自动跑回归、建 Badcase | 需要幂等/配额/确认/审计/回滚；Prompt 注入可造成真实损失 | 成熟期 |

**选择：A。**

**反选论证**：

- 不选 B：写操作需要一整套工程能力（幂等键、预算熔断、二次确认、before/after 审计、并发控制、补偿），当前不具备；且 `start_eval_run` 会直接产生 token 成本，Prompt 注入的后果从「泄露」升级为「烧钱 + 改数据」。
- 只读已覆盖日常 80% 价值：定位失败原因、对比两次 Run、检索相似 Badcase、查看数据集 Schema。

**接受的代价**：Agent 只能「看」，不能「做」；高价值动作仍需人回到 Web/CLI。

**撤销条件**：P1 完成写操作工程能力（幂等 + 配额 + 确认 + 审计 + 回滚）并通过独立威胁建模。

---

### 决策点 3：认证方式

| 方案 | 优势 | 劣势 | 适用场景 |
|---|---|---|---|
| A. 仅 API Key | 实现快、无需 IdP、IDE 配置简单 | 无 SSO/MFA、吊销粒度粗、无法表达用户身份 | 内部小团队 |
| B. 仅 OAuth 2.1 | 标准、支持 SSO/MFA、细粒度 scope | 需要 IdP、客户端配置复杂、上线慢 | 企业客户 |
| C. API Key + OAuth 预留 | 先上线，后续平滑迁移 | 需要提前抽象，短期多一层接口 | **本项目** |

**选择：C。**

**反选论证**：

- 不选 A：未来接企业 SSO 时要改鉴权中间件、Token 模型、工具代码，迁移成本高。
- 不选 B：当前没有 IdP；为一个只读、内部使用的服务引入 OAuth 授权服务器与客户端注册流程，投入产出比不合理。

**OAuth 预留清单（必须全部落地，否则视为未预留）**：

1. `AuthProvider` 协议 + `Principal` 模型（`tenant_id` / `subject` / `scopes` / `auth_method` / `expires_at`）。
2. 配置开关 `MCP_AUTH_MODE=api_key|oauth`；OAuth 模式下缺配置必须启动失败，禁止静默降级。
3. 预留 `/.well-known/oauth-protected-resource` 端点（OAuth 模式返回 RFC 9728 元数据；API Key 模式返回 404）。
4. 401 响应预留 `WWW-Authenticate: Bearer resource_metadata="..."`。
5. Token 校验位预留：`iss` / `aud` / `exp` / `scope`，并禁止 token passthrough。
6. 业务代码只依赖 `Principal`，禁止直接读取 `Authorization` 头。
7. Scope 常量集中定义，API Key 与 OAuth 共用同一套 scope 字符串。

**接受的代价**：无 SSO/MFA；API Key 需要自行轮换与吊销；无法区分「用户」与「服务」身份。

**撤销条件**：需要 SSO/MFA、对外部客户开放、或需要自助注册客户端 → 启用 OAuth 实现。

---

### 决策点 4：进程与数据访问

| 方案 | 优势 | 劣势 | 适用场景 |
|---|---|---|---|
| A. 挂载在 API 进程 | 改动最小、复用 DI | 发布耦合、暴露面扩大、故障互相影响 | 开发期 |
| B. 独立进程 + Service + 读写 DB | 隔离、无 HTTP 跳转 | MCP 进程持有写权限，风险高 | 不推荐 |
| B'. 独立进程 + Service + 受限 DB 账号 | 隔离、无额外一跳、DB 层兜底只读 | 仍持有 DB 凭证 | **首期** |
| C. 独立进程 + Internal API | 安全边界最干净、MCP 无 DB 凭证 | 多一跳、需维护 internal 契约 | 对外暴露时 |

**选择：B'。**

**反选论证**：

- 不选 A：MCP 协议演进与 API 发布耦合；长连接/流式响应会影响 API 稳定性。
- 不选 B：读写账号意味着一个工具实现 bug 就能改数据，违反「只读」承诺。
- 不选 C（当前）：需要额外建设 internal API 与服务间认证，P0 成本过高；B' 已能通过数据库授权把写风险降到最低。

**受限账号授权（精确到语句）**：

```sql
CREATE USER 'pingce_mcp'@'%' IDENTIFIED BY '<secret>';
GRANT SELECT ON pingce.* TO 'pingce_mcp'@'%';
GRANT INSERT ON pingce.mcp_tool_call TO 'pingce_mcp'@'%';
-- 不授予 UPDATE / DELETE / CREATE / ALTER / DROP
```

并设置会话级保护：

```sql
SET SESSION MAX_EXECUTION_TIME = 5000;
SET SESSION TRANSACTION READ ONLY;
```

审计写入使用独立连接（仅 `INSERT mcp_tool_call`），不参与业务只读事务。

**接受的代价**：MCP 进程仍持有数据库凭证；凭证泄露的影响面大于方案 C。

**撤销条件**：对外部客户开放、或合规要求「MCP 进程不得持有 DB 凭证」→ 切换方案 C。

---

## 4. 后果

### 正面

- 团队与远程 Agent 可共享同一套只读能力，无需每人安装。
- 集中鉴权、审计、限流、配额，满足企业交付基本要求。
- 只读范围把 Prompt 注入的破坏面限制在「数据外泄」而非「数据篡改 + 成本失控」。
- OAuth 预留使未来接 IdP 只需替换 `AuthProvider`，工具与业务代码零改动。
- 数据库授权提供最后一道防线：即使代码有 bug，也无法写业务表。

### 负面

- 多一个部署单元与一套监控。
- API Key 生命周期管理（签发、轮换、吊销）需要产品化。
- 无 SSO/MFA，短期不适合直接暴露给外部客户。
- MCP 进程持有 DB 凭证，安全等级低于 internal API 方案。

### 风险与缓解

| 风险 | 缓解 |
|---|---|
| API Key 泄露 | 最小 scope、可吊销、`last_used_at` 异常告警、IP allowlist（可选） |
| 跨租户越权 | Service 层强制 `tenant_id` 过滤 + 自动化越权测试 |
| Prompt 注入诱导外泄 | 结果大小上限、敏感字段脱敏、审计异常告警 |
| 单点故障 | 多副本 + readiness 检查 + 优雅停机 |
| 协议版本不兼容 | `MCP-Protocol-Version` 协商 + 明确错误码 |
| 只读承诺被破坏 | 工具注册表 allowlist + DB 授权 + CI 快照测试（禁止出现写工具） |

---

## 5. 验证方式

| 验证项 | 方法 | 通过标准 |
|---|---|---|
| 无写工具 | 对 `tools/list` 做快照测试 | 工具名集合与 allowlist 完全一致，无写动词 |
| 只读 DB | 用 `pingce_mcp` 账号执行 `INSERT/UPDATE/DELETE` | 全部被 MySQL 拒绝 |
| 跨租户 | 用租户 A 的 Key 查询租户 B 的资源 | 一律 403/404，且不泄露存在性 |
| 认证 | 缺失/错误/过期/吊销 Key | 401；scope 不足 403 |
| OAuth 预留 | 切换 `MCP_AUTH_MODE=oauth` + fake provider | 工具代码零改动即可通过 |
| 结果上限 | 构造超大结果 | 返回截断 + `next_cursor` 或 `RESULT_TOO_LARGE` |
| 性能 | 元数据类工具压测 | P95 < 300ms（不含网络） |
| 注入 | 样本中植入指令文本 | 仅作为数据返回，不触发任何工具调用 |

---

## 6. 参考

- MCP Specification `2025-06-18`（JSON-RPC 2.0、Streamable HTTP、tools/resources/prompts、tool annotations）
- OAuth 2.1、RFC 8707（Resource Indicators）、RFC 9728（Protected Resource Metadata）
- 项目宪法 v1.2.0「MCP 接入约束」
