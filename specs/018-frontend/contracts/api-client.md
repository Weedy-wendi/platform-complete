# 前端 API 客户端契约

**范围**: `018-frontend`

## 生成

```bash
pnpm --dir frontend run gen:api
# openapi-typescript ../../specs/017-rest-api/contracts/openapi.yaml -o src/types/api.ts
```

- `src/types/api.ts` **只由生成器写入**；手写修改 CI 失败。
- 请求/响应类型必须来自生成类型；禁止 `any` 绕过。

## 客户端

```ts
// src/api/client.ts
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T>
```

- 自动加 `Authorization: Bearer <key>`。
- 统一解析 `Error` envelope；`401` 清理会话；`403/404` 统一提示。
- 所有错误展示 `trace_id`（便于排查）。
- 支持 `Idempotency-Key`（创建类请求）。
- 分页使用 `cursor` + `limit`，不使用 offset。

## 状态

- Pinia `authStore`：principal、tenant、scopes（仅内存/sessionStorage）。
- Pinia `tenantStore`：当前租户与可见项目。
- 请求层不缓存敏感数据；登出清理。

## 检查

- CI：`pnpm gen:api && git diff --exit-code src/types/api.ts`
- CI：`vue-tsc --noEmit`、ESLint、Vitest、Playwright。
