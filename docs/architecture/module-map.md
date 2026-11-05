# Pingce 模块地图（Module Map）

**版本**: 1.0.0 | **日期**: 2026-11-05 | **关联**: `constitution.md` v1.3.0

本文件定义平台的模块边界、职责、数据所有权与依赖规则。任何新增功能必须先回答「属于哪个模块」；回答不了，说明领域模型还没想清楚。

---

## 1. 模块化原则

1. **一个模块 = 一个业务能力边界**，不是一张表、不是一个技术层。
2. **每个模块只有一个所有者**（子 Agent 角色），同一时间只允许一个 Agent 修改同一模块。
3. **跨模块只能调用 `public.py`**，禁止 import 其他模块的 `models` / `repository` / `service`。
4. **每张表只属于一个模块**，禁止跨模块 JOIN；跨模块读取走公开查询接口或读模型。
5. **模块内强一致，模块间最终一致**：跨模块副作用通过 Outbox + 幂等事件处理器完成。
6. **先有接口，再有实现**：`public.py` 的 DTO 与 Protocol 必须先评审，再写实现。

---

## 2. 模块总览

| ID | 模块 | 职责 | 拥有的表 | 公开接口 | 依赖 | 阶段 |
|---|---|---|---|---|---|---|
| M00 | `core` | 配置、DB 会话、租户上下文、错误模型、ID/分页/时钟、测试夹具 | 无 | `TenantContext`、`AppError`、`UnitOfWork`、`Page[T]` | 无 | P0a |
| M01 | `identity` | 租户、用户、角色、权限、API Key、认证适配 | `tenant`、`user`、`role`、`permission`、`user_role`、`api_key` | `IdentityService`、`ApiKeyVerifier`、`Principal` | core | P0a |
| M02 | `audit` | 审计日志、MCP 工具调用审计、保留策略 | `audit_log`、`mcp_tool_call` | `AuditWriter`、`AuditReader` | core | P0a |
| M03 | `assets` | 对象存储抽象、预签名、校验、生命周期 | `artifact` | `Storage`、`ArtifactService` | core, audit | P0a |
| M14 | `observability` | 结构化日志、Trace、指标、健康检查、告警 | 无 | `get_logger`、`tracer`、`metrics` | core | P0a |
| M04 | `catalog` | 项目、数据源、数据集、版本、样本、血缘 | `project`、`datasource`、`dataset`、`dataset_version`、`sample`、`lineage_edge` | `CatalogService`、`CatalogReader` | core, assets, audit | P0b |
| M07 | `jobs` | 任务状态机、队列、重试、幂等、调度、DLQ | `job`、`job_event`、`dead_letter_task`、`idempotency_key` | `JobService`、`TaskRunner`、`JobHandler` | core, audit | P0b |
| M10 | `model_gateway` | Provider 配置、LiteLLM 适配、超时/重试/熔断、成本核算 | `provider_config`、`model_call` | `ModelGateway`、`ModelCallRecord` | core, audit | P0b |
| M06 | `evaluation` | 评分器、指标、套件、目标适配、Trace 接入、Run、样本结果、基线 | `evaluator`、`evaluator_version`、`metric`、`eval_suite`、`suite_version`、`target`、`run`、`run_item`、`score`、`judge_call`、`baseline` | `EvaluationService`、`RunReader`、`TargetAdapter`、`TraceSource` | core, catalog, jobs, model_gateway, assets, audit | P0b |
| M09 | `gate` | 门禁规则、基线对比、判定、证据 | `gate`、`gate_rule`、`gate_result` | `GateService`、`GateReader` | evaluation, catalog | P0c |
| M08 | `reporting` | 读模型、报告生成、对比报告、导出、快照 | `report_snapshot`、`read_model_*` | `ReportService`、`ReportReader` | evaluation, functional, catalog | P0c |
| M13 | `mcp` | MCP HTTP 适配、认证、工具注册表、限额、审计 | 无（复用 audit） | `McpServer`、`ToolRegistry` | identity, catalog, evaluation, gate, search, audit | P0c |
| M05 | `ingestion` | 连接器、同步任务、Schema 推断/漂移、清洗、质检 | `connector`、`ingestion_job`、`sync_cursor`、`quality_rule`、`quality_result` | `IngestionService`、`Connector SPI` | catalog, jobs, assets, audit | P1 |
| M11 | `search` | 向量索引、Embedding 版本、语义检索、关键词降级 | 无（Qdrant） | `VectorIndex`、`SemanticSearch` | catalog, evaluation | P1 |
| M12 | `functional` | 用例、套件、执行、断言、视觉差异、证据 | `test_case`、`test_suite`、`test_run`、`test_step`、`assertion`、`visual_diff` | `FunctionalTestService`、`TestRunner` | jobs, assets, audit | P2 |

> 阶段说明：P0a 基础设施 → P0b 核心评测闭环 → P0c 门禁/报告/MCP → P1 数据接入与语义检索 → P2 可视化功能测试。

---

## 3. 依赖关系

箭头表示「依赖」。**禁止出现环。**

```text
                         ┌──────────────┐
                         │  M00 core    │
                         └──────┬───────┘
        ┌───────────────┬───────┼────────┬──────────────┐
        ▼               ▼       ▼        ▼              ▼
   M14 observability  M01 identity  M02 audit  M07 jobs  M03 assets
                                                       │
                                                       ▼
                                                  M04 catalog
                                                   │   │   │
                             ┌─────────────────────┘   │   └──────────────┐
                             ▼                         ▼                  ▼
                     M10 model_gateway           M11 search          M05 ingestion
                             │                         │
                             ▼                         │
                        M06 evaluation ◄───────────────┘
                          │    │
              ┌───────────┘    └────────────┐
              ▼                             ▼
          M09 gate                     M08 reporting
              │                             ▲
              └──────────────► M13 mcp ◄────┘
                                   ▲
                                   │
                            M12 functional（P2）
```

**关键规则**：

- `core` 不依赖任何业务模块。
- `jobs` 不 import 任何业务模块；业务模块通过 `JobHandler` 注册表反向注入。
- `reporting` 只读；不得调用任何模块的写方法。
- `mcp` 只调用各模块 `public.py`，且只调用只读方法。
- `search` 不写业务表；只维护 Qdrant 索引与 embedding 元数据。
- `functional` 是 P2，`reporting` 对其依赖必须通过可选接口（`ReportSource`）注入，避免 P0 阻塞。

---

## 3.5 跨模块能力：Agent 接入

Agent 应用接入不是新模块，而是 `evaluation` 下的两个薄适配层：

| 方向 | 接口 | 说明 |
|---|---|---|
| Invoke | `TargetAdapter` | 平台调用被测 Agent，返回规范 `AgentResponse` |
| Observe | `TraceSource` | 从 OTLP / OpenInference / SDK 读取轨迹 |

硬规则：

- 适配器只做协议/字段映射，不做评分、不做业务判断。
- 评测核心不得出现 `if target == "xxx"` 的分叉。
- 新增 Agent 优先用声明式配置（OpenAI 兼容 / HTTP + JSONPath），不够再写适配器。
- 所有适配器必须通过同一套 conformance suite。
- 适配器版本、Target 配置版本写入 Run Manifest。

详见 `docs/architecture/agent-integration.md`。

---

## 4. 数据所有权

| 模块 | 表 | 说明 |
|---|---|---|
| identity | `tenant` / `user` / `role` / `permission` / `user_role` / `api_key` | 认证与授权 |
| audit | `audit_log` / `mcp_tool_call` | append-only |
| assets | `artifact` | 大对象元数据，二进制在 OSS |
| catalog | `project` / `datasource` / `dataset` / `dataset_version` / `sample` / `lineage_edge` | 数据资产 |
| ingestion | `connector` / `ingestion_job` / `sync_cursor` / `quality_rule` / `quality_result` | 接入与质检 |
| evaluation | `evaluator` / `evaluator_version` / `metric` / `eval_suite` / `suite_version` / `target` / `run` / `run_item` / `score` / `judge_call` / `baseline` | 评测主域 |
| jobs | `job` / `job_event` / `dead_letter_task` / `idempotency_key` | 任务与幂等 |
| reporting | `report_snapshot` / `read_model_*` | 只读投影 |
| gate | `gate` / `gate_rule` / `gate_result` | 门禁 |
| model_gateway | `provider_config` / `model_call` | 模型调用 |
| functional | `test_case` / `test_suite` / `test_run` / `test_step` / `assertion` / `visual_diff` | 功能测试 |
| search | 无（Qdrant collection） | 向量索引 |
| mcp | 无（写 `audit.mcp_tool_call`） | 协议适配 |

**硬规则**：

- 其他模块不得直接 `SELECT` 本模块的表；只允许通过 `public.py` 查询方法。
- 报表类跨域查询使用 `reporting` 拥有的读模型/物化视图，不允许在业务模块里写跨域 JOIN。
- 每张表必须在模块 README 中登记；新增表必须更新本文件。

---

## 5. 公开接口规范

每个模块必须提供 `public.py`，内容仅包含：

```python
# app/modules/catalog/public.py
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class DatasetVersionRef:
    tenant_id: str
    dataset_id: str
    version: int
    content_hash: str

class CatalogReader(Protocol):
    def get_dataset(self, ctx: TenantContext, dataset_id: str) -> DatasetView: ...
    def get_version(self, ctx: TenantContext, ref: DatasetVersionRef) -> DatasetVersionView: ...
    def page_samples(self, ctx: TenantContext, ref: DatasetVersionRef, cursor: str | None, limit: int) -> Page[SampleView]: ...
```

规则：

1. **只导出 Protocol、不可变 DTO、领域事件、枚举**；禁止导出 ORM 模型、Repository、内部 Service。
2. 所有方法第一个参数必须是 `TenantContext`；禁止隐式全局租户。
3. DTO 使用 `@dataclass(frozen=True)` 或 Pydantic `model_config = ConfigDict(frozen=True)`。
4. 分页统一返回 `Page[T]`（`items` + `next_cursor`）。
5. 公开接口变更必须升版本并在 `CHANGELOG` 记录；破坏性变更需 ADR。
6. 跨模块调用不得共享数据库事务；需要一致性时使用 Outbox 事件。

---

## 6. 跨模块一致性

- 模块内：同一 DB 事务。
- 模块间：`event_outbox`（由 `core` 提供）→ 事件总线 → 幂等消费者。
- 事件命名：`<module>.<entity>.<action>`，如 `evaluation.run.completed`。
- 消费者必须幂等：以 `event_id` 建唯一索引。
- 禁止在事务内调用其他模块的写方法或外部 API。

---

## 7. 架构测试（CI 硬门禁）

使用 `import-linter` + 自定义 AST 测试，至少覆盖：

```ini
[importlinter]
root_package = app

[importlinter:contract:no-cross-module-internals]
name = 禁止跨模块内部导入
type = forbidden
source_modules =
    app.modules.catalog
forbidden_modules =
    app.modules.evaluation.models
    app.modules.evaluation.repository
    app.modules.evaluation.service
```

自定义测试逻辑：

1. 遍历 `app/modules/*` 的所有 import。
2. 若 import 目标属于另一个模块，则路径必须以 `.public` 结尾。
3. 若发现 `models` / `repository` / `service` 跨模块导入 → 测试失败。
4. 若发现循环依赖 → 测试失败。
5. 若发现业务模块 import `app.api` → 测试失败。

---

## 8. 阶段与关键路径

```text
P0a: CORE-03 → IDN-01 → IDN-03 → AST-01
P0b: CAT-03 → CAT-04 → JOB-02 → EVL-05 → EVL-06
P0c: MCP-02 → MCP-04 → MCP-09 → MCP-10
P1 : ING-04 / SRC-05
P2 : FUN-03 / FUN-04
```

关键路径上的任务延期，直接推迟整体交付。非关键路径任务可并行。

---

## 9. 模块变更流程

1. 提 ADR：说明新模块/边界调整的动机、依赖方向、数据所有权。
2. 更新本文件与 `task-index.md`。
3. 更新架构测试契约。
4. 在模块 `README.md` 登记职责、表、公开接口。
5. 通过评审后才允许创建目录与迁移。
