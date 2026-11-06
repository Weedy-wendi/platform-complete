# Implementation Plan: identity（M01）

**Feature**: `003-identity` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- SQLAlchemy 模型 + Alembic 迁移；密码/令牌使用高熵 + HMAC（API Key）。
- RBAC：角色→权限矩阵；默认拒绝；与 API Key scope 并行。
- 认证：FastAPI 依赖注入 `Principal`；API Key 解析 → HMAC → 缓存 → Principal。
- JWT/OIDC：预留 `AuthProvider`，校验 `iss/aud/exp/scope`。

## 2. 数据模型

`tenant`、`user`、`role`、`permission`、`user_role`、`api_key`。`api_key` 复用 MCP 已有表；新增 `tenant/user/role/permission/user_role`。

## 3. 公开接口

`IdentityService`、`ApiKeyVerifier`、`Principal`；方法第一个参数为 `TenantContext`。

## 4. 测试策略

- 单元：HMAC、格式、scope、RBAC 矩阵。
- 集成：签发→校验→吊销；角色分配；登录审计。
- 安全：跨租户读/写/导出、明文泄露、吊销时效。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| Key 泄露 | 只存 HMAC、最小 scope、可吊销 |
| 缓存导致吊销延迟 | TTL ≤60s |
| RBAC 绕过 | 默认拒绝 + 安全测试 |
| 租户上下文伪造 | 认证层注入，业务不读 header |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | Key/角色版本与审计 |
| II 五原语 | 身份作为横切能力 |
| III API/CLI First | 认证供 REST/MCP 共用 |
| IV Boring Tech | HMAC/标准 JWT |
| V 控制/执行分离 | 认证不执行长任务 |
| VI 证据驱动 | 隔离/泄露/吊销测试 |
| VII 模块化单体 | `public.py` 边界 |
