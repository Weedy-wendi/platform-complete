# Feature Specification: Web 前端（P3）

**Feature**: `018-frontend` | **Phase**: P3 | **Status**: Implemented

**技术栈**: Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router

**任务前缀**: FE-01 ~ FE-10

---

## 1. 为什么做

平台的数据、评测、门禁、报告与功能测试需要面向人的界面。前端只通过 `017-rest-api` 的 `/v1` 访问，不直接调用 MCP，也不手写 API 类型。

## 2. 角色

- 租户用户：浏览项目/数据集、查看 Run、对比结果、查看门禁/报告。
- 评测工程师：配置评分器/Suite/Target，发起 Run。
- QA：查看功能测试结果、视觉差异、证据。
- 平台管理员：管理租户/用户/Key/Provider。

## 3. 功能需求

- **FE-001** 应用壳：登录、租户切换、导航、全局错误/加载状态；路由守卫。
- **FE-002** 项目与数据集：项目列表/详情；数据集检索；版本列表；Schema 查看；样本预览（脱敏）。
- **FE-003** Run：列表/详情；状态/进度/指标/成本；明细分页；失败样本下钻；与基线对比。
- **FE-004** 评分器/Suite/Target：列表、详情、创建/编辑（受权限控制）；版本展示。
- **FE-005** 门禁：Gate 结果、逐规则 expected/actual/evidence；失败规则高亮。
- **FE-006** 报告：Run 报告、对比报告；Markdown 渲染；导出 JSON/CSV/JUnit；分享链接。
- **FE-007** Badcase：语义检索、标签/数据集过滤、`degraded` 提示、证据下钻。
- **FE-008** 功能测试：用例/套件、Run 详情、步骤结果、截图/录屏、视觉差异。
- **FE-009** 管理面：租户、用户、角色、API Key（签发只显示一次）、Provider 配置。
- **FE-010** API 客户端：由 OpenAPI 生成；禁止手写 `types/api.ts`；统一错误/trace_id 处理。
- **FE-011** 国际化：中文/英文；日期/数字/时区（UTC 展示，本地化）。
- **FE-012** 可访问性与响应式：键盘操作、焦点管理、对比度；桌面优先，窄屏可用。
- **FE-013** 认证：API Key 输入后保存在内存/sessionStorage；不写入 URL/日志；JWT/OIDC 预留。
- **FE-014** 权限：按角色/scope 隐藏或禁用写操作；403/404 统一提示。
- **FE-015** 性能预算：首屏 LCP <2.5s；路由懒加载；大列表虚拟滚动/分页。
- **FE-016** 可观测：前端错误上报含 `trace_id`；不采集敏感内容。

## 4. 验收场景

1. **Given** 有效凭据，**When** 打开项目页，**Then** 只看到当前租户数据。
2. **Given** 一个运行中的 Run，**When** 打开详情，**Then** 进度/指标/成本实时更新（轮询或 SSE）。
3. **Given** 两个 Run，**When** 打开对比，**Then** 显示逐指标差值、劣化/改善、显著性。
4. **Given** 一个 Gate，**When** 查看规则，**Then** 显示 expected/actual/evidence，失败项高亮。
5. **Given** 语义检索降级，**When** 搜索 Badcase，**Then** 显示 `degraded` 提示，结果仍可用。
6. **Given** 非管理员角色，**When** 访问管理面，**Then** 隐藏入口或返回 403。
7. **Given** OpenAPI 变更，**When** 前端未重新生成类型，**Then** CI 失败。

## 5. 页面/路由（摘要）

`/login`、`/`、`/projects`、`/projects/:id`、`/datasets`、`/datasets/:id`、`/runs`、`/runs/:id`、`/runs/:id/compare`、`/evaluators`、`/suites`、`/gates`、`/reports`、`/badcases`、`/functional`、`/admin`、`/settings`。

## 6. 非功能需求

- **NFR-001** 仅通过 `/v1` 访问；不直连 MCP/MySQL/Redis。
- **NFR-002** 类型安全：`openapi-typescript` 生成 + `vue-tsc` 严格模式。
- **NFR-003** 测试：Vitest 组件/单元；Playwright E2E 覆盖关键路径。
- **NFR-004** 构建产物锁定；依赖 lockfile；镜像 digest 固定。
- **NFR-005** 安全：不存明文 Key 到 localStorage；XSS/CSRF 防护；CSP。

## 7. 不在范围

- 移动端原生 App、SSR/SEO。
- 可视化大屏/复杂图表库（首期用 Element Plus + ECharts 可选）。
- MCP 协议 UI（MCP 由 IDE 使用）。

## 8. 依赖

`017-rest-api`（必须先生效）；`007-catalog`、`010-evaluation`、`011-gate`、`012-reporting`、`014-search`、`015-functional` 提供业务数据。
