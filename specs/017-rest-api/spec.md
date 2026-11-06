# Feature Specification: REST / OpenAPI 接入层（P0d）

**Feature**: `017-rest-api` | **Phase**: P0d | **Status**: Implemented

**覆盖模块**: `api`（新增接入层；不新增业务实体）

**任务前缀**: API-01 ~ API-10

---

## 1. 为什么做

宪法要求 **API / CLI First**：任何 UI 能力都必须先通过 API 暴露。当前仓库只有 MCP 只读适配器，没有面向浏览器/外部系统的 HTTP API。前端（`018-frontend`）、CLI、第三方集成都需要这一层。

MCP 是第 5 接入层，只读；REST API 是平台的主接入层，支持读写（受 RBAC/租户约束）。

## 2. 角色

- 租户用户：通过 Web/CLI 管理项目、数据集、Run、报告。
- 服务账号：通过 API Key 调用，按 scope 授权。
- 前端：只通过 `/v1` 与生成的类型访问，不手写 API 镜像类型。
- 运维：健康检查、指标、审计。

## 3. 功能需求

- **FR-001** 提供 `/v1` JSON HTTP API；**OpenAPI 3.1 是唯一契约**；前端类型由 `openapi-typescript` 生成。
- **FR-002** 认证：`Authorization: Bearer <api_key>`；JWT/OIDC 预留；认证后注入 `TenantContext`。
- **FR-003** 授权：RBAC + API Key scope；默认拒绝；越权返回 403/404，不泄露存在性。
- **FR-004** 分页：不透明签名游标；禁止 offset；列表按稳定键排序。
- **FR-005** 错误模型：`code` / `message` / `trace_id` / `details`；不返回堆栈/内部路径。
- **FR-006** 项目/数据源/数据集/样本：CRUD 与查询；数据集版本发布不可变；样本批量写入。
- **FR-007** Run：创建返回 `202 + run_id`；查询状态/进度/明细/对比；取消；不阻塞等待长任务。
- **FR-008** 评分器/Suite/Target：查询与配置；版本化。
- **FR-009** Gate/报告：查询门禁结果；生成/导出 Run 报告与对比报告。
- **FR-010** Badcase 检索：委托 `SemanticSearch`；返回 `degraded`；不实现检索逻辑。
- **FR-011** 管理面：租户、用户、角色、API Key、Provider 配置（受平台管理员 scope）。
- **FR-012** 幂等：创建类接口支持 `Idempotency-Key`；重复请求返回同一资源。
- **FR-013** 运维端点：`/healthz`、`/readyz`、`/metrics`（不承载业务 API）。
- **FR-014** 契约快照：OpenAPI diff 进入 CI；手写 API 类型导致 CI 失败。
- **FR-015** 审计：所有写操作记录 actor/action/resource/trace_id。

## 4. 非功能需求

- **NFR-001** OpenAPI 3.1；`/v1` 内向后兼容；破坏性变更走新 major。
- **NFR-002** 元数据 P95 <300ms；列表分页稳定；大结果流式导出。
- **NFR-003** 所有外部依赖调用有超时；长任务返回 202 + 查询/SSE。
- **NFR-004** 租户隔离在 Service 与 Repository 两层强制。
- **NFR-005** 请求体上限、限流、TLS 终止于 Ingress。

## 5. 用户故事与验收

### US1 认证与租户

1. **Given** 有效 API Key，**When** 调用 `/v1/projects`，**Then** 只返回该租户项目。
2. **Given** 缺失/过期/吊销 Key，**When** 调用，**Then** 401 + `WWW-Authenticate`。
3. **Given** scope 不足，**When** 写操作，**Then** 403。

### US2 数据集

1. **Given** 一个项目，**When** 创建数据集并发布版本，**Then** 返回版本与 `content_hash`。
2. **Given** 已发布版本，**When** 修改，**Then** 409/拒绝。
3. **Given** 大量样本，**When** 批量写入，**Then** 202/完成，行数一致。

### US3 Run

1. **Given** 一个 Suite，**When** 创建 Run，**Then** 返回 `202 + run_id`，不阻塞。
2. **Given** 一个 Run，**When** 查询 items，**Then** 分页、可按状态/指标过滤。
3. **Given** 两个 Run，**When** 对比，**Then** 返回差值/劣化/改善/显著性。
4. **Given** 运行中的 Run，**When** 取消，**Then** 状态变为 `cancelled`，已完成 item 保留。

### US4 报告与 Gate

1. **Given** 一个 Run，**When** 生成报告，**Then** 返回 Markdown/JSON；可导出 CSV/JUnit。
2. **Given** 一个 Suite + Run，**When** 查询 Gate，**Then** 返回 `passed` 与逐规则证据。

## 6. 不在范围

- MCP 协议（`001-mcp-server`）。
- UI 组件与页面（`018-frontend`）。
- 评测执行逻辑（`004-evaluation-core`）。
- 语义检索实现（`006-ingestion-search`）。

## 7. 依赖

P0a（core/identity/audit）、P0b（catalog/jobs/model_gateway/evaluation）、P0c（gate/reporting）；P1（search）用于 Badcase 检索。前端依赖本规格。
