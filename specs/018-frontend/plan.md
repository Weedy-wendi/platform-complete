# Implementation Plan: Web 前端（P3）

**Feature**: `018-frontend` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- **框架**: Vue 3 + TypeScript + Vite
- **UI**: Element Plus
- **状态**: Pinia（auth、tenant、UI 状态）
- **路由**: Vue Router（懒加载 + 守卫）
- **API**: `openapi-typescript` 生成类型 + `openapi-fetch` 或轻量 client
- **图表**: ECharts（按需引入）
- **测试**: Vitest + Vue Test Utils；Playwright E2E
- **国际化**: vue-i18n（zh-CN / en-US）
- **质量**: ESLint + Prettier + `vue-tsc`；类型检查纳入 CI

## 2. 目录结构

```text
frontend/
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── router/
│   ├── stores/          # auth, tenant, ui
│   ├── api/             # generated client + error handling
│   ├── types/api.ts     # 生成，不手写
│   ├── views/           # projects, datasets, runs, gates, reports, badcases, functional, admin
│   ├── components/      # DataTable, StatusTag, MetricChart, EvidenceViewer
│   ├── locales/
│   └── styles/
├── tests/               # Vitest
├── e2e/                 # Playwright
└── package.json
```

## 3. 认证与租户

```text
登录/输入 API Key → 校验 → 保存到 memory/sessionStorage
→ 每个请求 Authorization: Bearer <key>
→ Pinia 保存 tenant/principal
→ 路由守卫按角色/scope 控制
```

- 不把 Key 写入 URL、localStorage、日志。
- 401 → 清理会话并跳转登录；403 → 提示权限不足；404 → 统一“未找到”。

## 4. 页面阶段

1. FE-01 壳/登录/租户/布局/错误处理。
2. FE-02 项目/数据集/Schema/样本。
3. FE-03 Run 列表/详情/明细/对比。
4. FE-04 评分器/Suite/Target。
5. FE-05 门禁。
6. FE-06 报告/导出/分享。
7. FE-07 Badcase 检索。
8. FE-08 功能测试/视觉差异/证据。
9. FE-09 管理面。
10. FE-10 生成 API 客户端/类型校验/CI。

## 5. 测试策略

- 单元/组件：表单校验、状态标签、错误处理、权限隐藏。
- E2E：登录、项目/数据集、Run 创建/查询/对比、Gate、报告、Badcase。
- 契约：OpenAPI 生成类型 diff。
- 可访问性：axe/键盘走查。
- 性能：Lighthouse LCP <2.5s。

## 6. 风险

| 风险 | 缓解 |
|---|---|
| 手写 API 类型漂移 | 生成 + CI diff |
| 大列表卡顿 | 分页/虚拟滚动 |
| Key 泄露 | sessionStorage/内存；CSP；不日志 |
| 权限 UI 与后端不一致 | 以 API 403 为准；UI 仅辅助 |
| 前端依赖漂移 | lockfile + 镜像 digest |

## 7. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | 展示 manifest/版本 |
| II 五原语 | 页面围绕 Asset/Run/Evidence/Gate |
| III API/CLI First | 只通过 `/v1`；类型生成 |
| IV Boring Tech | Vue/Element Plus/Vite |
| V 控制/执行分离 | 长任务 202 + 轮询/SSE |
| VI 证据驱动 | E2E/契约/性能测试 |
| VII 模块化单体 | 前端独立应用，不绕过 API |
