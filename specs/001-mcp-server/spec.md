# Feature Specification: MCP Server（HTTP 只读接入）

**Feature Branch**: `001-mcp-server`

**Created**: 2026-11-05

**Status**: Draft

**Input**: 为 Pingce 平台的部分功能提供 MCP 服务；仅 Streamable HTTP；只读；API Key 认证并预留 OAuth 接口。

**关联文档**: `docs/adr/ADR-005-mcp-access-layer.md`、`constitution.md` v1.2.0

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 在 IDE 中连接并发现能力 (Priority: P1)

程序员在 Claude Code / Cursor 中配置 Pingce MCP 地址与 API Key，连接成功后能看到平台提供的只读工具列表，并能确认这些工具不会修改任何数据。

**Why this priority**: 连接与发现是所有后续能力的前提；没有它，其余工具不可用。

**Independent Test**: 只实现协议握手、认证与 `tools/list`，即可用任意 MCP 客户端完成连接并看到 10 个只读工具。

**Acceptance Scenarios**:

1. **Given** 一个有效且未过期的 API Key，**When** 客户端发送 `initialize`，**Then** 返回协议版本、`serverInfo` 与 `capabilities.tools`，HTTP 状态 200。
2. **Given** 已连接，**When** 客户端发送 `tools/list`，**Then** 返回 10 个工具，且每个工具的 `annotations.readOnlyHint = true`。
3. **Given** 缺失、错误或已吊销的 Key，**When** 客户端发送任意请求，**Then** 返回 401，并带 `WWW-Authenticate: Bearer`。
4. **Given** Key 缺少某个工具所需的 scope，**When** 调用该工具，**Then** 返回 403 与机器可读错误码，且不泄露资源是否存在。
5. **Given** 客户端声明了不支持的 `MCP-Protocol-Version`，**When** 发送请求，**Then** 返回明确错误，不静默降级。

---

### User Story 2 - 探索数据集与样本 (Priority: P1)

程序员让 Agent 查找某个数据集、查看字段结构、预览少量样本，以便判断该数据集是否适合当前评测任务。

**Why this priority**: 数据是评测的入口；没有数据集上下文，Agent 无法给出有意义的建议。

**Independent Test**: 使用已存在的租户与数据集，依次调用 `list_projects`、`search_datasets`、`get_dataset_schema`、`preview_samples`，能拿到结构化结果。

**Acceptance Scenarios**:

1. **Given** 租户下有 3 个项目，**When** 调用 `list_projects`，**Then** 只返回该租户的项目，按更新时间倒序。
2. **Given** 数据集名称包含关键字，**When** 调用 `search_datasets`，**Then** 返回匹配项与 `latest_version`、`sample_count`，并支持游标分页。
3. **Given** 数据集有多个版本，**When** 调用 `get_dataset_schema` 不传版本，**Then** 返回最新版本的字段定义与 `content_hash`。
4. **Given** 请求预览 50 条样本，**When** 调用 `preview_samples`，**Then** 最多返回 20 条，且敏感字段已脱敏。
5. **Given** 样本内容中包含类似「忽略之前指令」的文本，**When** 返回给客户端，**Then** 仅作为数据内容返回，不触发任何服务端动作。

---

### User Story 3 - 理解评测结果 (Priority: P1)

程序员问 Agent「上次评测为什么失败」「这次改动比基线好还是差」，Agent 通过 Run 查询与对比工具给出结论，并能下钻到失败样本。

**Why this priority**: 这是只读场景下最高频、价值最大的能力。

**Independent Test**: 使用两次已完成的 Run，调用 `get_run`、`get_run_items`、`compare_runs`，能拿到状态、指标差异与失败样本列表。

**Acceptance Scenarios**:

1. **Given** 一个运行中的 Run，**When** 调用 `get_run`，**Then** 返回 `status=running`、`progress`、已完成/失败计数与当前成本。
2. **Given** 一个已完成的 Run，**When** 调用 `get_run_items` 且 `status=failed`，**Then** 返回失败样本分页列表，默认不返回完整输入/输出。
3. **Given** 调用方拥有 `mcp:eval:read_content` scope 且显式请求 `include_io=true`，**When** 调用 `get_run_items`，**Then** 返回脱敏后的输入/输出摘录。
4. **Given** 两次 Run 使用同一 Suite 的不同数据集版本，**When** 调用 `compare_runs`，**Then** 返回逐指标差值、劣化项与改善项，并标注是否达到统计显著。
5. **Given** Run 属于其他租户，**When** 调用 `get_run`，**Then** 返回 404（不暴露存在性）。

---

### User Story 4 - Badcase 与门禁查询 (Priority: P2)

程序员让 Agent 检索相似 Badcase，或查询某次 Run 是否通过门禁，以便决定是否需要修 Prompt。

**Why this priority**: 依赖前三个故事的数据；价值高但可稍后交付。

**Independent Test**: 使用已有 Badcase 与 Gate 记录，调用 `search_badcases`、`check_gate`，返回结构化结果与证据链接。

**Acceptance Scenarios**:

1. **Given** Badcase 库中存在相似问题，**When** 调用 `search_badcases`，**Then** 返回按相似度或时间排序的结果，并带 `dataset_id` / `sample_id`。
2. **Given** 一次已完成 Run 与一个 Suite，**When** 调用 `check_gate`，**Then** 返回 `passed`、逐条规则结果与证据引用。
3. **Given** 语义检索服务不可用，**When** 调用 `search_badcases`，**Then** 降级为关键词检索并标注 `degraded=true`，不返回 5xx。

**Dependency**: `search_badcases` 依赖 `SRC-05`（语义检索/关键词降级），`check_gate` 依赖 `GAT-04`（门禁结果）。依赖未就绪时工具保持注册但返回 `UPSTREAM_UNAVAILABLE`；**不得在 MCP 内实现检索、降级或门禁判定逻辑**。

---

### Edge Cases

- API Key 过期、吊销、租户被禁用。
- Key 的 scope 与工具要求不匹配。
- 游标被篡改、过期、跨租户复用。
- 结果超过 64KB。
- 数据库主库不可用、只读副本延迟过大。
- 限流/队列依赖不可用时的降级策略（建议：本地令牌桶兜底，宁严勿松）。
- 客户端并发发起 20 个请求。
- 数据集中包含 PII、密钥样式字符串、Prompt 注入文本。
- Run 正在运行、已取消、部分失败（`succeeded_with_errors`）。
- 协议版本高于服务端支持范围。
- 审计写入失败（不得阻塞主请求，但必须告警）。

---

## Requirements *(mandatory)*

### Functional Requirements

**协议与传输**

- **FR-001**: MCP 协议 MUST 仅通过 Streamable HTTP 暴露在单一端点 `/mcp`，不提供 stdio；`/healthz`、`/readyz`、`/metrics` 仅作为运维端点，不承载 MCP 协议。
- **FR-002**: 服务 MUST 使用 JSON-RPC 2.0，并支持 `initialize`、`tools/list`、`tools/call`、`resources/list`、`resources/read`。
- **FR-003**: 服务 MUST 协商 `MCP-Protocol-Version`；不支持的版本 MUST 返回明确错误。
- **FR-004**: 服务 MUST 以无状态模式运行，不依赖 `Mcp-Session-Id` 做请求路由。

**认证与授权**

- **FR-005**: 服务 MUST 接受 `Authorization: Bearer <api_key>`。
- **FR-006**: API Key MUST 绑定 `tenant_id`、一组 scope、过期时间与吊销状态。
- **FR-007**: 服务 MUST 对每个工具校验所需 scope；不足时返回 403。
- **FR-008**: 服务 MUST 在 Service 与 Repository 两层强制租户过滤（Repository 基类自动注入 `tenant_id`），禁止仅依赖工具层过滤。
- **FR-009**: 服务 MUST 提供 `AuthProvider` 抽象，业务代码不得直接读取认证头。
- **FR-010**: 服务 MUST 预留 OAuth 2.1 Resource Server 接口（配置开关、metadata 端点、`aud/iss/exp/scope` 校验位），但首期不启用；启用后 MUST 校验 `aud` 等于本服务 canonical URI，并拒绝 token passthrough。

**工具面（只读）**

- **FR-011**: 服务 MUST 仅注册以下 10 个只读工具：`list_projects`、`search_datasets`、`get_dataset_schema`、`preview_samples`、`list_evaluators`、`get_run`、`get_run_items`、`compare_runs`、`search_badcases`、`check_gate`。
  - 其中 `search_badcases` / `check_gate` 为条件可用工具：依赖未就绪时返回 `UPSTREAM_UNAVAILABLE`，但不得从工具清单移除（保持 10 工具契约稳定）。
- **FR-012**: 所有工具 MUST 标注 `readOnlyHint=true`、`destructiveHint=false`、`idempotentHint=true`、`openWorldHint=false`。
- **FR-013**: 服务 MUST NOT 注册任何写工具；CI 必须通过工具名 allowlist 快照测试。
- **FR-014**: 服务 MUST NOT 暴露任意 SQL、任意 URL 抓取、代码执行、删除、全量导出能力。
- **FR-015**: 每个工具 MUST 提供稳定的 `inputSchema` 与 `outputSchema`，并带版本号。

**分页、限额与错误**

- **FR-016**: 所有列表型工具 MUST 使用不透明签名游标分页，禁止 offset 分页。
- **FR-017**: 单次工具结果 MUST ≤ 64KB；超出时 MUST 截断并返回 `next_cursor` 或 `RESULT_TOO_LARGE`。
- **FR-018**: `preview_samples` MUST 单次 ≤ 20 条，单条 payload ≤ 4KB，且 MUST 脱敏。
- **FR-019**: `get_run_items` MUST 单页 ≤ 100 条；默认不返回完整输入/输出。
- **FR-020**: 服务 MUST 对每个 API Key 与租户分别限流，超限返回 429 + `Retry-After`。
- **FR-021**: 错误 MUST 包含稳定错误码、可读消息与 `trace_id`，不得返回堆栈或内部路径。

**审计与可观测**

- **FR-022**: 每次工具调用 MUST 记录 `tenant_id`、`api_key_id`、工具名与版本、状态、耗时、结果字节数、`trace_id`。
- **FR-023**: 审计记录 MUST 为 append-only，且不得包含完整参数、PII 或密钥。
- **FR-024**: 服务 MUST 输出 OpenTelemetry trace 与 Prometheus 指标。
- **FR-025**: 服务 MUST 提供 `/healthz`（liveness）与 `/readyz`（依赖检查）。

**数据与安全**

- **FR-026**: MCP 使用的数据库账号 MUST 仅有业务表 `SELECT` 与审计表 `INSERT` 权限。
- **FR-027**: 服务 MUST 对样本内容视为不可信输入，结构化包裹并标注来源。
- **FR-028**: 服务 MUST NOT 在日志中记录完整 API Key、完整 Prompt、完整样本内容。
- **FR-029**: 服务 MUST 支持优雅停机：停止接收新请求，等待 in-flight 完成。
- **FR-030**: 服务 MUST 在 API Key 吊销后 ≤ 60 秒内生效（缓存 TTL 上限）。

### Key Entities

- **ApiKey**: 平台签发的只读凭据；含 `key_id`、密钥哈希、`tenant_id`、scopes、过期/吊销状态。
- **Principal**: 认证后的调用主体；含 `tenant_id`、`subject`、`scopes`、`auth_method`、`expires_at`。
- **Tool**: 只读能力单元；含名称、版本、输入/输出 Schema、所需 scope、annotations。
- **Cursor**: 不透明分页令牌；含查询指纹、最后键、过期时间、HMAC 签名。
- **ToolCall**: 一次工具调用审计；append-only。
- **Dataset / DatasetVersion / Sample**: 复用平台既有实体，MCP 只读。
- **Run / RunItem / Metric**: 复用平台既有实体，MCP 只读。
- **Badcase / Gate / GateResult**: 复用平台既有实体，MCP 只读。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 新用户在 10 分钟内完成「获取 Key → 配置 IDE → 连接成功 → 看到工具列表」。
- **SC-002**: `tools/list` 返回的工具集合与 allowlist 快照 100% 一致，且不含任何写动词。
- **SC-003**: 元数据类工具 P95 < 300ms；`preview_samples` / `get_run_items` P95 < 1s（不含网络）。
- **SC-004**: 跨租户访问测试 100% 返回 403/404，且响应时间与「资源不存在」无显著差异。
- **SC-005**: 使用受限数据库账号执行 `INSERT/UPDATE/DELETE` 100% 被拒绝。
- **SC-006**: 单 Key 限流生效：超过阈值后 100% 返回 429。
- **SC-007**: 超大结果 100% 被截断或返回 `RESULT_TOO_LARGE`，无一次超过 64KB。
- **SC-008**: 审计覆盖率 100%：每次工具调用都有对应记录，且可在 1 分钟内按 `trace_id` 检索。
- **SC-009**: OAuth 预留验证：切换 `MCP_AUTH_MODE=oauth` 并注入 fake provider 后，工具代码零改动即可完成鉴权。
- **SC-010**: 单实例在 50 QPS 下连续 30 分钟无 5xx，内存增长 < 10%。

---

## Assumptions

- 平台可能已有 API Key 签发能力；若无，由身份模块实现，MCP 复用同一 API Key 校验能力，不重复实现。
- 首期部署在内网或 VPN 后，TLS 终止于 Ingress。
- 平台数据库可为 MCP 创建独立受限账号（业务表只读 + 审计表 INSERT），并支持只读副本。
- 读取评测明细走只读副本；主库只承担元数据查询。
- MCP 协议基线为 `2025-06-18` 修订版。
- 首期不接入企业 IdP；OAuth 仅预留接口。
- 样本脱敏规则复用平台既有 PII 规则。

---

## Out of Scope

- stdio 传输
- 任何写操作（启动评测、创建 Badcase、取消 Run、修改数据集）
- Prompts 与 Sampling
- OAuth 2.1 的完整实现（仅预留接口）
- 多客户端自助注册与工具市场
- 可视化功能测试相关工具

---

## Review & Acceptance Checklist

- [ ] 工具清单与 ADR-005 一致，且全部为只读
- [ ] 认证、scope、租户隔离、限流、审计均有验收用例
- [ ] 游标签名与跨租户复用有测试
- [ ] 结果大小上限与脱敏有测试
- [ ] 数据库受限账号权限已用 SQL 验证
- [ ] OAuth 切换路径有 fake provider 测试
- [ ] 可观测指标与告警项已定义
- [ ] 文档包含 IDE 配置示例与故障排查
