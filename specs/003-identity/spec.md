# Feature Specification: identity（M01）

**Feature**: `003-identity` | **Phase**: P0a | **Status**: Implemented

**任务**: IDN-01 ~ IDN-13（`docs/planning/tasks/00-foundation.md`）

---

## 1. 模块职责

租户、用户、角色、权限、API Key、认证适配。所有模块的租户上下文来源。

## 2. 为什么做

MCP 已有 API Key 子集；平台需要完整的租户/用户/RBAC，才能支撑 REST、前端、审计与多租户隔离。

## 3. 功能需求

- **FR-001** 租户/用户/角色模型：租户 slug 唯一；用户可多角色；软删除；审计字段。
- **FR-002** RBAC：角色/权限可组合；默认拒绝；越权 `ForbiddenError`。
- **FR-003** API Key：签发/校验/吊销/轮换；只存 `HMAC-SHA256(pepper, secret)`；明文只显示一次。
- **FR-004** 吊销 ≤60s 生效；缓存 TTL ≤60s；未知 scope 拒绝签发。
- **FR-005** 认证适配：API Key 首期；JWT/OIDC 预留；401/403 正确。
- **FR-006** 租户隔离测试：读/写/导出/跨租户 Key 100% 拒绝。
- **FR-007** 身份审计：登录、签发、吊销、角色变更写审计。

## 4. 验收场景

1. **Given** 平台管理员创建租户与租户管理员，**When** 签发 API Key，**Then** 明文只出现一次，数据库只有 HMAC。
2. **Given** Key 被吊销，**When** 60 秒内再次使用，**Then** 401。
3. **Given** 租户 A 的 Key，**When** 访问租户 B 数据，**Then** 0 行/404。
4. **Given** 用户缺少角色，**When** 调用管理接口，**Then** 403。
5. **Given** 登录/签发/吊销，**When** 操作完成，**Then** 审计有 actor/target/trace_id。

## 5. 关键实体

`tenant`、`user`、`role`、`permission`、`user_role`、`api_key`。

## 6. 边界与异常

- Key 过期/吊销/未知 key_id、scope 不足、租户禁用、角色冲突、JWT 预留、跨租户。

## 7. 不在范围

- 企业 IdP 完整 OAuth 流程（仅预留）。
- 业务权限（由各模块 scope 定义）。

## 8. 依赖

`002-core`（TenantContext/Repository/错误模型）、`004-audit`（审计钩子）。
