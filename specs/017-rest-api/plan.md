# Implementation Plan: REST / OpenAPI 接入层（P0d）

**Feature**: `017-rest-api` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- **框架**: FastAPI（ASGI）+ Pydantic v2；`/v1` 路由；OpenAPI 3.1 自动导出。
- **认证**: API Key Bearer（复用 identity）；JWT/OIDC 预留；`TenantContext` 依赖注入。
- **授权**: RBAC + scope；默认拒绝。
- **长任务**: 创建 Run/导入返回 `202 Accepted + run_id`；查询/SSE 获取进度。
- **幂等**: `Idempotency-Key` + `idempotency_key` 唯一索引。
- **分页**: 签名游标（复用 MCP cursor 实现思路）；禁止 offset。
- **错误**: 统一 `Error` envelope；`trace_id` 必含。
- **契约**: `contracts/openapi.yaml` 为源；CI 快照；前端类型生成。

## 2. 目录结构

```text
backend/app/api/
├── main.py            # FastAPI app, /v1 router, error handlers
├── deps.py            # auth, tenant, rbac, pagination
├── schemas/           # Pydantic request/response
└── routes/
    ├── health.py
    ├── projects.py
    ├── datasets.py
    ├── runs.py
    ├── evaluators.py
    ├── gates.py
    ├── reports.py
    ├── badcases.py
    └── admin.py

specs/017-rest-api/contracts/openapi.yaml
specs/017-rest-api/contracts/errors.md
```

## 3. 路由与状态码

| 路由 | 方法 | 状态码 | 说明 |
|---|---|---|---|
| `/v1/projects` | GET/POST | 200/201 | 列表/创建 |
| `/v1/datasets` | GET/POST | 200/201 | 列表/创建 |
| `/v1/datasets/{id}/versions` | POST | 201 | 发布会不可变版本 |
| `/v1/datasets/{id}/versions/{v}/samples` | GET | 200 | 游标分页 |
| `/v1/runs` | POST/GET | 202/200 | 创建（异步）/列表 |
| `/v1/runs/{id}` | GET | 200 | 状态/进度/汇总 |
| `/v1/runs/{id}/items` | GET | 200 | 明细分页 |
| `/v1/runs/{id}/cancel` | POST | 202 | 取消 |
| `/v1/runs/{id}/compare` | GET | 200 | 与基线对比 |
| `/v1/evaluators` | GET/POST | 200/201 | 评分器 |
| `/v1/gates/{suite}/{run}` | GET | 200 | 门禁结果 |
| `/v1/reports/{run}` | GET | 200 | 报告/导出 |
| `/v1/badcases/search` | POST | 200 | 语义检索（可降级） |
| `/v1/functional/runs` | POST/GET | 202/200 | 功能测试 Run（P2） |
| `/v1/admin/*` | * | * | 租户/用户/Key/Provider |

## 4. 认证与租户

```text
Authorization: Bearer <api_key>
  → ApiKeyVerifier → Principal
  → TenantContext(tenant_id, subject_id, scopes, trace_id)
  → RBAC/scope 检查
  → Service（强制 tenant_id）
```

- 401：缺失/无效/过期/吊销。
- 403：scope/角色不足。
- 404：跨租户资源，避免泄露存在性。

## 5. 错误与分页

- `Error = {code, message, trace_id, details?}`。
- `Page = {items, next_cursor?}`。
- 游标签名、TTL 15 分钟；跨租户/查询指纹不匹配 → `INVALID_CURSOR`。

## 6. 阶段

1. API-01 框架/OpenAPI/错误/健康。
2. API-02 认证/租户/RBAC/限流。
3. API-03 项目/数据源/数据集/样本。
4. API-04 评分器/Suite/Target。
5. API-05 Run 创建/查询/明细/对比/取消。
6. API-06 Gate/报告/导出。
7. API-07 Badcase 检索。
8. API-08 管理面。
9. API-09 OpenAPI 快照 + 前端类型生成。
10. API-10 契约/安全/性能测试。

## 7. 测试策略

- 契约：OpenAPI 快照；请求/响应 Schema；前端类型 diff。
- 集成：CRUD、202 + 查询、SSE、幂等、分页。
- 安全：401/403/404、跨租户、scope、限流。
- 性能：元数据 P95 <300ms；列表分页稳定。

## 8. 风险

| 风险 | 缓解 |
|---|---|
| OpenAPI 与实现漂移 | 自动导出 + 快照 + CI |
| 前端手写类型 | 生成 + diff 阻断 |
| 长任务阻塞 API | 202 + Worker + 查询/SSE |
| 跨租户泄露 | Service/Repository 双层过滤 + 安全测试 |
| 破坏性 API 变更 | `/v1` 兼容策略 + 新 major |

## 9. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | 响应含 `manifest_hash`/版本 |
| II 五原语 | 复用 Asset/Run/Evidence/Gate |
| III API/CLI First | OpenAPI 3.1 为唯一契约 |
| IV Boring Tech | FastAPI/Pydantic/生成类型 |
| V 控制/执行分离 | 写操作 202；长任务在 Worker |
| VI 证据驱动 | 契约/安全/性能测试 |
| VII 模块化单体 | `app/api` 仅接入层，不写业务逻辑 |
