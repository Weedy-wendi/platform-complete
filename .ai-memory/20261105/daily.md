# 2026-11-05

## [12:32] - 技术选型定案: Pingce 技术栈与硬约束入宪

- **文件**: `.specify/memory/constitution.md`
- **决策**:
  - 元数据库：MySQL 8.0 系列最新补丁（放弃 PostgreSQL）
  - 队列/缓存：Redis 7.x（放弃 RabbitMQ；已写入 broker 独立实例、AOF、noeviction、visibility_timeout=6h、幂等键、DLQ 等护栏）
  - 后端：FastAPI + SQLAlchemy 2.0 同步 + PyMySQL + Alembic（控制面禁用 async ORM）
  - 前端：Vue 3.5 + TypeScript strict + Vite + Element Plus + Pinia + Vue Query + ECharts + vxe-table + Vue Flow
  - 对象存储：云 OSS（S3 兼容抽象），私有化降级 MinIO，禁止单机 MinIO 作生产唯一存储
  - 语义检索：Qdrant（Apache 2.0），禁止在 MySQL 存向量
  - 模型网关：LiteLLM 独立进程
- **关键补充**: MySQL 无 RLS，租户隔离改由 Repository 层强制 + 跨租户越权测试门禁
- **验证**: 全文无模板占位符（grep 校验）；章节结构与 `.specify/templates/constitution-template.md` 对齐；文件 286 行 / 9889 字符，UTF-8 中文正常

## [13:19] - 规范沉淀: 新增「MCP 接入约束」章节并升版 1.1.0

- **文件**: `.specify/memory/constitution.md`
- **变更**: 新增 8 小节（定位与边界、传输与部署、工具面、长任务、认证与租户、安全、可观测与版本、阶段门槛）
- **决策**:
  - MCP 定位为第 5 接入层适配器，禁止实现业务逻辑、生产形态禁止直连 DB
  - 传输：stdio（个人 IDE + API Key）与 Streamable HTTP（团队/远程 + OAuth 2.1）共用一套工具注册表
  - 落地顺序：stdio 只读 → HTTP 只读 → HTTP 写操作
  - 写操作强制：幂等键、scope、审计、dry_run/二次确认、配额熔断
  - 禁止暴露：任意 SQL、任意 URL 抓取、代码执行、不可逆删除、全量导出
- **验证**: 章节插入位置在「技术栈硬约束」与「安全与合规硬约束」之间；版本行已改为 1.1.0；全文无模板占位符；最终 356 行 / 12371 字符，UTF-8 中文正常

## [13:31] - 文档交付: MCP 只读 HTTP 接入文档集 + 宪法 1.2.0

- **文件**:
  - `docs/adr/ADR-005-mcp-access-layer.md`
  - `specs/001-mcp-server/spec.md`
  - `specs/001-mcp-server/plan.md`
  - `specs/001-mcp-server/research.md`
  - `specs/001-mcp-server/data-model.md`
  - `specs/001-mcp-server/quickstart.md`
  - `specs/001-mcp-server/tasks.md`
  - `specs/001-mcp-server/contracts/tools.yaml`
  - `specs/001-mcp-server/contracts/errors.md`
  - `.specify/memory/constitution.md`（1.1.0 → 1.2.0）
- **决策**:
  - 传输：仅 Streamable HTTP；stdio 未批准
  - 范围：只读 10 个工具；禁止注册写工具
  - 认证：API Key（HMAC-SHA256 + pepper）；OAuth 2.1 通过 `AuthProvider` 预留
  - 数据访问：独立进程 + 受限 DB 账号（业务表 SELECT + 审计表 INSERT）
  - 部署：`/mcp`，TLS，双层限流，64KB 结果上限，审计 append-only
- **验证**: `tools.yaml` YAML 解析通过，10 个工具且全部 `readOnlyHint=true`；3 个 Resource；宪法无模板占位符；版本 1.2.0

## [14:33] - 文档交付: 模块化开发、101 任务拆解与子 Agent 协议

- **文件**:
  - `docs/README.md`
  - `docs/architecture/module-map.md`
  - `docs/architecture/module-conventions.md`
  - `docs/planning/subagent-protocol.md`
  - `docs/planning/task-index.md`
  - `docs/planning/tasks/00-foundation.md`
  - `docs/planning/tasks/01-data.md`
  - `docs/planning/tasks/02-evaluation.md`
  - `docs/planning/tasks/03-functional.md`
  - `docs/planning/tasks/04-mcp.md`
  - `specs/001-mcp-server/tasks.md`（增加权威任务卡映射）
  - `.specify/memory/constitution.md`（1.2.0 → 1.3.0）
- **决策**:
  - 15 个模块（core/identity/audit/assets/observability/catalog/ingestion/search/evaluation/jobs/model_gateway/gate/reporting/functional/mcp）
  - 跨模块只允许 `public.py`；每张表只归一个模块；禁止跨模块 JOIN
  - 101 个任务，分 P0a(26)/P0b(30)/P0c(25)/P1(14)/P2(6)
  - 每个任务含输入/输出/依赖/验收/测试/负责 Agent；12 个关键任务有详细任务卡
  - 子 Agent 统一按 `subagent-protocol.md` 执行：TDD、文件所有权、交付报告、阻塞升级
- **验证**: 任务索引与任务卡 ID 集合完全一致（101/101）；15 个模块全部有任务覆盖；宪法 1.3.0、391 行、无占位符

## [15:08] - 文档交付: 可维护性手册、QUAL 适应度任务、宪法 1.4.0

- **文件**:
  - `docs/architecture/maintainability.md`
  - `docs/planning/tasks/05-quality.md`
  - `docs/planning/task-index.md`（101 → 105 任务，新增 P0q）
  - `docs/README.md`（新增可维护性手册与 QUAL 任务入口）
  - `.specify/memory/constitution.md`（1.3.0 → 1.4.0）
- **决策**:
  - 可维护性三维度：可变更性、可诊断性、可传承性
  - 八机制：契约版本、expand-contract、可复现门禁、适配器 seam、适应度函数、可观测性、发布护栏、技术债预算
  - 四个适应度任务：QUAL-01 架构与契约、QUAL-02 可复现、QUAL-03 数据演进、QUAL-04 运行与迭代
  - 每季度 15–20% 容量还技术债；三个 kill switch（Judge/检索/MCP）
- **验证**: 任务索引与任务卡 ID 集合一致（105/105）；QUAL-01~04 均含输入/输出/依赖/验收/测试/Agent；宪法 1.4.0、467 行、无占位符

## [16:24] - 文档交付: 边界情况分析、QUAL-05 边界测试套件、宪法 1.5.0

- **文件**:
  - `docs/architecture/edge-cases.md`（新增）
  - `docs/planning/tasks/05-quality.md`（新增 QUAL-05）
  - `docs/planning/task-index.md`（105 → 106 任务，P0q 4 → 5）
  - `docs/README.md`（新增边界情况入口，任务数 106）
  - `docs/architecture/maintainability.md`（补充边界适应度函数与链接）
  - `.specify/memory/constitution.md`（1.4.0 → 1.5.0）
- **决策**:
  - 14 类边界：空/单例/上限/重复/并发/部分失败/超时/依赖故障/对抗/生命周期/时间/编码/协议/权限
  - 159 个具体场景（EC-*），每个含期望行为、处理策略、测试、P0–P3 级别
  - 补充状态机非法迁移、并发幂等矩阵、依赖故障矩阵、12 条评审问题
  - 新增 QUAL-05：P0/P1 边界场景 100% 自动化，CI `edge-suite` < 10 分钟
- **验证**: 任务索引与任务卡 ID 一致（106/106）；P0q=5；EC ID 159 个且唯一；宪法 1.5.0、468 行、无占位符

## [16:30] - 文档交付: Agent 接入模型、EVL-13~16、宪法 1.6.0

- **文件**:
  - `docs/architecture/agent-integration.md`（新增）
  - `docs/planning/tasks/02-evaluation.md`（新增 EVL-13~16）
  - `docs/planning/task-index.md`（106 → 110 任务，P0b 30 → 34）
  - `docs/README.md`（新增 Agent 接入入口，任务数 110）
  - `docs/architecture/module-map.md`（evaluation 增加 TargetAdapter/TraceSource，新增 3.5 节）
  - `docs/architecture/maintainability.md`（关联文档补链接）
  - `.specify/memory/constitution.md`（1.5.0 → 1.6.0）
- **决策**:
  - 结论：不需要为每个 Agent 重做系统；只做 TargetAdapter / TraceSource 薄适配
  - 六种接入模式：OpenAI 兼容、HTTP+映射、MCP、OTLP、SDK/CLI、浏览器、批量文件
  - 规范契约：TargetInvocation / AgentResponse / TraceSpan / ContentPart
  - 声明式 Target Config（JSONPath/JMESPath），70% 场景零代码
  - Record/Replay：保存原始响应，换指标不重跑 Agent
  - 所有适配器必须通过同一套 conformance suite
- **验证**: 任务索引与任务卡 ID 一致（110/110）；P0b=34；宪法 1.6.0、469 行、无占位符

## [16:56] - 修复: /speckit.analyze 6 个 HIGH

- **文件**:
  - `.specify/feature.json`（新增，指向 `specs/001-mcp-server`）
  - `specs/001-mcp-server/spec.md`（US4 依赖、FR-011 条件工具说明）
  - `specs/001-mcp-server/plan.md`（MCP 工具实现边界）
  - `specs/001-mcp-server/tasks.md`（执行门禁、T048/T049 重构、T060–T064、Phase 8）
  - `docs/planning/tasks/04-mcp.md`（MCP-07/12/13/14/15 验收补强 + MCP-12 详细卡）
  - `docs/planning/task-index.md`（MCP-12 移到 W5）
- **修复**:
  - G1：`search_badcases` / `check_gate` 改为调用 `SemanticSearch` / `GateReader`，MCP 不实现检索/门禁；依赖未就绪返回 `UPSTREAM_UNAVAILABLE`
  - G2：新增 T060–T062 覆盖 `resources/list` / `resources/read` + 3 个 Resource
  - G3：新增 T063 优雅停机
  - G4：新增 T064 日志与审计脱敏测试
  - C1：`tasks.md` 顶部增加强制任务卡加载门禁
  - I4：`MCP-12` 从 W4 移到 W5，消除与 SRC-05 的顺序矛盾
- **验证**: feature.json 生效；T001–T064 共 64 项；6 个 HIGH 全部关闭；任务索引仍为 110 项；W4 不含 MCP-12、W5 含 MCP-12

## [17:03] - 修复: 清理 8 个 MEDIUM + 复检 0 HIGH

- **文件**:
  - `specs/001-mcp-server/spec.md`（FR-001/008/010/012、Assumptions）
  - `specs/001-mcp-server/plan.md`（OAuth token passthrough、Service+Repository、双 DSN、账号命名）
  - `specs/001-mcp-server/tasks.md`（T025/T026/T027 补强、T065、单一真相）
  - `specs/001-mcp-server/contracts/tools.yaml`（search_badcases/check_gate 增加 UPSTREAM_UNAVAILABLE）
  - `specs/001-mcp-server/contracts/errors.md`（UPSTREAM_UNAVAILABLE 200 / SERVICE_UNAVAILABLE 503）
  - `specs/001-mcp-server/checklists/requirements.md`（新增，17 项全通过）
  - `docs/planning/tasks/04-mcp.md`（MCP-02/04/06 验收补强、单一真相说明）
- **修复**:
  - G5：新增 T065 限流功能测试（三级 + 429 + Retry-After + Redis 兜底）
  - G6：T027 增加吊销 ≤60s 时钟注入断言
  - G7：T025 校验四个 annotation
  - C2：FR-010 增加 aud 校验与拒绝 token passthrough
  - I1：FR-001 区分 MCP 端点与运维端点
  - I2：FR-008 统一为 Service + Repository 双层
  - D1：明确 tasks.md / 04-mcp.md / task-index.md 三层单一真相
  - U1：新增 requirements checklist（17/17）
  - 顺带修复：U2 假设、I3 映射、UPSTREAM/SERVICE 错误码、MCP_AUDIT_DSN、账号命名
- **验证**: T001–T065 共 65 项；40/40 需求有任务；checklist 17/17；YAML 10 工具/3 Resource；复检 0 HIGH / 0 MEDIUM

## [17:23] - 实现: Phase 1–2（T001–T025）

- **文件**:
  - `backend/pyproject.toml`、`backend/app/`（core/identity/audit/mcp/cli）
  - `backend/migrations/`（0001_api_key、0002_mcp_tool_call）
  - `backend/deploy/sql/mcp_grants.sql`
  - `backend/tests/`（core/mcp/identity/contract/integration/security/architecture/migrations）
  - `backend/Dockerfile`、`deploy/compose.yaml`、`deploy/ingress.yaml`
  - `backend/README.md`、`backend/.env.example`
- **实现**:
  - MCP SDK Streamable HTTP 服务：initialize / tools/list / tools/call / resources
  - API Key HMAC 认证 + 60s 缓存 + 吊销；OAuth Resource Server 预留 + metadata 端点
  - 10 只读工具 allowlist、四个 annotations、启动断言、敏感 scope
  - 签名游标、64KB/4KB 限额、PII 脱敏、错误码、审计、三级限流（Redis + 本地兜底）
  - Prometheus 指标、OTel tracer、health/readyz、CLI `pingce mcp serve`
  - Alembic 迁移、受限 DB 账号 SQL、Compose/Ingress、架构测试
- **验证**: 54 tests passed；ruff check/format 通过；mypy 39 files 通过；`pingce mcp serve --help` 可用
- **未完成/待补**: MySQL Docker daemon 未启动，迁移 upgrade/downgrade 与 GRANT 实际验证待补；MCP-07 在任务索引中标记 DOING

## [19:19] - 验证: MySQL 迁移/受限账号/MCP 审计端到端通过

- **文件**:
  - `scripts/verify-mysql.ps1`（新增，Windows PowerShell 5.1 兼容）
  - `backend/README.md`（补充验证命令与数据目录说明）
  - `.gitignore`（新增 `.local/`）
  - `docs/planning/task-index.md`（MCP-07 → DONE；DONE 9 / DOING 0）
  - `specs/001-mcp-server/tasks.md`（T001–T025 全部完成；集成说明更新）
- **验证结果**:
  - MySQL data bind mount: `E:\WORKSPACE\Pingce\.local\mysql-verify`（非 C:，约 211MB）
  - `alembic upgrade head → downgrade -1 → upgrade head` 通过
  - `api_key` / `mcp_tool_call` 表与 `p202611` / `p202612` / `pmax` 分区存在
  - `pingce_mcp_ro`：SELECT 成功；UPDATE/DELETE/CREATE/DROP 全部拒绝
  - `pingce_mcp_audit`：INSERT 成功；SELECT/UPDATE/DELETE 全部拒绝
  - 真实 DB 签发 API Key；MCP 服务 `list_projects` 调用成功并写入 `mcp_tool_call`
  - 脚本默认删除容器、保留数据；`-KeepContainer` / `-CleanData` 可调
- **复检**: 54 tests passed；ruff check/format 通过；mypy 39 files 通过

## [21:30] - 实现: Phase 3–9（T026–T072）

- **服务层**:
  - `backend/app/services/`：`models.py`、`repositories.py`、`projects.py`、`datasets.py`、`evaluation.py`、`badcases.py`、`search.py`、`gate.py`、`__init__.py`
  - `ServiceRegistry` + 内存仓储（测试用）；`SemanticSearch` / `GateReader` 作为外部依赖边界
- **工具层**:
  - `backend/app/mcp/tools/`：`projects.py`、`datasets.py`、`evaluation.py`、`badcases.py`，全部 10 个只读工具接入
  - `backend/app/mcp/pagination.py`、`format.py`；`limits.py` 增加 `fit_mapping`
- **Resources**:
  - `backend/app/mcp/resources/datasets.py`、`reports.py`、`__init__.py`
  - 支持 dataset schema、run summary、run report 三种 URI，并校验 scope
- **限流修复**:
  - 新增 `backend/app/mcp/rate_limit_middleware.py`：HTTP 层 429 + `Retry-After`，支持重工具独立桶
  - `server.py` 中间件顺序：Auth 外层 → RateLimit 内层；优雅停机 `timeout_graceful_shutdown=30`
- **可观测/运维**:
  - `deploy/prometheus/alerts.yaml`（错误率、P95、鉴权失败、审计失败、游标异常、宕机）
  - `docs/security/mcp-security-checklist.md`
  - `scripts/load-mcp.py`（默认 50 QPS × 30 分钟，可短跑）
  - `backend/README.md` 更新工具/资源/压测/告警说明
- **测试**:
  - 新增 contract/security/integration/unit 用例：初始化契约、scope 矩阵、协议版本、只读承诺、OAuth fake provider、结果限额、审计失败、日志脱敏、限流、资源、quickstart、优雅停机
  - `backend/tests/support/seeds.py` + `tests/__init__.py`
- **验证**: 142 tests passed；`ruff check`/`ruff format --check` 通过；`mypy` 58 files 通过
- **任务状态**: `tasks.md` T001–T072 全部 `[X]`；`task-index.md` MCP-01~15 DONE，TODO 95 / DONE 15
- **说明**: `search_badcases` / `check_gate` 不在 MCP 内实现检索/降级/判定；依赖未就绪返回 `UPSTREAM_UNAVAILABLE`

## [22:40] - 收敛: Phase 10（T073–T082）

- **CI**:
  - `.github/workflows/ci.yml`：`ruff`、`ruff format --check`、`mypy`、完整 `pytest`；MySQL service 执行迁移往返与受限 GRANT 校验
- **生产装配**:
  - `app/services/factory.py`：`PINGCE_MCP_SERVICES_FACTORY`（`module:callable`）；生产缺少工厂时启动失败，禁止空内存服务
  - `Settings.mcp_services_factory`；`.env.example`/README 更新
- **CLI 与运维**:
  - `app/cli/main.py` 复用 `server.run()`，保留 30s 优雅停机
  - `app/cli/maintain_partitions.py` + `pingce mcp maintain-partitions`；`docs/runbooks/mcp-partition-maintenance.md`
- **错误与可观测**:
  - `parse_datetime` 非法值转 `INVALID_ARGUMENT`
  - 游标失败递增 `mcp_cursor_invalid_total`
  - 限流中间件增加 413 请求体上限
  - `/readyz` 检查审计 DB
- **数据库**:
  - `create_readonly_engine_from_dsn`：`MAX_EXECUTION_TIME=5000`、`SET SESSION TRANSACTION READ ONLY`、`time_zone='+00:00'`
- **部署**:
  - `deploy/ingress.yaml` 拆分公网 `/mcp` 与内部 `/healthz`、`/readyz`、`/metrics`（IP allowlist）
- **验证**:
  - 160 tests passed；`ruff check`/`format --check` 通过；`mypy` 60 files 通过
  - `verify-mysql.ps1` PASS（含只读会话引擎）
  - 容器 smoke PASS
  - 分区维护 dry-run + apply 在真实 MySQL 上创建 `p202701`/`p202702`
- **任务状态**: `tasks.md` T001–T082 全部 `[X]`

## [23:15] - 收敛: Phase 11（T083–T085）

- **错误契约**:
  - `resources/read` 捕获未预期异常，返回 `INTERNAL` + `trace_id`，不再泄露 `str(e)` 或 `code=0`
- **限流可用性**:
  - `RateLimitMiddleware` 捕获 `ServiceUnavailableError`，返回 HTTP 503 + `Retry-After`
- **依赖可复现**:
  - 新增 `backend/requirements-dev.lock`（pytest/pytest-asyncio/httpx/ruff/mypy/testcontainers）
  - CI `quality` job 与本地 lockfile venv 改用 dev lock；新增 `tests/architecture/test_ci_and_locks.py`
- **验证**:
  - 164 tests passed（本地 + lockfile venv）
  - `ruff check`/`format --check`、`mypy` 60 files 通过
- **任务状态**: `tasks.md` T001–T085 全部 `[X]`

## [23:45] - 收敛: Phase 12（T086）

- **压测工具**:
  - `scripts/load-mcp.py` 增加 `/metrics` 的 `process_resident_memory_bytes` 采集、`--max-memory-growth-pct`、`--max-p95-ms`；超阈值非零退出
  - 新增 `tests/unit/test_load_script.py`（指标解析、metrics URL 推导、百分位）
- **验证**:
  - 167 tests passed；`ruff check`/`format --check`、`mypy` 60 files 通过
  - 本地 5 QPS × 3s 冒烟 PASS；Linux 容器 `/metrics` 确认包含 `process_resident_memory_bytes`
- **任务状态**: `tasks.md` T001–T086 全部 `[X]`

## [23:59] - 文档: 补齐规格与任务索引缺口

- **规格套件**:
  - `specs/README.md`：规格索引 + 14 个模块 → spec/plan/contracts 映射
  - `002-platform-foundation`（core/identity/audit/assets/observability）
  - `003-quality-guardrails`（QUAL）
  - `004-evaluation-core`（catalog/jobs/model_gateway/evaluation）
  - `005-gate-reporting`（gate/reporting）
  - `006-ingestion-search`（ingestion/search）
  - `007-functional-testing`（functional）
  - `008-rest-api`（API-01~10；OpenAPI 3.1 契约）
  - `009-frontend`（FE-01~10；Vue 3 + Element Plus）
- **任务索引**:
  - 110 → **130**：新增 P0d REST API 10 项、P3 前端 10 项
  - 状态：DONE 15 / TODO 115；补充 MCP 适配器依赖口径
- **文档导航**:
  - `docs/README.md` §2 增加规格索引与套件；§5 增加 P0d/P3 与 130/15/115 统计
- **验证**:
  - `specs/008-rest-api/contracts/openapi.yaml` 可解析（OpenAPI 3.1.0，18 paths / 12 schemas）
  - 任务索引行数 130，与阶段汇总一致

## [00:20] - 文档: 规格按模块拆分（002–018）

- **目录**:
  - 14 个模块独立规格：`002-core`、`003-identity`、`004-audit`、`005-assets`、`006-observability`、`007-catalog`、`008-jobs`、`009-model-gateway`、`010-evaluation`、`011-gate`、`012-reporting`、`013-ingestion`、`014-search`、`015-functional`
  - 横向规格：`016-quality-guardrails`、`017-rest-api`、`018-frontend`
- **内容**: 每个模块含 `spec.md` / `plan.md` / `contracts/interfaces.md` / `tasks.md`
- **引用更新**: `specs/README.md`、`docs/README.md`、`docs/planning/task-index.md`
- **说明**: 23:59 条目中的 002–009 阶段套件已被本条目拆分替代；REST/前端改为 017/018

## [00:40] - 实现: 002-core（CORE-01~07）

- **文件**:
  - `backend/app/core/context.py`：`TenantContext` + contextvar（`set/get/reset`、`from_principal`）
  - `backend/app/core/repository.py`：租户过滤 Repository 基类（`scoped/get/list/add`）
  - `backend/app/core/modules.py`：模块枚举
  - `backend/app/core/db.py`：`read_session` / `write_session`
  - `backend/tests/unit/core/`：context、repository、sessions、modules 测试
  - `backend/tests/architecture/test_module_boundaries.py`：新增 import cycle 检测
  - `backend/tests/integration/conftest.py`：testcontainers MySQL/Redis fixtures（opt-in）
- **验证**:
  - 178 passed，2 skipped（testcontainers 默认跳过）
  - `ruff check`、`mypy` 通过
  - `PINGCE_RUN_TESTCONTAINERS=1` 下 MySQL/Redis fixture 通过
- **任务状态**: CORE-01~07 DONE；项目 DONE 22 / TODO 108

## [01:05] - 实现: 002-core 收敛（CORE-08/09）

- **CORE-08 平台读写路由**:
  - `backend/app/core/config.py`：新增 `database_url`、`read_replica_url`、`redis_url`；`read_database_url` 回退；校验 replica 必须配写库
  - `backend/app/core/db.py`：新增 `SessionRegistry`（`from_settings` / `read_session` / `write_session` / `dispose`）与 `get/set/reset_session_registry`
  - `backend/tests/unit/core/test_session_registry.py`：回退写库、读写分离、配置校验、懒加载替换
- **CORE-09 Redis 隔离**:
  - `backend/tests/integration/conftest.py`：新增 `redis_namespace` / `redis_client`，teardown 按前缀清理
  - `backend/tests/integration/core/test_infrastructure_fixtures.py`：namespace 与清理路径冒烟
- **文档**: `backend/README.md`、`docs/README.md`、`specs/README.md`、`docs/planning/task-index.md`
- **验证**: 185 passed / 5 skipped；testcontainers 5 passed；ruff check/format、mypy 通过
- **任务状态**: CORE-01~09 DONE；项目 DONE 24 / TODO 108 / 总数 132

## [01:40] - 实现: 002-core 收敛（CORE-10~13）

- **CORE-10 SQL 日志**:
  - `backend/app/core/db.py`：`install_sql_logging()` 监听 `before_cursor_execute`，记录 SQL 模板、`trace_id`、`tenant_id`，不记录绑定参数；所有 `create_engine_from_dsn` 自动接入
  - `backend/app/core/logging.py`：`JsonFormatter` 输出 `sql` 字段；无 `Principal` 时回退 `TenantContext` 的 tenant/trace
- **CORE-11 import-linter**:
  - `backend/.importlinter`：layers（cli > mcp > services > modules > core）+ modules 禁止 import mcp
  - `.github/workflows/ci.yml`：新增 `lint-imports` 步骤
- **CORE-12 错误码注册表**:
  - `backend/app/core/errors.py`：`ErrorSpec` + `ERROR_CODE_SPECS`（11 个错误码的 HTTP/MCP 映射）+ `get_error_spec`
  - `backend/tests/unit/core/test_errors.py`：自动枚举 `AppError` 子类，校验注册表与映射全覆盖
- **CORE-13 时钟测试**:
  - `backend/tests/unit/core/test_clock.py`：aware/naive UTC 与 `to_iso` 归一化
- **验证**: 205 passed / 5 skipped；`lint-imports` 2 contracts kept；ruff check/format、mypy 通过
- **任务状态**: CORE-01~13 DONE；项目 DONE 28 / TODO 108 / 总数 136

## [02:30] - 实现: 003-identity（IDN-01~06 + AUD-01）

- **IDN-01 模型/迁移**:
  - `backend/app/modules/identity/models.py`：`Tenant`、`User`、`Role`、`Permission`、`UserRole`、`RolePermission`（软删除 + 审计字段）
  - `backend/migrations/versions/0003_identity.py`：建表/索引/唯一约束 + downgrade
  - `backend/app/modules/identity/repository.py`：租户过滤 Repository
- **IDN-02 RBAC**:
  - `backend/app/modules/identity/policies.py`：`AccessPolicy`、`IDENTITY_PERMISSIONS`、默认拒绝、`require_scope/permission`
- **IDN-03 API Key**:
  - `backend/app/modules/identity/api_key.py`：`rotate()`、租户范围 `revoke()`、`get_record()`、记录 `created_by`
- **IDN-04 认证适配**:
  - `backend/app/modules/identity/auth.py`：Bearer 解析、`ApiKeyAuthenticator`、JWT `JwtAuthenticator` 预留、FastAPI 依赖工厂
- **IDN-05 隔离测试**:
  - `backend/tests/security/identity/test_tenant_isolation.py`：跨租户读/写/列表/Key 拒绝
- **IDN-06 审计 + AUD-01**:
  - `backend/app/modules/audit/models.py`：`audit_log`
  - `backend/app/modules/audit/writer.py`：`AuditLogEvent`、`InMemory/SqlAuditLogWriter`、`sanitize_detail`
  - `backend/migrations/versions/0004_audit_log.py`
  - `backend/app/modules/identity/service.py`：租户/用户/角色/Key 用例 + 审计钩子
- **验证**: 237 passed / 8 skipped；testcontainers identity 3 + core 5 通过；ruff check/format、mypy、lint-imports 通过
- **任务状态**: IDN-01~06、AUD-01 DONE；项目 DONE 35 / TODO 101 / 总数 136

## [03:10] - 实现: 003-identity 收敛（IDN-07/08）

- **IDN-07 缓存 TTL**:
  - `backend/app/modules/identity/api_key.py`：`cache_ttl_seconds` 强制 `0 < ttl <= 60`
  - `backend/tests/unit/identity/test_api_key.py`：0/-1/61/3600 拒绝，60 接受
- **IDN-08 软删除唯一性**:
  - `backend/app/modules/identity/repository.py`：新增 `slug_exists` / `email_exists` / `name_exists` / `get_by_code_including_deleted`
  - `backend/app/modules/identity/service.py`：唯一性检查包含软删除记录，返回 `InvalidArgumentError`；软删除 permission 复用并恢复
  - `backend/tests/unit/identity/test_service.py`：软删除用户/租户/角色重建回归测试
- **验证**: 241 passed / 8 skipped；ruff check/format、mypy、lint-imports 通过
- **任务状态**: IDN-01~08、AUD-01 DONE；项目 DONE 37 / TODO 101 / 总数 138

## [03:45] - 实现: 003-identity 收敛（IDN-09/10）

- **IDN-09 租户状态**:
  - `backend/app/modules/identity/tenant_status.py`：`TenantStatusChecker` + `SqlTenantStatusChecker`（TTL ≤60s、可失效）
  - `backend/app/modules/identity/api_key.py`：`verify()` / `issue()` 校验租户 active；支持注入 checker
  - `backend/app/modules/identity/auth.py`：`ApiKeyAuthenticator` 可校验租户状态
  - `backend/app/modules/identity/service.py`：`set_tenant_status()`；所有租户级用例校验租户 active/未删除
  - 测试：禁用租户 Key 401、管理操作拒绝、重新启用恢复
- **IDN-10 契约对齐**:
  - `backend/app/core/context.py`：`Principal.auth_method` 支持 `api_key` / `oauth` / `jwt`
  - `backend/tests/unit/core/test_context.py`：JWT Principal 类型测试
- **验证**: 243 passed / 8 skipped；testcontainers identity 3 passed；ruff check/format、mypy、lint-imports 通过
- **任务状态**: IDN-01~10、AUD-01 DONE；项目 DONE 39 / TODO 101 / 总数 140

## [04:20] - 实现: 003-identity 收敛（IDN-11~13）

- **IDN-11 MCP 租户状态**:
  - `backend/app/modules/identity/tenant_status.py`：`SqlTenantStatusChecker` 新增 `allow_missing`（legacy MCP key 兼容）
  - `backend/app/mcp/server.py`：`_build_api_key_service` 注入 tenant status checker（`allow_missing=True`）
  - `backend/tests/unit/mcp/test_auth_api_key.py`：禁用租户 MCP 认证拒绝
- **IDN-12 JWT 预留**:
  - `backend/app/modules/identity/auth.py`：`JwtAuthenticator` 支持注入 verifier，配置后可返回 `Principal(auth_method="jwt")`
  - `backend/tests/unit/identity/test_auth.py`：配置/未配置两种路径
- **IDN-13 软删除租户**:
  - `backend/tests/unit/identity/test_service.py`：`tenant.deleted_at` 后 Key 401、管理操作 NotFound
  - `backend/tests/unit/identity/test_tenant_status.py`：checker 的 active/disabled/deleted/missing 行为
- **验证**: 248 passed / 8 skipped；testcontainers identity 3 passed；ruff check/format、mypy、lint-imports 通过
- **任务状态**: IDN-01~13、AUD-01 DONE；项目 DONE 42 / TODO 101 / 总数 143

## [05:30] - 实现: 004-audit（AUD-02/03）

- `backend/app/modules/audit/reader.py`：`AuditReader`、`SqlAuditReader`、`InMemoryAuditReader`；租户过滤、actor/resource/since、keyset 分页
- `backend/app/modules/audit/models.py`：`audit_log` 复合主键 `(id, created_at)`
- `backend/migrations/versions/0005_audit_partitions.py`：按月 RANGE 分区 + downgrade
- `backend/app/cli/maintain_partitions.py`：`--table` 支持；`app/cli/main.py` 新增 `audit maintain-partitions`（180 天）
- `backend/app/modules/audit/writer.py`：`SafeAuditLogWriter` + `audit_write_failed_total`
- 测试：reader/retention/grants/partition；MySQL 容器验证通过
- **任务状态**: AUD-01~03 DONE；项目 DONE 44 / TODO 99 / 总数 143

## [06:00] - 实现: 005-assets（AST-01~05）

- `backend/app/modules/assets/storage.py`：`Storage` SPI、key 规范、TTL/校验
- `backend/app/modules/assets/local.py`、`s3.py`、`factory.py`：LocalStorage、OSS/MinIO S3 适配、懒加载 boto3、path-style
- `backend/app/modules/assets/models.py` + `service.py`：`artifact` 元数据、`ArtifactService`（create/get/get_bytes/presign/delete）
- `backend/migrations/versions/0006_artifact.py`
- 测试：storage contract（local/fake/OSS/MinIO）、artifact service、跨租户、配置校验；MySQL 迁移验证
- 修复：重复 key 不再覆盖/删除已有对象；MinIO path-style 配置
- **任务状态**: AST-01~05 DONE；项目 DONE 49 / TODO 94 / 总数 143

## [06:40] - 实现: 006-observability（OBS-01~05）

- `backend/app/core/logging.py`：Prompt/样本等敏感字段脱敏、`redact_payload`
- `backend/app/core/tracing.py`：采样率、OTLP exporter（可选）、FastAPI/Celery instrumentation、`flush_tracing`
- `backend/app/core/metrics.py`：HTTP、队列、Job 失败、模型调用/成本、readiness 指标
- `backend/app/core/health.py`：DB/Redis/对象存储检查、liveness/readiness、失败指标
- `backend/app/modules/assets/*`：Storage `healthcheck`
- `deploy/prometheus/alerts.yaml`：平台错误率/P95/队列/成本/审计/依赖告警
- 测试：observability、health、metrics、alerts；全量通过
- **任务状态**: OBS-01~05 DONE；P0a 完成；项目 DONE 54 / TODO 89 / 总数 143


## [23:30] - ??: 009-018 ?????????
- ? `/speckit.converge` ?? 009-018????????????
  - 009 MGW-06?provider ??????? artifact?raw_ref ???
  - 010 EVL-17?Judge ???????????? Cohen's kappa ? ?<0.7 ??
  - 011 GAT-06?Gate ??????
  - 012 REP-06??????? JSON/CSV/JUnit ??
  - 013 ING-09????? DLQ?????/????
  - 015 FUN-07???????/console/network????/trace
  - 016 QUAL-06~09?? tests/repro?N-1 ???kill switch ???????14 ????????
  - 017 API-11?REST ???????
  - 018 FE-11~16??????????????????????????????
- 014-search ???????????
- ??????? 160 ??143 DONE + 17 ?? TODO???? 1.1.1?
- MCP ??????? `KILL_SWITCHES.require("mcp")`?QUAL-08 ?????
