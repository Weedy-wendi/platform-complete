# Pingce 文档导航

本目录是项目的设计与执行文档。**代码不是唯一真相，契约与任务卡同样是。**

---

## 1. 先读什么

新加入的开发者 / 子 Agent，按这个顺序读：

1. `.specify/memory/constitution.md` — 项目宪法（硬约束）
2. `docs/architecture/module-map.md` — 模块边界与数据所有权
3. `docs/architecture/module-conventions.md` — 模块内怎么写代码
4. `docs/planning/subagent-protocol.md` — 接到任务后怎么做
5. `docs/planning/task-index.md` — 任务总表与状态
6. 对应模块的任务卡 — `docs/planning/tasks/*.md`

---

## 2. 文档地图

| 目录 | 内容 | 何时看 |
|---|---|---|
| `.specify/memory/constitution.md` | 核心原则、技术栈硬约束、安全、MCP、模块化治理 | 任何决策前 |
| `docs/adr/` | 架构决策记录（ADR） | 改架构/选型前 |
| `docs/architecture/module-map.md` | 15 个模块、依赖、表归属、公开接口 | 确定功能归属时 |
| `docs/architecture/module-conventions.md` | 目录结构、命名、测试、迁移、DoD | 写代码前 |
| `docs/architecture/maintainability.md` | 可维护性三维度、八机制、指标、30/60/90、红线 | 设计与复盘时 |
| `docs/architecture/edge-cases.md` | 14 类边界场景、状态机/并发/故障矩阵、评审清单 | 设计/评审/测试时 |
| `docs/architecture/agent-integration.md` | Agent 接入六模式、TargetAdapter/TraceSource、Record/Replay | 接入新 Agent 时 |
| `docs/planning/subagent-protocol.md` | 子 Agent 标准流程、交付模板、升级规则 | 每个任务开始前 |
| `docs/planning/task-index.md` | 143 个任务、阶段、依赖、状态 | 排期/找任务时 |
| `docs/planning/tasks/00-foundation.md` | core / identity / audit / assets / observability | P0a |
| `docs/planning/tasks/01-data.md` | catalog / ingestion / search | P0b / P1 |
| `docs/planning/tasks/02-evaluation.md` | evaluation / jobs / model_gateway / gate / reporting | P0b / P0c |
| `docs/planning/tasks/03-functional.md` | 可视化功能测试 | P2 |
| `docs/planning/tasks/04-mcp.md` | MCP 只读接入 | P0c |
| `docs/planning/tasks/05-quality.md` | 质量护栏（架构/契约/可复现/迁移/运行） | P0q |
| `specs/README.md` | 规格索引：阶段套件、模块契约、任务映射 | 找规格/写实现前 |
| `specs/001-mcp-server/` | MCP 功能规格、计划、契约、快速开始 | MCP 实施 |
| `specs/002-core/` ~ `018-frontend/` | 各模块 spec / plan / contracts | 按模块实施时 |

---

## 3. 真相优先级

出现冲突时，按以下顺序判定：

1. `constitution.md`（最高）
2. ADR（已接受的架构决策）
3. `module-map.md`（模块边界）
4. `contracts/`（接口契约）
5. `spec.md` / `plan.md`
6. `tasks/*.md`（执行细节）
7. 代码注释

**代码与文档不一致时，先确认哪一方是错的；不得默认代码正确。**

---

## 4. 文档维护规则

- 新增模块：更新 `module-map.md` + `task-index.md` + 架构测试。
- 新增公开接口：更新 `public.py` 契约 + 模块 README + `CHANGELOG`。
- 新增任务：写任务卡 + 在 `task-index.md` 登记。
- 变更架构：先写 ADR，再改文档，最后改代码。
- 任务完成：更新 `task-index.md` 状态，并在交付报告中附验证证据。

---

## 5. 当前阶段

| 阶段 | 状态 | 目标 | 说明 |
|---|---|---|---|
| P0a 基础设施 | 完成（CORE/IDN/AUD/AST/OBS） | 租户、Key、对象存储、审计、可观测 | CORE-01~13、IDN-01~13、AUD-01~03、AST-01~05、OBS-01~05 已完成 |
| P0q 质量护栏 | 完成 | 架构/契约/重放/迁移/运行门禁生效 | QUAL-01~10 完成；快照、边界矩阵、迁移/破坏性 DDL、运行门禁就绪 |
| P0b 评测闭环 | 完成 | 数据集 + Run + 复现 | CAT/JOB/MGW-01~07/EVL-01~17 完成 |
| P0c 门禁/报告/MCP | 完成 | Agent 可通过 MCP 读结果 | MCP-01~15、GAT-01~06、REP-01~06 完成 |
| P0d REST/OpenAPI | 完成 | Web/外部客户端通过 `/v1` 访问 | API-01~14 完成；规格见 `specs/017-rest-api/` |
| P1 接入/检索 | 完成 | CSV/REST + 语义检索 | ING-01~11、SRC-01~06 完成 |
| P2 功能测试 | 完成 | 浏览器用例 + 证据 | FUN-01~08 完成 |
| P3 Web 前端 | 完成 | 浏览器完成数据/评测/门禁/报告操作 | FE-01~21 完成；规格见 `specs/018-frontend/` |

任务总数：**173**；已完成：**173**；未开始：**0**。

> MCP 已完成的是“只读适配器”，业务数据依赖平台服务。`search_badcases` / `check_gate` 在 SRC-05 / GAT-04 就绪前返回 `UPSTREAM_UNAVAILABLE`；生产环境必须提供 `PINGCE_MCP_SERVICES_FACTORY`。
>
> 164 个项目任务与 `specs/001-mcp-server/tasks.md` 的 T001–T086 是两套编号；后者已全部完成。
>
> 2026-11-05 补登 P0d REST/OpenAPI 与 P3 Web 前端：REST API 是宪法「API/CLI First」的主接入层；前端只通过 `/v1` 访问，不直连 MCP。
