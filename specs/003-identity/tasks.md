# Tasks: identity（M01）

**Source of truth**: `docs/planning/task-index.md`；明细见 `docs/planning/tasks/00-foundation.md`。

- [X] IDN-01 租户/用户/角色模型 + 迁移
- [X] IDN-02 RBAC 策略引擎
- [X] IDN-03 API Key 生命周期（HMAC、吊销 ≤60s、scope 白名单）
- [X] IDN-04 认证适配器（API Key；JWT 预留）
- [X] IDN-05 租户隔离测试
- [X] IDN-06 身份审计钩子

## 交付检查

- [X] Key 明文不落库/日志
- [X] 吊销 ≤60s 生效
- [X] 跨租户 100% 拒绝
- [X] 登录/签发/吊销有审计

---

## Phase 2: Convergence

- [X] IDN-07 [HIGH] 限制 `ApiKeyService.cache_ttl_seconds` 必须满足 `0 < ttl <= 60`（并在 `IdentityService`/配置入口保持同一约束），补 0/60/61 边界测试，确保吊销 ≤60s 生效 per FR-004 / plan 风险「缓存导致吊销延迟」 (partial)
- [X] IDN-08 [MEDIUM] 修复软删除与唯一约束冲突：`create_user` / `create_tenant` / `create_role` 在复用已软删除的 email / slug / role name 时返回明确 `InvalidArgumentError`（或调整唯一键/删除策略），补回归测试 per FR-001 (partial)

---

## Phase 3: Convergence

- [X] IDN-09 [HIGH] 在认证与租户级用例中强制校验租户状态：`Tenant.status == "active"` 且 `deleted_at IS NULL`；禁用/删除租户的 API Key 必须 401、管理操作必须拒绝；补禁用/删除租户回归测试 per FR-006 / §6 边界「租户禁用」 (partial)
- [X] IDN-10 [LOW] 对齐 `Principal.auth_method` 与 identity 契约：支持 `Literal["api_key", "jwt", "oauth"]`（保留现有 OAuth 兼容）并补契约类型测试，使 JWT 预留适配器可返回兼容 Principal per `contracts/interfaces.md` / plan「JWT/OIDC 预留」 (partial)

---

## Phase 4: Convergence

- [X] IDN-11 [HIGH] 将租户状态检查接入 MCP API Key 认证构建路径（`app/mcp/server.py::_build_api_key_service`），对缺失 tenant 行的 legacy key 保持兼容（`allow_missing`），补禁用租户 MCP 认证测试 per FR-006 / IDN-09 (partial)
- [X] IDN-12 [LOW] 让 `JwtAuthenticator` 支持注入 verifier，配置后可返回 `Principal(auth_method="jwt")`，默认仍拒绝；补适配器测试 per IDN-10 / `contracts/interfaces.md` (partial)
- [X] IDN-13 [LOW] 补软删除租户回归测试：设置 `tenant.deleted_at` 后其 API Key 返回 401、管理操作返回 `NotFoundError` per IDN-09「禁用/删除租户回归测试」 (partial)
