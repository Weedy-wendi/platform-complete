# Pingce 规格索引（Spec Index）

本目录是项目的功能规格（spec-driven）入口。每个规格目录包含：

- `spec.md`：需求、用户故事、验收场景、边界
- `plan.md`：技术方案、模块结构、数据模型、阶段、风险
- `contracts/`：公开接口 / 协议 / OpenAPI
- `tasks.md`：任务映射；**项目任务状态以 `docs/planning/task-index.md` 为准**

---

## 1. 规格总表

| 规格 | 阶段 | 模块 | 任务前缀 | 状态 |
|---|---|---|---|---|
| `001-mcp-server` | P0c | M13 mcp | T001–T086 | **DONE**（适配器） |
| `002-core` | P0a | M00 core | CORE | **DONE** |
| `003-identity` | P0a | M01 identity | IDN | **DONE** |
| `004-audit` | P0a | M02 audit | AUD | **DONE** |
| `005-assets` | P0a | M03 assets | AST | **DONE** |
| `006-observability` | P0a | M14 observability | OBS | **DONE** |
| `007-catalog` | P0b | M04 catalog | CAT | **DONE** |
| `008-jobs` | P0b | M07 jobs | JOB | **DONE** |
| `009-model-gateway` | P0b | M10 model_gateway | MGW | **DONE** |
| `010-evaluation` | P0b | M06 evaluation | EVL | **DONE** |
| `011-gate` | P0c | M09 gate | GAT | **DONE** |
| `012-reporting` | P0c | M08 reporting | REP | **DONE** |
| `013-ingestion` | P1 | M05 ingestion | ING | **DONE** |
| `014-search` | P1 | M11 search | SRC | **DONE** |
| `015-functional` | P2 | M12 functional | FUN | **DONE** |
| `016-quality-guardrails` | P0q | 跨模块 | QUAL | **DONE** |
| `017-rest-api` | P0d | api（新增） | API | **DONE** |
| `018-frontend` | P3 | frontend（新增） | FE | **DONE** |

---

## 2. 模块 → 规格 / 契约映射

| 模块 | 规格目录 | 契约文件 |
|---|---|---|
| M00 core | `002-core` | `contracts/interfaces.md` |
| M01 identity | `003-identity` | `contracts/interfaces.md` |
| M02 audit | `004-audit` | `contracts/interfaces.md` |
| M03 assets | `005-assets` | `contracts/interfaces.md` |
| M14 observability | `006-observability` | `contracts/interfaces.md` |
| M04 catalog | `007-catalog` | `contracts/interfaces.md` |
| M07 jobs | `008-jobs` | `contracts/interfaces.md` |
| M10 model_gateway | `009-model-gateway` | `contracts/interfaces.md` |
| M06 evaluation | `010-evaluation` | `contracts/interfaces.md` |
| M09 gate | `011-gate` | `contracts/interfaces.md` |
| M08 reporting | `012-reporting` | `contracts/interfaces.md` |
| M05 ingestion | `013-ingestion` | `contracts/interfaces.md` |
| M11 search | `014-search` | `contracts/interfaces.md` |
| M12 functional | `015-functional` | `contracts/interfaces.md` |
| API（新增） | `017-rest-api` | `contracts/openapi.yaml`、`contracts/errors.md` |
| Frontend（新增） | `018-frontend` | `contracts/routes.md`、`contracts/api-client.md` |

> 每个模块有独立的 `spec.md` / `plan.md` / `contracts/` / `tasks.md`。

---

## 3. 编号与任务口径

- `001-mcp-server` 使用特性任务 **T001–T086**，已全部完成并通过测试。
- 其他规格使用模块任务前缀（`CORE-01`、`CAT-03`、`API-01`、`FE-01` 等），与 `docs/planning/task-index.md` 一一对应。
- 本目录的 `tasks.md` 只做任务映射，**不替代任务索引**；状态、依赖、Agent 归属以任务索引与任务卡为准。
- **143 个项目任务**与 MCP 的 **86 个特性任务**是两套编号，不要混用。

---

## 4. 为什么按模块拆 spec

每个模块有独立的业务边界、数据所有权和公开接口，独立 spec 便于：

- 按模块分配 Agent 与评审；
- 单独维护契约与快照；
- 按依赖顺序实施，不受其他模块文档变更影响。

跨模块决策（租户上下文、审计、存储、Run Manifest、门禁口径）在相关模块的 `spec.md`/`plan.md` 中引用或约束，不在本索引重复。

---

## 5. 依赖与关键路径

```text
P0a: 002-core → 003-identity → 004-audit → 005-assets → 006-observability
P0b: 007-catalog → 008-jobs → 009-model-gateway → 010-evaluation
P0c: 011-gate / 012-reporting → 001-mcp-server（已完成）
P1 : 013-ingestion / 014-search
P2 : 015-functional
P0q: 016-quality-guardrails（跨阶段并行）
P0d: 017-rest-api
P3 : 018-frontend
```

MCP（`001`）已作为只读适配器完成，但真实数据依赖 `CAT-05`、`EVL-08/09`、`GAT-04`、`SRC-05`、`REP-02`；生产需通过 `PINGCE_MCP_SERVICES_FACTORY` 注入平台服务。

---

## 6. 新增/变更流程

1. 先改对应模块的 `spec.md`，再改 `plan.md`，最后改契约与 `tasks.md`。
2. 更新 `docs/planning/task-index.md` 的任务、依赖、状态。
3. 涉及模块边界的变更先写 ADR，并更新 `docs/architecture/module-map.md`。
4. 契约变更必须同步快照测试（OpenAPI / `tools.yaml` / `public.py`）。
