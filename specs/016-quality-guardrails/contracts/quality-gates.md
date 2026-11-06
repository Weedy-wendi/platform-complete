# 质量门禁契约

**范围**: 跨模块 | **Owner**: agent-qa / agent-core

## 门禁清单

| Gate | 命令 | 失败条件 |
|---|---|---|
| `architecture` | `lint-imports` + `pytest tests/architecture` | 跨模块内部 import、循环依赖、业务模块 import `app.api` |
| `contracts` | `pytest tests/contract` + `pnpm gen:api && git diff --exit-code` | `public.py`/OpenAPI/`tools.yaml` 漂移；前端手写类型 |
| `reproducibility` | `pytest tests/repro` | 重放不一致；Judge 差 >0.05；κ <0.7；版本可变 |
| `migrations` | `alembic upgrade head && downgrade -1 && upgrade head` | 迁移失败；破坏性 DDL 无豁免；N-1 不兼容 |
| `edge-suite` | `pytest tests/edge` | 14 类场景缺失或失败；>10 分钟 |
| `runtime` | `promtool check rules` + kill-switch 冒烟 | 告警语法错误；开关不可用 |

## 负例要求

每个门禁必须有“注入违规 → 必须失败”的自测，禁止用 `skip`/`noqa` 绕过。

## 产物

- `backend/tests/architecture/`
- `backend/tests/contract/`
- `backend/tests/repro/`
- `backend/tests/edge/`
- `frontend/src/types/api.ts`（生成）
- `docs/runbooks/db-restore.md`
- `docs/runbooks/rollback.md`
- `deploy/prometheus/alerts.yaml`
- `deploy/grafana/dashboards/*.json`
