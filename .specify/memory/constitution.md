# Pingce 项目宪法（Project Constitution）

> 面向研发团队的 AI 质量基础设施：把 AI 应用的输入数据、输出结果、评测标准统一资产化，让「这次改动到底变好还是变坏」变成一条可复现、可门禁、可下钻的命令。
>
> 本宪法是技术决策的最高约束。任何实现、依赖、迁移、发布与本文件冲突时，以本文件为准；确需偏离的，必须在 PR 中附 ADR 豁免记录。

## Core Principles

### I. 可复现优先（Reproducibility First）— NON-NEGOTIABLE

任何一次 Run 必须能由 Manifest 完整重放，否则结果不得作为门禁依据。

- 数据集版本、评分器版本、Rubric 版本一经发布即不可变，只能新建版本。
- 每次 Run 必须持久化完整 Manifest：`dataset_hash`、`evaluator_versions[]`、`metric_configs`、`target_config`（model / temperature / seed / prompt_version）、采样策略与 seed、`code_version`、运行环境。
- 复现方式统一为「按 `manifest_hash` 重跑」，禁止依赖人工记忆或聊天记录还原。
- 规则类指标重跑必须 100% 一致；Judge 类指标同模型同版本重跑分数差必须可解释且有阈值。

### II. 五原语内核（Asset / Version / Run / Evidence / Gate）

数据中台、评测中台、可视化功能测试三个功能面共用同一套内核，禁止各自复制权限、审计、存储与任务体系。

- 任何新功能必须落到五原语之一，落不进去说明抽象错了，先改抽象再加功能。
- 模块之间只能通过 service 接口或领域事件通信，禁止跨模块直接查表。
- 三个功能面共享同一套 RBAC、审计日志、对象存储、任务队列、报告引擎。

### III. 程序员优先（API / CLI First）

目标用户是程序员，UI 是可视化补充，不是唯一入口。

- 任何 UI 能力必须先在 API 暴露；UI 不得拥有 API 没有的能力。
- CLI 必须可进 CI：稳定退出码、JUnit/JSON 报告、可配置失败阈值。
- OpenAPI 3.1 是前后端唯一契约；前端类型必须由 `openapi-typescript` 生成，禁止手写重复类型。
- 所有长任务遵循 `202 Accepted + run_id + 轮询/SSE` 模式，禁止同步阻塞等待。

### IV. 稳定优先于性能（Boring Technology）

性能优化必须有基线；没有测量数据的优化一律拒绝。

- 只用 LTS / 长支持版本，禁止生产使用创新版、RC、非 LTS。
- 组件数量最小化：每增加一个中间件，必须说明它替代了什么、故障时如何降级。
- 关键路径同步化：控制面数据库访问使用同步驱动；异步只用于确实的 IO 并发。
- 每个外部调用必须有 connect / read / total 三层超时，禁止无限等待。
- 依赖版本必须锁定（lockfile + 镜像 digest），禁止浮动版本上生产。

### V. 控制面与执行面分离（Control Plane / Data Plane）

API 只写元数据、投递任务、返回 202；所有长任务在 Worker 执行。

- 控制面不得执行不可信代码，不得承载超过 30 秒的同步任务。
- 用户自定义 Evaluator、Connector、浏览器脚本必须在沙箱执行：资源限制、网络白名单、超时强杀、只读挂载。
- Worker 可独立扩缩容；浏览器测试必须使用独立 Worker 池，避免内存泄漏拖垮评测任务。

### VI. 证据驱动交付（Evidence Over Claims）

无证据 = 未完成。

- 每个功能必须附带：测试结果、可观测指标、失败路径验证。
- 每个迁移必须附带：回滚脚本、备份确认、影响行数评估。
- 每个性能声明必须附带：基线数据、测量方法、复现命令。
- Bug 修复必须先复现失败，修复后把失败用例转为回归测试留仓。

### VII. 模块化单体（Modular Monolith）

MVP 阶段单仓、单部署单元、清晰模块边界；禁止提前拆微服务。

- 允许的进程拆分仅有：`api`、`worker-*`、`scheduler`、`gateway`。
- 撤销条件（满足任一才重新评估）：团队 > 15 人；某模块有独立发布节奏；单模块出现无法通过水平扩展解决的瓶颈。

---

## 模块化开发与任务执行（Modular Development & Task Execution）

### 1. 模块边界

- 模块划分以 `docs/architecture/module-map.md` 为唯一真相；新增/调整模块必须先提 ADR。
- 每个模块必须有：负责人 Agent、`public.py`、拥有的表、README、测试目录。
- 跨模块只允许 import `public.py`；禁止 import 其他模块的 `models` / `repository` / `service`。
- 每张表只属于一个模块；禁止跨模块 JOIN；跨域报表必须使用 `reporting` 拥有的读模型。
- 模块内强一致，模块间最终一致；跨模块副作用必须走 Outbox + 幂等消费者。

### 2. 任务卡

- 任何任务开工前必须有任务卡，至少包含：ID、模块/阶段、负责 Agent、目标、输入、输出、依赖、验收条件、测试用例、执行步骤、禁止事项、验证命令、完成定义。
- 无任务卡的任务不得进入实现；任务卡缺失字段视为未就绪。
- 任务状态以 `docs/planning/task-index.md` 为唯一真相；完成必须附验证证据。
- 任务卡明细位于 `docs/planning/tasks/`；通用执行流程见 `docs/planning/subagent-protocol.md`。

### 3. 子 Agent 执行

- 子 Agent 必须按 `subagent-protocol.md` 执行：加载上下文 → 校验依赖 → 建工作区 → 先写失败测试 → 最小实现 → 验证 → 自审 → 交付报告 → 更新状态。
- 同一模块同一时间只允许一个实现 Agent 修改；跨模块改动必须拆任务。
- 禁止为了让测试通过而删除测试、放宽断言、吞异常、去掉租户过滤。
- 同一测试连续失败 2 次必须停止并列出 2–3 个方案与推荐项，不得无限试错。

### 4. CI 硬门禁

- 架构测试必须阻止跨模块内部 import、循环依赖、业务模块 import `app.api`。
- 契约测试必须校验 `public.py`、OpenAPI、MCP `tools/list` 与契约文件一致。
- 迁移必须验证 upgrade → downgrade → upgrade。
- 核心域覆盖率 ≥ 85%，其他模块 ≥ 70%。
- 跨租户越权测试必须作为合并门禁。

---

## 可维护性与迭代（Maintainability & Iteration）

### 1. 判据

- **可维护 = 改得动、看得清、接得住；可迭代 = 反馈环短、兼容策略清楚、回滚有路。**
- 可维护性是预算，不是阶段：每季度至少预留 15–20% 容量用于还债。
- 评测平台的第一可维护性是「可复现」；结果不可复现，其他优化没有意义。

### 2. 契约与版本

- 模块间契约以 `public.py` 为准；只增不改，破坏性变更必须 ADR。
- HTTP API 在 `/v1` 内向后兼容；旧版至少保留 2 个 minor。
- MCP 工具契约只增工具、不改语义；提前 1 个 minor 公告，保留 2 个 minor。
- Agent 接入必须通过 `TargetAdapter` / `TraceSource` 适配器与声明式配置；禁止为单个 Agent 修改评测核心或复制评测逻辑。
- 前端类型、MCP Schema、测试夹具必须从契约生成，禁止手写镜像。

### 3. 数据演进

- 数据库变更必须遵循 expand-contract：加字段先 nullable，删字段先停写。
- 应用必须兼容 N-1 schema；滚动发布期间新旧版本都能运行。
- 一个迁移一个 DDL；必须提供 `downgrade()`；不可逆迁移必须附数据快照方案。
- 迁移必须通过 `up → down → up`；每季度至少一次真实恢复演练。

### 4. 可复现门禁

- 同一 Manifest 重放 5 次，规则指标必须 100% 一致。
- Judge 同模型同版本重放，分数差 ≤ 0.05；Judge 与人工一致率 κ ≥ 0.7 才可进门禁。
- 数据集版本、评分器版本、Rubric 版本、模型版本一律 pinning 且不可变。
- 任何「分数变化」必须能归因到某个版本变化，否则不得合并。

### 5. 适应度函数

以下检查必须进入 CI，失败即阻断合并：

- 模块边界：`import-linter` + 跨模块 import 只允许 `.public`。
- 契约一致：`public.py`、OpenAPI、MCP `tools/list` 与契约文件一致。
- 可复现：Manifest 重放。
- 迁移可回滚：`up/down/up`。
- 租户隔离：跨租户读写导出测试。
- 性能与成本：benchmark 基线、单 Run 预算。
- 安全：依赖 CVE 扫描。
- 文档：链接检查、任务卡字段完整性。
- 边界与异常路径：P0/P1 场景必须有自动化用例（见 `docs/architecture/edge-cases.md`）。

### 6. 发布与回滚

- 新功能默认关闭；必须提供 Judge、语义检索、MCP 三个 kill switch。
- 发布默认渐进式：内部 → 10% → 全量；每步有观察窗口。
- 回滚脚本必须预写并每季度演练；无回滚方案不得发布。
- 数据库变更与应用发布解耦，禁止把不可逆 DDL 和业务发布绑在一起。

### 7. 技术债与依赖

- 技术债必须有账本：问题、影响、利息、触发条件、主人、到期时间。
- 依赖必须锁定版本；高危 CVE 阻断合并；升级 PR 自动化。
- 新增抽象必须 ADR；禁止「先写一套，后面再统一」。

### 8. 文档与决策

- ADR 一旦接受不可修改，只能新增 superseding ADR。
- 模块 README 必须与代码同 PR 更新；文档过期视为缺陷。
- 任务卡是规格：无输入/输出/依赖/验收/测试/Agent 的任务不得开工。

### 9. 红线

- 评测结果不绑定 Manifest。
- 线上直接改 Judge Prompt / Rubric 不升版本。
- 数据集版本原地更新。
- 跨模块直接 JOIN 或 import 内部实现。
- 迁移不可回滚且无快照。
- 测试依赖真实 LLM / 真实 OSS。
- 日志包含完整 Prompt、样本、密钥。
- 契约无版本、无弃用周期。
- 用覆盖率代替行为验证。
- 模块没有 owner。

---

## 技术栈硬约束（Technology Constraints）

### 技术栈总表

| 层 | 选型 | 版本策略 | 禁止项 |
|---|---|---|---|
| 语言 | Python | 3.12+ | 3.9 及以下 |
| Web 框架 | FastAPI + Pydantic v2 | 锁定 minor | 控制面使用 async ORM |
| ORM / 迁移 | SQLAlchemy 2.0（同步）+ PyMySQL + Alembic | 锁定 minor | asyncmy / 全异步 Session |
| 元数据库 | MySQL | 8.0 系列最新补丁（≥ 8.0.40） | 5.7、9.x 创新版 |
| 队列 / 缓存 | Redis | 7.x（自用）；商业分发前评估 Valkey | 单实例混用 broker 与 cache |
| 任务框架 | Celery | 5.x | 使用 Redis result backend 存大结果 |
| 对象存储 | 云 OSS（S3 兼容） | 托管服务 | 业务代码直连厂商 SDK |
| 语义检索 | Qdrant | 最新稳定版 | 在 MySQL 中存向量 |
| 模型网关 | LiteLLM（独立进程） | 锁定版本 | 业务代码直连 Provider SDK |
| 前端 | Vue 3 + TypeScript + Vite | TS `strict: true` | 关闭 strict、fork Element Plus |
| UI 组件 | Element Plus | 锁定 minor | 直接改 `node_modules` |
| 图表 / 大表格 | ECharts + vxe-table | 锁定 major | 未虚拟化的万行表格 |
| 流程图 | Vue Flow 或 LogicFlow（二选一） | 锁定 major | 同时引入两套图引擎 |
| 可观测 | OpenTelemetry + Prometheus + Grafana + Loki | — | 无 trace_id 的日志 |
| 部署 | Docker Compose（单机）/ Helm（可选） | 镜像锁 digest | MVP 强依赖 K8s |

### 1. 后端：FastAPI

- Python 3.12+；使用 `pyproject.toml` + `uv` 或 `pip-tools` 锁定依赖。
- **控制面数据库访问一律同步**：SQLAlchemy 2.0 + PyMySQL；CRUD 端点使用 `def`（FastAPI 自动走线程池）。
- `async def` 仅用于：SSE 流式输出、纯网络转发、无数据库事务的聚合读取。
- Worker 内调用模型/外部服务使用 `httpx.AsyncClient`，必须显式设置 `timeout=httpx.Timeout(...)`。
- 所有请求必须携带 `tenant_id` 上下文，由依赖注入统一解析，禁止从请求体读取租户。
- 统一异常模型：`code` / `message` / `trace_id` / `details`；禁止把堆栈返回给客户端。
- OpenAPI 3.1 必须可导出，作为前端类型生成与契约测试的唯一来源。

### 2. 数据库：MySQL 8.0

版本与基础配置：

1. **版本**：MySQL 8.0 系列最新补丁（≥ 8.0.40）。禁止 5.7（已 EOL）、禁止 9.x 创新版。
2. **字符集**：全库 `utf8mb4` + `utf8mb4_0900_ai_ci`；ID、邮箱、API Key 等唯一键列使用 `utf8mb4_0900_as_cs` 或 `utf8mb4_bin`，避免大小写撞键。
3. **时间**：统一 UTC，使用 `DATETIME(6)`；禁止 `TIMESTAMP`（时区与 2038 问题）。
4. **sql_mode**：显式设置为 `STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO`，禁止依赖默认宽松模式。
5. **隔离级别**：`READ COMMITTED`，降低间隙锁与死锁概率。
6. **事务**：事务内禁止调用外部 API；单事务时长目标 < 100ms，硬上限 1s。
7. **外键**：高频写入表（`run_item`、`score`、`trace_span`、`judge_call`）禁止外键，改由应用层保证 + 每日对账任务。
8. **分区**：`run_item` 等明细表按 `tenant_id` HASH 或按月 RANGE 分区；主键使用包含分区键的复合键 `(tenant_id, id)`；分区表不建外键。
9. **JSON**：仅存展示型、低频字段；需要查询/排序/聚合的字段必须抽为 STORED 生成列并建索引，禁止对 JSON 做深层次全表扫描。
10. **迁移**：一次迁移一个 DDL；大表使用 `ALGORITHM=INPLACE, LOCK=NONE` 或 gh-ost；上线前必备份 + 回滚脚本；禁止业务高峰执行。
11. **连接**：连接池启用 `pool_pre_ping=True`、`pool_recycle < wait_timeout`；`max_allowed_packet ≥ 64MB`。
12. **观测**：开启慢查询日志；核心 SQL 走 `performance_schema`；报表与导出走只读副本，禁止打主库。

**租户隔离（重要）**：MySQL 不提供 Row-Level Security。租户隔离必须在数据访问层强制完成：

- 所有业务表必须含 `tenant_id` 且建索引。
- 统一 Repository 基类自动注入 `tenant_id` 过滤，禁止业务代码手写跨租户查询。
- 必须存在自动化「跨租户越权」测试套件，覆盖读、写、导出、下载四类操作。

### 3. 队列与缓存：Redis + Celery

**Redis 同时承担 Celery broker 与缓存，必须用两个独立实例（不同 DB index 不足以隔离淘汰策略）。**

broker 实例硬性配置：

- 持久化：`appendonly yes` + `appendfsync everysec`；RDB 作为补充。
- 淘汰策略：`maxmemory-policy noeviction`；容量水位告警阈值 70%。
- 高可用：主从 + Sentinel（MVP 不上 Cluster）；禁止单点无副本。
- 监控：队列深度 `LLEN`、内存、`evicted_keys`、`blocked_clients`、`connected_clients`。

Celery 硬性配置：

- `task_acks_late = True`、`task_reject_on_worker_lost = True`、`worker_prefetch_multiplier = 1`。
- `broker_transport_options = {"visibility_timeout": <最长任务时长 × 1.5>}`；当前硬约束为 **6 小时**（与单 Run 上限对齐），变更任务上限必须同步修改此值。
- **所有任务必须幂等**：以 `idempotency_key = hash(run_id, item_id, attempt)` 建唯一索引；重复投递不得产生重复计费或重复写入。
- 结果不写 Celery result backend；统一写 MySQL 元数据 + 对象存储，Redis 只存短 TTL 的进度快照。
- 重试：指数退避 + 抖动，最多 3 次；区分「被测方错误」与「平台错误」，后者不计入质量统计。
- 死信：超过重试上限写入 `dead_letter_task` 表并告警，提供 CLI 人工重放；禁止静默丢弃。
- 调度器必须单例：使用 MySQL `GET_LOCK()` 做 leader election，或单副本 + 存活告警。

cache 实例：

- `maxmemory-policy allkeys-lru`；只缓存可重建数据，禁止存唯一副本。
- 缓存 key 必须带租户前缀与版本号；禁止缓存跨租户共享的敏感数据。

### 4. 对象存储：云 OSS（S3 兼容）

- 默认使用云 OSS；私有化/离线环境降级为 MinIO，但**单机 MinIO 不得作为生产唯一存储**。
- 业务代码只依赖统一 `Storage` 抽象（S3 协议），禁止直连厂商 SDK；迁移存储不得改业务代码。
- 禁止 public bucket；一律使用预签名 URL，TTL ≤ 15 分钟。
- Key 规范：`tenant/{tenant_id}/{asset_type}/{asset_id}/{version}/{filename}`。
- 写入必须计算并记录 `sha256`；读取时校验完整性。
- 数据集快照、截图、录屏、trace 等大对象**禁止进入 MySQL**；库中只存 `artifact` 引用。
- 必须配置生命周期策略、版本控制、删除保护；生产桶开启服务端加密。

### 5. 语义检索：Qdrant

- 默认 Qdrant（Apache 2.0），通过统一 `VectorIndex` SPI 访问，业务代码不直接依赖客户端。
- **禁止在 MySQL 中存储向量**；MySQL 只存向量元数据与业务外键。
- 每个向量必须记录：`embedding_model`、`embedding_version`、`dim`、`normalized`、`tenant_id`、`source_ref`。
- 切换 embedding 模型必须全量重建索引，采用双写 + 别名切换，禁止原地覆盖。
- 租户隔离：单 collection + `tenant_id` payload 索引 + Repository 层强制过滤；租户数 > 200 时改为 collection-per-tenant。
- Qdrant 不可用时必须降级为关键词检索，禁止阻塞评测主流程。
- payload 最小化：禁止把完整 prompt/输出原文写入向量 payload，只存引用 ID。

### 6. 前端：Vue 3 + Element Plus

- Vue 3.5+ + TypeScript（`strict: true`）+ Vite；CI 必须跑 `vue-tsc --noEmit`。
- 状态：Pinia（全局 UI 状态）+ `@tanstack/vue-query`（服务端状态、缓存、重试）。
- 图表 ECharts（按需引入，实例必须 `dispose()`）；万行表格使用 vxe-table 或虚拟滚动；DAG 编辑使用 Vue Flow 或 LogicFlow，二选一。
- API 类型由 `openapi-typescript` 从 OpenAPI 生成，禁止手写镜像类型。
- 主题定制只允许 CSS 变量；禁止 fork Element Plus 源码或修改 `node_modules`。
- 实时日志优先 SSE；仅在需要双向通信时使用 WebSocket，必须实现指数退避重连。
- 测试：Vitest + Vue Test Utils（单元/组件）、Playwright（关键路径 E2E）。
- 禁止 SSR、禁止微前端、禁止为管理后台引入低代码表单引擎。

### 7. 模型网关：LiteLLM

- 所有模型调用必须经过独立部署的 LiteLLM 网关；业务代码禁止直连 Provider SDK。
- 网关必须配置：超时、重试、限流、熔断、成本统计、Provider 降级。
- API Key 加密存储，日志脱敏；禁止在 trace 中记录完整密钥。
- 每次 Judge 调用必须留痕：模型、版本、prompt hash、输入输出引用、token 数、成本。
- 单 Run 必须设置 token/金额预算上限，超预算暂停并告警。

### 8. 可观测与部署

- 全链路 OpenTelemetry trace；日志为结构化 JSON，必须含 `trace_id`、`tenant_id`、`run_id`（如适用）。
- 核心看板至少四张：队列深度、Run 成功率、单条延迟 P95、Token 成本。
- 健康检查区分 liveness 与 readiness；readiness 必须检查 DB 与队列可用性。
- 支持优雅停机：SIGTERM → 停止取新任务 → 等待 in-flight 完成 → 退出。
- 镜像锁定 digest；配置通过环境变量注入；密钥通过 Secret 管理，禁止入库明文。

---

## MCP 接入约束（MCP Integration Constraints）

### 1. 定位与边界

- MCP 是第 5 个接入层适配器，与 REST、CLI、Webhook 平级；不是新业务系统。
- 禁止在 MCP 层实现业务逻辑；所有工具调用必须落到 Application Service。
- 生产形态下 MCP Server 不得拥有业务写权限；P0 允许通过受限数据库账号（业务表只读 + 审计表仅 INSERT）访问，对外暴露时必须切换为 internal API 且不持有 DB 凭证。
- 一套工具注册表，多传输复用（当前仅 Streamable HTTP；未来如新增 stdio 必须复用同一注册表）；禁止为不同传输复制实现。

### 2. 传输与部署

- **当前批准传输：仅 Streamable HTTP**。独立 `mcp-server` 进程，多租户、集中鉴权与审计；禁止使用已废弃的 HTTP+SSE 传输。
- **stdio 未批准**：如出现离线/本地需求，需先提 ADR，并复用同一工具注册表。
- 生产环境 HTTP 模式必须独立进程部署，禁止挂载在 API 进程或 Worker 上。
- 落地顺序：HTTP 只读（当前）→ OAuth 2.1（P1）→ HTTP 写操作（未批准，需独立威胁建模）；跳级需 ADR 豁免。

### 3. 工具面

- 任务导向，不做 CRUD 镜像；MVP 工具数 ≤ 12。首期固定 10 个只读工具，清单以 `specs/001-mcp-server/contracts/tools.yaml` 为准。
- 工具必须准确标注 `readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint`；禁止错误标注诱导客户端自动批准。
- 禁止暴露：任意 SQL 或查询构造器、任意 URL 抓取、用户代码执行、不可逆删除、全量数据导出。
- 单次工具结果 ≤ 64KB；超出必须游标分页或改走 Resource。
- 报告、schema、大样本集走 `resources/read`，禁止塞进 tool result。
- 工具描述由平台统一版本化管理，租户不可自定义描述。

### 4. 长任务

- 单次工具调用硬超时 ≤ 25 秒，禁止在调用内等待评测完成。
- 长任务必须返回句柄（`run_id`），并提供独立的 status / report 工具。
- 支持 `notifications/progress` 时必须使用客户端传入的 `progressToken`。
- 写操作必须接受 `client_request_id` 并映射为 `idempotency_key`；重试返回同一资源 ID。

### 5. 认证与租户

- **当前模式：HTTP + API Key（Bearer）**。API Key 必须绑定 `tenant_id` 与最小 scope，支持过期与吊销，吊销后 ≤ 60 秒生效。
- **OAuth 2.1 为预留**：必须在对外部客户开放前启用；按 Resource Server 实现，支持 PKCE，校验 `iss` / `aud` / `exp` / `scope`。
- 必须实现 `AuthProvider` 抽象与 `Principal` 模型；业务代码禁止直接读取 `Authorization` 头。
- 禁止 token passthrough：拒绝受众非本服务的 token。
- 复用现有 IdP（OIDC / SAML），禁止自建 Authorization Server。
- OAuth 预留清单（配置开关、metadata 端点、`WWW-Authenticate`、scope 常量）见 `docs/adr/ADR-005-mcp-access-layer.md`，缺一项视为未预留。
- 首期只读 scope：`mcp:projects:read`、`mcp:datasets:read`、`mcp:eval:read`、`mcp:eval:read_content`、`mcp:badcases:read`、`mcp:gate:read`；写 scope 仅预留，不得签发。
- 所有 MCP 请求必须绑定租户；service 层强制过滤，跨租户越权测试为发布门禁。

### 6. 安全

- 默认按不可信客户端设计；MCP 请求等同于外部 API 请求。
- 写操作必须支持 `dry_run` 或二次确认（优先使用 elicitation），禁止静默执行。
- 数据集样本、报告等 Resource 内容视为不可信输入，必须结构化包裹并标记来源。
- 禁止把完整参数、PII、密钥写入日志；只记录 hash、长度、`trace_id`。
- 审计表 `mcp_tool_call` 为 append-only，记录 client / tool / version / status / latency / result_bytes。
- 租户级配额与成本熔断必须存在；单 Run 样本数与金额上限沿用容量约束。

### 7. 可观测与版本

- 每个工具调用必须有 OTel span：`mcp.tool.name`、`mcp.tool.version`、`mcp.client.id`、`mcp.transport`、`tenant.id`。
- 指标至少包含：调用量、错误率、P95 延迟、结果字节数、鉴权失败数、限流次数。
- 工具注册表必须版本化；`inputSchema` 变更必须走契约测试与弃用周期（提前 1 个 minor 公告，保留 2 个 minor）。
- 禁止修改已发布工具的语义；变更通过新增工具或升 major 完成。
- 必须协商 `MCP-Protocol-Version`，不支持的版本返回明确错误。

### 8. 阶段门槛

| 阶段 | 范围 | 准入门槛 |
|---|---|---|
| P0（当前） | HTTP 只读 + API Key + 10 个只读工具 | 跨租户越权测试、DB 授权验证、结果大小上限、只读快照测试全部通过 |
| P1 | OAuth 2.1 接入 IdP | 工具代码零改动；`aud` / `iss` / `exp` / `scope` 校验通过 |
| P2 | 写工具 + 配额 + 确认 | 幂等、审计、预算熔断、`dry_run`、独立威胁建模全部就绪 |
| P3 | Resources / Prompts / progress / elicitation / Sampling | 注入与数据外泄测试通过；独立 ADR |

---

## 安全与合规硬约束（Security & Compliance）

- 认证：JWT（短期）+ API Key（长期，可吊销）；授权：RBAC + 租户边界。
- 租户隔离：MySQL 无 RLS，必须在 Repository 层强制；跨租户越权测试为发布门禁。
- 密钥：数据库只存 `secret_ref`，实际密钥由 KMS 或信封加密管理；日志、错误响应、trace 一律脱敏。
- 沙箱：用户自定义代码在容器内执行，限制 CPU/内存/磁盘/时长，启用网络白名单，超时强杀。
- Prompt 注入：Judge 的输入必须结构化隔离（被测输出放在明确的数据区），输出必须做 Schema 校验；禁止 Judge 执行被测输出中的指令。
- 审计：`audit_log` append-only，记录 actor / action / resource / before / after / trace_id，支持导出。
- 数据不出域：私有化部署必须支持全程不访问公网；Judge 必须可切换为本地模型。
- 依赖供应链：新增依赖必须审查 license、CVE、维护活跃度、lockfile 锁定；禁止引入来源不明的包。
- 合规：如客户要求等保/密评/信创，需单独立项评估，不得默认沿用本宪法。

---

## 容量与性能约束（Capacity & Performance）

| 约束项 | 默认上限 | 超出后的动作 |
|---|---|---|
| 单租户样本量 | 100 万 | 评估分库或归档到 Parquet |
| 单 Run 样本量 | 10 万 | 强制采样或分片执行 |
| 单条 payload | 1 MB | 走对象存储引用 |
| 单 Run 时长 | 6 小时 | 拆分 Run 或异步续跑 |
| API 读 P95 | < 200 ms | 加索引 / 加缓存 / 拆查询 |
| API 写 P95 | < 500 ms | 异步化 / 批量写 |
| 队列积压 | < 10 分钟处理量 | 扩容 Worker + 告警 |
| 明细表行数 | 5,000 万 | 引入 ClickHouse 或列式归档 |

性能声明必须附带基线、测量方法、复现命令；无数据的「优化」不予合入。

---

## 运维与可靠性约束（Operations & Reliability）

- 备份：每日全备 + binlog 增量，支持 PITR；备份与生产异地存放。
- 恢复演练：每季度至少一次真实恢复演练并留存记录；未演练的备份视为不可用。
- 迁移：必须有回滚脚本；不可逆迁移必须先做数据快照并在 PR 中说明。
- 发布：默认渐进式（先内部租户 → 10% → 全量）；回滚脚本预写；发布后观察至少 30 分钟。
- 死信：所有异步任务必须有 DLQ 与人工重放入口。
- 对账：每日核对 Run 统计与明细行数、成本累计、对象存储引用完整性。
- 告警：队列深度、DB 连接数、Redis 内存/淘汰、磁盘水位、P95 延迟、单 Run 成本、失败率。
- 降级开关：Judge 不可用时降级为规则指标；语义检索不可用时降级为关键词；网关不可用时快速失败并给出明确错误码。

---

## 明确不做（Non-Goals）

以下事项在本项目当前阶段明确不做，新增需先修订本宪法：

- 模型训练、微调、推理服务托管
- 人工标注众包平台（仅保留小规模内部复核队列）
- 通用 BI、低代码大屏、报表设计器
- 实时流计算（Flink/Spark Streaming）
- 微服务拆分、服务网格
- MVP 阶段强依赖 Kubernetes
- 在 MySQL 中存储向量
- 单机 MinIO 作为生产唯一存储
- 为单一功能面复制权限/审计/存储体系

---

## 开发流程与质量门禁（Development Workflow & Quality Gates）

1. 流程：Spec → Plan → Tasks → Implement → Verify → Retro。跳过 Spec 的功能不得进入实现。
2. PR 门禁（全部通过才可合并）：
   - `ruff` / `mypy`（或 `pyright`）通过
   - `pytest` 单元 + 集成通过；核心领域覆盖率 ≥ 85%，整体 ≥ 70%
   - OpenAPI 契约测试通过；前端 `vue-tsc --noEmit` 通过
   - 迁移附回滚脚本并本地验证
   - 新增依赖附供应链审查结论
   - 新功能附可观测指标与失败路径测试
3. 禁止直接修改生产配置或手工执行 SQL；一切变更走迁移或配置发布流程。
4. 跨模块改动必须先查依赖影响面，禁止「改一处、崩一片」。
5. 文档：每个模块必须有 README；每个对外 API 必须有 OpenAPI 描述与示例；每个 ADR 必须记录撤销条件。

---

## Governance

- 本宪法优先于任何个人偏好、历史代码与外部模板。
- 修订流程：提出 ADR → 说明动机与影响面 → 更新本文件 → 版本号递增 → 同步受影响的 Spec/Plan。
- 版本语义：MAJOR = 原则或技术栈不兼容变更；MINOR = 新增约束；PATCH = 措辞澄清。
- 例外：任何违反本宪法的实现必须在 PR 中显式标注「宪法豁免」，附原因、风险、补救计划与到期时间；无豁免记录的违例不得合入。
- 审查：每次架构评审、发布评审必须逐条核对本宪法相关章节。

**Version**: 1.6.0 | **Ratified**: 2026-11-05 | **Last Amended**: 2026-11-05
