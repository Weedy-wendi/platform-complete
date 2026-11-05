# 前端路由契约

**范围**: `018-frontend`

| 路由 | 页面 | 权限 | 主要 API |
|---|---|---|---|
| `/login` | 登录/输入 API Key | 公开 | — |
| `/` | 工作台/概览 | 登录 | `/v1/projects`、`/v1/runs` |
| `/projects` | 项目列表 | `projects:read` | `/v1/projects` |
| `/projects/:id` | 项目详情 | `projects:read` | `/v1/projects/{id}` |
| `/datasets` | 数据集检索 | `datasets:read` | `/v1/datasets` |
| `/datasets/:id` | 数据集详情/版本/Schema/样本 | `datasets:read` | `/v1/datasets/{id}/versions/...` |
| `/runs` | Run 列表 | `runs:read` | `/v1/runs` |
| `/runs/:id` | Run 详情/明细 | `runs:read` | `/v1/runs/{id}`、`/items` |
| `/runs/:id/compare` | 对比 | `runs:read` | `/v1/runs/{id}/compare` |
| `/evaluators` | 评分器 | `evaluators:read` | `/v1/evaluators` |
| `/suites` | Suite/Target | `evaluators:read` | `/v1/evaluators` |
| `/gates` | 门禁结果 | `gates:read` | `/v1/gates/...` |
| `/reports` | 报告/导出 | `reports:read` | `/v1/reports/...` |
| `/badcases` | Badcase 检索 | `badcases:read` | `/v1/badcases/search` |
| `/functional` | 功能测试 | `functional:read` | `/v1/functional/...` |
| `/admin` | 租户/用户/Key/Provider | 平台管理员 | `/v1/admin/...` |
| `/settings` | 个人设置/语言 | 登录 | — |

## 规则

1. 路由懒加载；未登录跳转 `/login`。
2. 权限不足隐藏入口；直接访问由 API 403/404 兜底。
3. 详情页必须展示 `trace_id`（错误时）与版本/`manifest_hash`（Run）。
4. 不把 API Key 写入 URL。
