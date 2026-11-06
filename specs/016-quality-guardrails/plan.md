# Implementation Plan: 质量护栏（P0q）

**Feature**: `003-quality-guardrails` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- **架构**: `import-linter` + AST 测试；负例注入必须失败。
- **契约**: `public.py` 快照、OpenAPI 快照、MCP `tools.yaml` 快照；前端 `openapi-typescript` 生成后 diff。
- **可复现**: Manifest 重放 Job、Golden Set、Judge 校准报告、不可变版本测试。
- **数据演进**: Alembic `up/down/up`、破坏性 DDL 检查、N-1 兼容矩阵、恢复演练 Runbook。
- **运行**: Prometheus 规则 + Grafana 看板 JSON、kill switch、灰度/回滚 Runbook、技术债账本。
- **边界**: `tests/edge/` 表驱动 + 故障注入；CI `edge-suite` <10 分钟。

## 2. CI Job 设计

| Job | 内容 | 阻断 |
|---|---|---|
| `architecture` | import-linter、AST、`public.py` 快照 | 是 |
| `contracts` | OpenAPI、`tools.yaml`、前端类型 diff | 是 |
| `reproducibility` | 重放 5 次、Judge 校准、不可变版本 | 是 |
| `migrations` | `up/down/up`、破坏性 DDL、N-1 | 是 |
| `edge-suite` | 14 类边界场景 | 是 |
| `runtime` | 告警规则语法、kill switch 冒烟 | 告警/阻断按环境 |

## 3. 阶段

1. QUAL-01 架构与契约护栏（CORE-01/06 后）。
2. QUAL-03 数据演进护栏（CORE-07 后）。
3. QUAL-02 可复现护栏（EVL-05/10/03、CAT-03 后）。
4. QUAL-05 边界套件（CORE-07、QUAL-01 后）。
5. QUAL-04 运行与迭代护栏（OBS-03/05 后）。

## 4. 风险

| 风险 | 缓解 |
|---|---|
| 门禁太慢 | 分 Job、缓存依赖、契约测试并行 |
| 快照变更被“一键更新”绕过 | 快照变更需评审 + CODEOWNERS |
| 边界套件 flaky | fake/容器隔离、固定种子、重试上限 |
| kill switch 误用 | 权限 + 审计 + 演练 |

## 5. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | 重放/校准/不可变门禁 |
| II 五原语 | 契约与边界测试 |
| III API/CLI First | OpenAPI 快照与前端类型生成 |
| IV Boring Tech | 固定工具版本、lockfile |
| V 控制/执行分离 | 边界套件不依赖生产执行面 |
| VI 证据驱动 | 所有门禁在 CI 中可复现 |
| VII 模块化单体 | import 边界硬门禁 |
