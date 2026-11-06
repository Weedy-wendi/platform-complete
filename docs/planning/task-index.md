# 任务索引（Task Index）

**版本**: 1.3.0 | **日期**: 2026-11-06 | **任务总数**: 173

本文件是任务状态的唯一真相。任务卡明细在 `docs/planning/tasks/`；P0d/P3 的任务卡在 `specs/017-rest-api/tasks.md`、`specs/018-frontend/tasks.md`。执行协议见 `docs/planning/subagent-protocol.md`。

---

## 1. 使用方式

1. 按阶段找到任务 ID。
2. 打开对应任务卡，确认输入、输出、依赖、验收、测试。
3. 确认依赖状态为 Done。
4. 按 `subagent-protocol.md` 执行。
5. 完成后回到本文件更新状态。

状态取值：`TODO` / `DOING` / `BLOCKED` / `DONE`。

---

## 2. 阶段与里程碑

| 阶段 | 目标 | 模块 | 任务数 | 里程碑 |
|---|---|---|---|---|
| P0a | 基础设施可运行 | CORE、IDN、AUD、AST、OBS | 49 | 能建租户、发 Key、存对象、写审计 |
| P0q | 质量护栏（跨阶段） | QUAL | 5 | 架构/契约/重放/迁移/运行/边界门禁在 CI 生效 |
| P0b | 核心评测闭环 | CAT、JOB、MGW、EVL | 34 | 能建数据集、接入 Agent、跑评测、复现结果 |
| P0c | 门禁/报告/MCP | GAT、REP、MCP | 25 | Agent 能通过 HTTP MCP 读取评测结果 |
| P0d | REST/OpenAPI 接入层 | API | 10 | Web/外部客户端可通过 `/v1` 读写平台能力 |
| P1 | 数据接入与语义检索 | ING、SRC | 14 | 能接 CSV/REST，能语义检索 Badcase |
| P2 | 可视化功能测试 | FUN | 6 | 能跑浏览器用例并产出证据 |
| P3 | Web 前端 | FE | 10 | 可在浏览器完成数据/评测/门禁/报告操作 |

---

## 3. 关键路径

```text
P0a/P0b/P0c:
CORE-03 → CORE-04 → IDN-01 → IDN-03 → CAT-03 → CAT-04
        → JOB-02 → JOB-03 → EVL-05 → EVL-06
        → MCP-02 → MCP-04 → MCP-09 → MCP-10

REST/前端（P0d/P3）:
API-01 → API-02 → API-05 → FE-01 → FE-03
```

关键路径上任一任务延期，整体交付延期。非关键路径任务可并行。MCP 段已完成，当前关键路径是 `CORE → IDN → CAT → JOB → EVL → GAT/REP → API → FE`。

---

## 4. 并行波次

| Wave | 可并行任务 | 前置 |
|---|---|---|
| W0 | CORE-01 ~ CORE-13、OBS-01 ~ OBS-05、AUD-01 | 无 |
| W1 | IDN-01 ~ IDN-06、AST-01 ~ AST-05、AUD-02/03 | W0 |
| W2 | CAT-01 ~ CAT-07、JOB-01 ~ JOB-06、MGW-01 ~ MGW-05、QUAL-01、QUAL-03 | W1 |
| W3 | EVL-01 ~ EVL-16、QUAL-02、QUAL-05 | W2 |
| W4 | GAT-01 ~ GAT-05、REP-01 ~ REP-05、MCP-01 ~ MCP-11、MCP-13 ~ MCP-15、QUAL-04 | W3 |
| W5 | ING-01 ~ ING-08、SRC-01 ~ SRC-06、MCP-12 | W3/W4 |
| W6 | FUN-01 ~ FUN-06 | W5 |

> MCP-12 依赖 SRC-05（W5），因此排在 W5；其余 MCP 任务在 W4。
>
> P0d REST：API-01/02 可在 W1/W4 后启动；API-03/04/05/08/09 在 W4/W5 后并行；API-06 依赖 `FUN-01`、API-07 依赖 `SRC-05`，排在 W6 后。P3 前端（FE-01 ~ FE-10）在 API-02/03/04/05/06/07/08/09 完成后串行推进。

同一 Wave 内，只有文件集合不相交的任务才可以并行。

---

## 5. 模块任务总表

### P0a — 基础设施

| ID | 任务 | 模块 | 依赖 | Agent | 状态 |
|---|---|---|---|---|---|
| CORE-01 | 项目骨架与模块加载 | core | — | agent-core | DONE |
| CORE-02 | 配置与密钥管理 | core | CORE-01 | agent-core | DONE |
| CORE-03 | DB 会话与租户上下文 | core | CORE-01/02 | agent-core | DONE |
| CORE-04 | 错误模型与错误码 | core | CORE-01 | agent-core | DONE |
| CORE-05 | ID/分页/时钟工具 | core | CORE-01 | agent-core | DONE |
| CORE-06 | 架构测试 | core | CORE-01 | agent-core | DONE |
| CORE-07 | 测试夹具（MySQL/Redis） | core | CORE-03 | agent-core | DONE |
| CORE-08 | 平台读写会话路由与配置 | core | CORE-02/03 | agent-core | DONE |
| CORE-09 | Redis 测试 key 隔离 | core | CORE-07 | agent-core | DONE |
| CORE-10 | DB 查询日志（tenant/trace，脱参） | core | CORE-03 | agent-core | DONE |
| CORE-11 | import-linter 架构契约 | core | CORE-06 | agent-core | DONE |
| CORE-12 | 错误码注册表与映射覆盖 | core | CORE-04 | agent-core | DONE |
| CORE-13 | 时钟工具 UTC 测试 | core | CORE-05 | agent-core | DONE |
| IDN-01 | 租户/用户/角色模型 | identity | CORE-03 | agent-identity | DONE |
| IDN-02 | RBAC 策略引擎 | identity | IDN-01 | agent-identity | DONE |
| IDN-03 | API Key 生命周期 | identity | IDN-01 | agent-identity | DONE |
| IDN-04 | 认证适配器（JWT/API Key） | identity | IDN-02/03 | agent-identity | DONE |
| IDN-05 | 租户隔离测试 | identity | IDN-01~04 | agent-identity | DONE |
| IDN-06 | 身份审计钩子 | identity | IDN-03、AUD-01 | agent-identity | DONE |
| IDN-07 | API Key 缓存 TTL 上限 | identity | IDN-03 | agent-identity | DONE |
| IDN-08 | 软删除与唯一约束处理 | identity | IDN-01 | agent-identity | DONE |
| IDN-09 | 租户禁用/删除校验 | identity | IDN-04 | agent-identity | DONE |
| IDN-10 | Principal auth_method 契约对齐 | identity | IDN-04 | agent-identity | DONE |
| IDN-11 | MCP 租户状态校验 | identity | IDN-09 | agent-identity | DONE |
| IDN-12 | JWT 适配器可注入 | identity | IDN-10 | agent-identity | DONE |
| IDN-13 | 软删除租户回归测试 | identity | IDN-09 | agent-identity | DONE |
| AUD-01 | audit_log 表与写入器 | audit | CORE-03 | agent-identity | DONE |
| AUD-02 | append-only 与保留策略 | audit | AUD-01 | agent-identity | DONE |
| AUD-03 | 审计查询接口 | audit | AUD-01 | agent-identity | DONE |
| AST-01 | Storage SPI + OSS 适配 | assets | CORE-02 | agent-data | DONE |
| AST-02 | 预签名与校验 | assets | AST-01 | agent-data | DONE |
| AST-03 | artifact 元数据 | assets | AST-01、CORE-03 | agent-data | DONE |
| AST-04 | MinIO 适配（私有化） | assets | AST-01 | agent-data | DONE |
| AST-05 | 存储契约测试 | assets | AST-01~04 | agent-data | DONE |
| OBS-01 | 结构化日志 | observability | CORE-01 | agent-core | DONE |
| OBS-02 | OpenTelemetry Trace | observability | OBS-01 | agent-core | DONE |
| OBS-03 | Prometheus 指标 | observability | OBS-01 | agent-core | DONE |
| OBS-04 | 健康检查 | observability | CORE-03 | agent-core | DONE |
| OBS-05 | 告警规则 | observability | OBS-03 | agent-core | DONE |

### P0b — 核心评测闭环

| ID | 任务 | 模块 | 依赖 | Agent | 状态 |
|---|---|---|---|---|---|
| CAT-01 | 项目 CRUD | catalog | CORE-03 | agent-data | DONE |
| CAT-02 | 数据源模型与密钥引用 | catalog | CAT-01 | agent-data | DONE |
| CAT-03 | 数据集与不可变版本 | catalog | CAT-01、AST-03 | agent-data | DONE |
| CAT-04 | 样本批量写入 | catalog | CAT-03 | agent-data | DONE |
| CAT-05 | 目录查询接口 | catalog | CAT-03/04 | agent-data | DONE |
| CAT-06 | 数据血缘 | catalog | CAT-03 | agent-data | DONE |
| CAT-07 | 目录测试（版本/隔离） | catalog | CAT-03~06 | agent-data | DONE |
| JOB-01 | job/job_event 模型 | jobs | CORE-03 | agent-eval | DONE |
| JOB-02 | TaskRunner SPI + Celery | jobs | JOB-01 | agent-eval | DONE |
| JOB-03 | 重试/幂等/DLQ | jobs | JOB-02 | agent-eval | DONE |
| JOB-04 | 调度器单例 | jobs | JOB-02 | agent-eval | DONE |
| JOB-05 | 进度与 SSE | jobs | JOB-01 | agent-eval | DONE |
| JOB-06 | 故障与恢复测试 | jobs | JOB-03/04 | agent-eval | DONE |
| MGW-01 | Provider 配置 | model_gateway | CORE-02 | agent-eval | DONE |
| MGW-02 | LiteLLM 适配 | model_gateway | MGW-01 | agent-eval | DONE |
| MGW-03 | 超时/重试/熔断 | model_gateway | MGW-02 | agent-eval | DONE |
| MGW-04 | Token/成本核算 | model_gateway | MGW-02 | agent-eval | DONE |
| MGW-05 | Provider 契约测试 | model_gateway | MGW-02~04 | agent-eval | DONE |
| EVL-01 | 评分器/指标模型 | evaluation | CORE-03 | agent-eval | DONE |
| EVL-02 | 规则评分器 | evaluation | EVL-01 | agent-eval | DONE |
| EVL-03 | Judge 评分器 | evaluation | EVL-01、MGW-02 | agent-eval | DONE |
| EVL-04 | Suite/Target/Baseline | evaluation | EVL-01 | agent-eval | DONE |
| EVL-05 | Run 创建与 Manifest | evaluation | CAT-03、EVL-04 | agent-eval | DONE |
| EVL-06 | Run 执行器 | evaluation | EVL-05、JOB-02、MGW-02 | agent-eval | DONE |
| EVL-07 | 状态机/重试/幂等 | evaluation | EVL-06、JOB-03 | agent-eval | DONE |
| EVL-08 | Run 查询接口 | evaluation | EVL-05 | agent-eval | DONE |
| EVL-09 | 对比与统计 | evaluation | EVL-08 | agent-eval | DONE |
| EVL-10 | 复现测试 | evaluation | EVL-05/06 | agent-qa | DONE |
| EVL-11 | Judge 校准流程 | evaluation | EVL-03 | agent-eval | DONE |
| EVL-12 | 成本预算与熔断 | evaluation | EVL-06、MGW-04 | agent-eval | DONE |
| EVL-13 | TargetAdapter SPI 与注册表 | evaluation | EVL-04 | agent-eval | DONE |
| EVL-14 | 声明式 HTTP/OpenAI 适配器 | evaluation | EVL-13 | agent-eval | DONE |
| EVL-15 | TraceSource（OTLP/OpenInference） | evaluation | EVL-13、OBS-02、AST-03 | agent-eval | DONE |
| EVL-16 | 适配器一致性 + Record/Replay | evaluation | EVL-14、EVL-15 | agent-qa | DONE |

### P0q — 质量护栏（跨阶段）

| ID | 任务 | 模块 | 依赖 | Agent | 状态 |
|---|---|---|---|---|---|
| QUAL-01 | 架构与契约护栏 | 跨模块 | CORE-01、CORE-06 | agent-qa | DONE |
| QUAL-02 | 可复现护栏 | 跨模块 | EVL-10、EVL-03、CAT-03 | agent-qa | DONE |
| QUAL-03 | 数据演进护栏 | 跨模块 | CORE-07 | agent-core | DONE |
| QUAL-04 | 运行与迭代护栏 | 跨模块 | OBS-03、OBS-05 | agent-core | DONE |
| QUAL-05 | 边界与异常路径测试套件 | 跨模块 | CORE-07、QUAL-01 | agent-qa | DONE |

> 详细任务卡见 `docs/planning/tasks/05-quality.md`。

### P0c — 门禁/报告/MCP

| ID | 任务 | 模块 | 依赖 | Agent | 状态 |
|---|---|---|---|---|---|
| GAT-01 | Gate/Rule 模型 | gate | EVL-04 | agent-eval | DONE |
| GAT-02 | 判定引擎 | gate | GAT-01、EVL-09 | agent-eval | DONE |
| GAT-03 | 基线集成 | gate | GAT-02 | agent-eval | DONE |
| GAT-04 | 结果与证据 | gate | GAT-02 | agent-eval | DONE |
| GAT-05 | 门禁测试（误拦/漏拦） | gate | GAT-02~04 | agent-qa | DONE |
| REP-01 | 读模型 | reporting | EVL-08 | agent-eval | DONE |
| REP-02 | Run 报告 | reporting | REP-01 | agent-eval | DONE |
| REP-03 | 对比报告 | reporting | REP-01、EVL-09 | agent-eval | DONE |
| REP-04 | 导出（JSON/CSV/JUnit） | reporting | REP-02 | agent-eval | DONE |
| REP-05 | 快照与分享链接 | reporting | REP-02 | agent-eval | DONE |
| MCP-01 | 模块骨架/配置/CLI | mcp | CORE-02 | agent-mcp | DONE |
| MCP-02 | AuthProvider + API Key | mcp | MCP-01、IDN-03 | agent-mcp | DONE |
| MCP-03 | OAuth 预留 | mcp | MCP-02 | agent-mcp | DONE |
| MCP-04 | 工具注册表/allowlist | mcp | MCP-01 | agent-mcp | DONE |
| MCP-05 | 游标/限额/脱敏 | mcp | MCP-01、AST-01 | agent-mcp | DONE |
| MCP-06 | 限流 | mcp | MCP-01 | agent-mcp | DONE |
| MCP-07 | 审计 | mcp | MCP-01、AUD-01 | agent-mcp | DONE |
| MCP-08 | 错误/可观测/健康 | mcp | MCP-01、OBS-02 | agent-mcp | DONE |
| MCP-09 | 协议装配 | mcp | MCP-02/04/05/06/07/08 | agent-mcp | DONE |
| MCP-10 | 数据集工具 | mcp | MCP-09、CAT-05 | agent-mcp | DONE |
| MCP-11 | 评测工具 | mcp | MCP-09、EVL-08/09 | agent-mcp | DONE |
| MCP-12 | Badcase/Gate 工具 | mcp | MCP-09、GAT-04、SRC-05 | agent-mcp | DONE |
| MCP-13 | Resources | mcp | MCP-09、CAT-05、REP-02 | agent-mcp | DONE |
| MCP-14 | 安全测试 | mcp | MCP-10~13 | agent-qa | DONE |
| MCP-15 | 压测与部署 | mcp | MCP-14 | agent-qa | DONE |

> **MCP 依赖说明**：MCP-10 ~ MCP-15 的 `DONE` 表示**适配器、契约、测试**完成，不表示端到端已有真实平台数据。MCP-10/11/13 的真实数据依赖 CAT-05、EVL-08/09、REP-02；MCP-12 依赖 GAT-04、SRC-05。这些平台任务仍为 `TODO`，因此 MCP 当前使用 `app/services` 的内存实现；生产必须由平台注入 `PINGCE_MCP_SERVICES_FACTORY`。

### P0d — REST/OpenAPI 接入层（补登）

> 2026-11-05 补登：REST/OpenAPI 是宪法「API/CLI First」的主接入层，原先未在任务索引中。规格与任务卡见 `specs/017-rest-api/`（`tasks.md` 为任务卡）。

| ID | 任务 | 模块 | 依赖 | Agent | 状态 |
|---|---|---|---|---|---|
| API-01 | FastAPI 骨架、`/v1` 路由、错误模型、健康端点 | api | CORE-02 | agent-api | DONE |
| API-02 | 认证/租户/RBAC/scope/限流 | api | API-01、IDN-04 | agent-api | DONE |
| API-03 | 项目/数据源/数据集/版本/样本接口 | api | API-02、CAT-05 | agent-api | DONE |
| API-04 | 评分器/Suite/Target 接口 | api | API-02、EVL-04 | agent-api | DONE |
| API-05 | Run 创建（202）/查询/明细/对比/取消 | api | API-02、EVL-08 | agent-api | DONE |
| API-06 | Gate/报告/导出/功能测试接口 | api | API-02、GAT-04、REP-02、FUN-01 | agent-api | DONE |
| API-07 | Badcase 检索接口（委托 SRC-05） | api | API-02、SRC-05 | agent-api | DONE |
| API-08 | 管理面：租户/用户/角色/Key/Provider | api | API-02、IDN-02 | agent-api | DONE |
| API-09 | OpenAPI 快照 + 前端类型生成校验 | api | API-01、QUAL-01 | agent-api | DONE |
| API-10 | 契约/安全/性能测试 | api | API-03~08 | agent-qa | DONE |

### P1 — 数据接入与语义检索

| ID | 任务 | 模块 | 依赖 | Agent | 状态 |
|---|---|---|---|---|---|
| ING-01 | Connector SPI | ingestion | CAT-03 | agent-data | DONE |
| ING-02 | CSV/JSONL 连接器 | ingestion | ING-01 | agent-data | DONE |
| ING-03 | REST 连接器 | ingestion | ING-01 | agent-data | DONE |
| ING-04 | 同步任务与水位 | ingestion | ING-02、JOB-02 | agent-data | DONE |
| ING-05 | Schema 推断/漂移 | ingestion | ING-04 | agent-data | DONE |
| ING-06 | 清洗规则 | ingestion | ING-04 | agent-data | DONE |
| ING-07 | 质检规则与结果 | ingestion | ING-04、CAT-03 | agent-data | DONE |
| ING-08 | 接入测试 | ingestion | ING-02~07 | agent-qa | DONE |
| SRC-01 | VectorIndex SPI | search | CORE-01 | agent-search | DONE |
| SRC-02 | Qdrant 适配 | search | SRC-01 | agent-search | DONE |
| SRC-03 | Embedding 版本管理 | search | SRC-02、MGW-02 | agent-search | DONE |
| SRC-04 | 索引任务与重建 | search | SRC-02、JOB-02 | agent-search | DONE |
| SRC-05 | 语义检索 + 关键词降级 | search | SRC-02/03 | agent-search | DONE |
| SRC-06 | 租户隔离与降级测试 | search | SRC-05 | agent-qa | DONE |

### P2 — 可视化功能测试

| ID | 任务 | 模块 | 依赖 | Agent | 状态 |
|---|---|---|---|---|---|
| FUN-01 | 用例/套件模型 | functional | CORE-03 | agent-functional | DONE |
| FUN-02 | API 断言执行器 | functional | FUN-01、JOB-02 | agent-functional | DONE |
| FUN-03 | 浏览器沙箱执行 | functional | FUN-01、JOB-02 | agent-functional | DONE |
| FUN-04 | 视觉差异 | functional | FUN-03、AST-01 | agent-functional | DONE |
| FUN-05 | 证据采集 | functional | FUN-03、AST-03 | agent-functional | DONE |
| FUN-06 | 功能测试与安全测试 | functional | FUN-02~05 | agent-qa | DONE |

### P3 — Web 前端（补登）

> 2026-11-05 补登：原始需求中的 Vue 3 + Element Plus 前端原先未在任务索引中。规格与任务卡见 `specs/018-frontend/`（`tasks.md` 为任务卡）；依赖 REST API（P0d）。

| ID | 任务 | 模块 | 依赖 | Agent | 状态 |
|---|---|---|---|---|---|
| FE-01 | 应用壳/登录/租户切换/路由守卫/全局错误 | frontend | API-02 | agent-frontend | DONE |
| FE-02 | 项目/数据集/版本/Schema/样本预览 | frontend | FE-01、API-03 | agent-frontend | DONE |
| FE-03 | Run 列表/详情/进度/指标/明细/对比 | frontend | FE-01、API-05 | agent-frontend | DONE |
| FE-04 | 评分器/Suite/Target 配置 | frontend | FE-01、API-04 | agent-frontend | DONE |
| FE-05 | 门禁结果/规则/证据 | frontend | FE-01、API-06 | agent-frontend | DONE |
| FE-06 | 报告/导出/分享链接 | frontend | FE-01、API-06 | agent-frontend | DONE |
| FE-07 | Badcase 语义检索（`degraded` 提示） | frontend | FE-01、API-07 | agent-frontend | DONE |
| FE-08 | 功能测试/视觉差异/证据查看 | frontend | FE-01、API-06、FUN-05 | agent-frontend | DONE |
| FE-09 | 管理面（租户/用户/Key/Provider） | frontend | FE-01、API-08 | agent-frontend | DONE |
| FE-10 | OpenAPI 生成客户端/类型校验/CI | frontend | API-09 | agent-frontend | DONE |
| MGW-06 | 原始响应写入 artifact 并回填 raw_ref | model_gateway | MGW-01 | agent-core | DONE |
| MGW-07 | connect/read/total 三层超时 | model_gateway | MGW-01 | agent-core | DONE |
| EVL-17 | Judge 校准 Cohen's kappa 与 kappa<0.7 门禁 | evaluation | EVL-11 | agent-eval | DONE |
| GAT-06 | Gate 通过率指标与低通过率告警 | gate | GAT-04 | agent-eval | DONE |
| REP-06 | 对比报告导出 JSON/CSV/JUnit | reporting | REP-03 | agent-eval | DONE |
| ING-09 | 同步失败 DLQ 与去重/字段转换 | ingestion | ING-04 | agent-data | DONE |
| ING-10 | 归档文件与 GBK/UTF-8 自动探测 | ingestion | ING-02 | agent-data | DONE |
| ING-11 | OSS/S3 连接器与存储读取 SPI | ingestion | ING-02 | agent-data | DONE |
| FUN-07 | 录屏/trace 证据采集与回放 | functional | FUN-05 | agent-qa | DONE |
| FUN-08 | 超时/失败重跑一次后进 DLQ | functional | FUN-03 | agent-qa | DONE |
| QUAL-06 | 可复现门禁 tests/repro | 跨模块 | QUAL-02 | agent-qa | DONE |
| QUAL-07 | N-1 应用兼容测试 | 跨模块 | QUAL-03 | agent-qa | DONE |
| QUAL-08 | kill switch 接入运行路径 | 跨模块 | QUAL-04 | agent-core | DONE |
| QUAL-09 | 补齐 14 类边界场景矩阵 | 跨模块 | QUAL-05 | agent-qa | DONE |
| QUAL-10 | 四张看板/依赖安全更新/灰度 Runbook | 跨模块 | QUAL-04 | agent-core | DONE |
| API-11 | 写操作审计 actor/action/resource/trace_id | api | API-02 | agent-api | DONE |
| API-12 | datasources CRUD 路由 | api | API-03 | agent-api | DONE |
| API-13 | suites/targets 查询路由 | api | API-04 | agent-api | DONE |
| API-14 | 报告分享链接端点 TTL/越权 | api | API-06 | agent-api | DONE |
| FE-11 | 国际化 zh-CN/en-US 与 UTC 格式化 | frontend | FE-01 | agent-frontend | DONE |
| FE-12 | 可访问性与响应式 | frontend | FE-01 | agent-frontend | DONE |
| FE-13 | 认证加固与 CSP | frontend | FE-01 | agent-frontend | DONE |
| FE-14 | 权限按 scope 隐藏/禁用写操作 | frontend | FE-01、API-02 | agent-frontend | DONE |
| FE-15 | 性能预算与分页/虚拟滚动 | frontend | FE-01 | agent-frontend | DONE |
| FE-16 | 前端可观测与 trace_id 上报 | frontend | FE-01 | agent-frontend | DONE |
| FE-17 | 报告 Markdown/导出 | frontend | FE-06 | agent-frontend | DONE |
| FE-18 | 评分器/Suite/Target 创建编辑 | frontend | FE-04 | agent-frontend | DONE |
| FE-19 | 数据集 Schema/样本预览 | frontend | FE-02 | agent-frontend | DONE |
| FE-20 | Gate 证据表格/失败高亮 | frontend | FE-05 | agent-frontend | DONE |
| FE-21 | 功能测试步骤/截图/视觉差异 | frontend | FE-08 | agent-frontend | DONE |

---

## 6. 状态看板

| 状态 | 数量 | 说明 |
|---|---|---|
| TODO | 0 | 尚未开始 |
| DOING | 0 | 进行中 |
| BLOCKED | 0 | 阻塞 |
| DONE | 173 | 已完成 |

> 任务总数：**173**（原 143 + 收敛新增 30）。

> MCP-01 ~ MCP-15 已完成（**适配器层面**）；`specs/001-mcp-server/tasks.md` 的 T001–T086 已全部完成并通过测试。
>
> **依赖口径**：MCP-10 ~ MCP-15 的 `DONE` 仅表示适配器、契约、测试完成。真实数据依赖 CAT-05、EVL-08/09、GAT-04、SRC-05、REP-02，这些平台任务仍为 `TODO`；生产接入需通过 `PINGCE_MCP_SERVICES_FACTORY` 注入平台只读服务。`search_badcases` / `check_gate` 在依赖未就绪时返回 `UPSTREAM_UNAVAILABLE`，MCP 内不实现检索或门禁逻辑。

> 每完成一个任务，更新对应行状态与本节统计。

---

## 7. 变更规则

- 新增任务：必须写任务卡，并在本文件登记。
- 删除任务：必须说明原因，并检查是否被其他任务依赖。
- 调整依赖：必须检查是否引入环。
- 任务拆分：父任务标记 `DONE` 前必须确认子任务全部完成。
- 状态只能由任务执行者更新；Reviewer 只能标记 `BLOCKED`。
