# Tasks: MCP Server（HTTP 只读接入）

> **权威任务卡**: `docs/planning/tasks/04-mcp.md`（含输入、输出、依赖、验收、测试、负责 Agent）。
> 本文件是 feature 级执行清单；T 级执行状态以本文件为准，项目级 MCP-xx 汇总状态以 `docs/planning/task-index.md` 为准。
>
> **执行门禁（MANDATORY）**: 开工前必须加载 `docs/planning/tasks/04-mcp.md`；每个 T 任务的输入/输出/依赖/验收/测试/负责 Agent 以对应 MCP-xx 卡为准。未加载任务卡不得开工。

**单一真相（Single Source of Truth）**：

- 本文件：feature 级执行清单与 T 状态（T001–T065）。
- `docs/planning/tasks/04-mcp.md`：任务卡字段（输入/输出/依赖/验收/测试/Agent），不维护执行状态。
- `docs/planning/task-index.md`：项目级 MCP-xx 状态汇总，不复制 T 细节。
- 三者通过下方映射表关联；任何任务增删改必须同步映射表。

**任务卡映射**：

| MCP 任务卡 | 对应执行项 |
|---|---|
| MCP-01 模块骨架/配置/CLI | T001–T006 |
| MCP-02 AuthProvider + API Key | T011–T014、T027–T028、T030 |
| MCP-03 OAuth 预留 | T013、T014 |
| MCP-04 工具注册表/allowlist | T018、T025、T053 |
| MCP-05 游标/限额/脱敏 | T015、T016、T037–T039 |
| MCP-06 限流 | T020、T065 |
| MCP-07 审计 | T019、T056、T064 |
| MCP-08 错误/可观测/健康 | T017、T021、T022 |
| MCP-09 协议装配 | T023、T024、T026、T029、T031 |
| MCP-10 数据集工具 | T032–T039 |
| MCP-11 评测工具 | T040–T047 |
| MCP-12 Badcase/Gate 工具 | T048–T051 |
| MCP-13 Resources | T060–T062 |
| MCP-14 安全测试 | T052–T054、T064 |
| MCP-15 压测与部署 | T055、T057–T059、T063 |

**Input**: `specs/001-mcp-server/`（spec.md、plan.md、research.md、data-model.md、contracts/）

**Prerequisites**: plan.md、spec.md、data-model.md、contracts/tools.yaml、contracts/errors.md

**Tests**: 本特性包含契约测试、安全测试、集成测试与压测；测试任务必须先于对应实现完成并确认失败。

**Organization**: 按用户故事分组，支持独立实现与独立验收。

---

## Phase 1: Setup（共享基础设施）

**Purpose**: 建立模块骨架、依赖与部署入口。

- [X] T001 创建模块骨架 `backend/app/mcp/`（server、registry、context、auth、tools、resources、limits、cursor、errors、audit、observability）
- [X] T002 在 `backend/pyproject.toml` 增加并锁定依赖：`mcp`、`starlette`、`uvicorn`、`pydantic`、`redis`、`opentelemetry-sdk`、`prometheus-client`
- [X] T003 新增配置项 `backend/app/core/config.py`：`MCP_AUTH_MODE`、`MCP_API_KEY_PEPPER`、`MCP_CURSOR_SECRET`、`MCP_MAX_RESULT_BYTES`、`MCP_DB_DSN`、`MCP_AUDIT_DSN`、`MCP_RATE_LIMIT_*`
- [X] T004 新增 CLI 入口 `backend/app/cli/mcp.py`：`pingce mcp serve --http --host --port`
- [X] T005 [P] 新增 `deploy/compose.yaml` 的 `mcp-server` 服务与健康检查
- [X] T006 [P] 新增 Ingress 路由 `/mcp`、请求体上限 256KB、TLS 配置

**Checkpoint**: 进程可启动，`/healthz` 可访问。

---

## Phase 2: Foundational（阻塞性前置）

**Purpose**: 认证、授权、限额、审计、错误模型、工具注册表。完成前不能开始任何用户故事。

- [X] T007 新增迁移：`api_key` 表（字段与索引见 `data-model.md`）
- [X] T008 新增迁移：`mcp_tool_call` 表 + 按月分区
- [X] T009 [P] 新增迁移：`pingce_mcp_ro` 与 `pingce_mcp_audit` 账号授权脚本 + 回滚脚本
- [X] T010 [P] 新增测试 `backend/tests/security/test_db_grants.py`：静态校验授权脚本只包含 SELECT / INSERT；`scripts/verify-mysql.ps1` 在真实 MySQL 中验证只读账号无法 UPDATE/DELETE/DDL、审计账号只能 INSERT
- [X] T011 实现 `Principal` 与 `AuthProvider` 协议 `backend/app/mcp/auth/base.py`
- [X] T012 实现 `ApiKeyAuthProvider` `backend/app/mcp/auth/api_key.py`（HMAC 校验、过期/吊销、60s 缓存）
- [X] T013 实现 `OAuthResourceServerProvider` 预留骨架 `backend/app/mcp/auth/oauth_stub.py` + `MCP_AUTH_MODE` 工厂 + 启动校验
- [X] T014 新增 OAuth 预留端点 `/.well-known/oauth-protected-resource`（API Key 模式返回 404）
- [X] T015 [P] 实现签名游标 `backend/app/mcp/cursor.py`（HMAC、TTL、租户/查询指纹校验）
- [X] T016 [P] 实现结果限额与脱敏 `backend/app/mcp/limits.py`（64KB、4KB 截断、PII 规则复用）
- [X] T017 [P] 实现错误模型 `backend/app/mcp/errors.py`（JSON-RPC + 业务码 + `trace_id`）
- [X] T018 实现只读工具 allowlist `backend/app/mcp/registry.py` + 启动断言
- [X] T019 实现审计写入 `backend/app/mcp/audit.py` + `backend/app/modules/audit/writer.py`（独立审计 DSN、失败不阻塞、指标）
- [X] T020 实现 Redis 令牌桶限流 `backend/app/mcp/rate_limit.py`（Key/Tenant/重工具三级 + 本地兜底）
- [X] T021 [P] 实现 OTel / Prometheus `backend/app/core/tracing.py` + `backend/app/core/metrics.py`
- [X] T022 实现 `/healthz` 与 `/readyz`
- [X] T023 装配 MCP Server `backend/app/mcp/server.py`：`initialize`、`notifications/initialized`、`tools/list`
- [X] T024 新增契约测试夹具 `backend/tests/conftest.py`：启动 in-process server、注入 fake Principal
- [X] T025 新增工具契约快照测试 `backend/tests/contract/mcp/test_tools_snapshot.py`：`tools/list` 与 `contracts/tools.yaml` 完全一致，且四个 annotation（`readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint`）全部匹配

**Checkpoint**: 认证、限流、审计、错误、注册表就绪；契约测试可运行。

> 集成说明：T007/T008 的迁移脚本已生成，T009/T010 的授权脚本已生成；已通过 `scripts/verify-mysql.ps1` 验证 `upgrade → downgrade → upgrade`、受限账号拒绝写/DDL、审计账号仅 INSERT，以及 MCP 服务真实写入 `mcp_tool_call`。

---

## Phase 3: User Story 1 — 连接与发现（Priority: P1）🎯 MVP

**Goal**: 任意 MCP 客户端可用 API Key 连接，完成初始化并看到 10 个只读工具。

**Independent Test**: 用 curl 或 MCP Inspector 完成 `initialize` → `notifications/initialized` → `tools/list`。

- [X] T026 [P] [US1] 契约测试：`initialize` 返回协议版本与 capabilities；无状态：不签发/不依赖 `Mcp-Session-Id`，跨请求可路由到任意副本
- [X] T027 [P] [US1] 安全测试：缺失/错误/过期/吊销 Key → 401；吊销后 ≤60 秒内必须失效（可控时钟，不 sleep）
- [X] T028 [P] [US1] 安全测试：scope 不足 → 403
- [X] T029 [P] [US1] 协议测试：不支持的 `MCP-Protocol-Version` → 明确错误
- [X] T030 [US1] 实现 401 的 `WWW-Authenticate` 与 403 的 `required_scope` 输出
- [X] T031 [US1] 用 Claude Code 或 MCP Inspector 走通 quickstart 第 3 节

**Checkpoint**: 连接可用，工具列表正确，认证失败路径完整。

---

## Phase 4: User Story 2 — 数据集探索（Priority: P1）

**Goal**: Agent 能检索项目/数据集、查看 Schema、预览脱敏样本。

**Independent Test**: 调用 `list_projects` → `search_datasets` → `get_dataset_schema` → `preview_samples`，结果符合契约。

- [X] T032 [P] [US2] 实现 `list_projects` `backend/app/mcp/tools/projects.py` + 租户过滤
- [X] T033 [P] [US2] 实现 `search_datasets` `backend/app/mcp/tools/datasets.py`（名称/标签/项目/时间 + 游标）
- [X] T034 [US2] 实现 `get_dataset_schema`（默认最新版本、`content_hash`）
- [X] T035 [US2] 实现 `preview_samples`（≤20 条、单条 ≤4KB、PII 脱敏）
- [X] T036 [P] [US2] 集成测试 `backend/tests/integration/test_datasets_tools.py`
- [X] T037 [P] [US2] 游标测试：篡改/过期/跨租户复用 → `INVALID_CURSOR`
- [X] T038 [P] [US2] 结果限额测试：构造超 64KB 结果 → 截断或 `RESULT_TOO_LARGE`
- [X] T039 [P] [US2] 注入测试：样本含指令文本，断言不触发任何服务端动作

**Checkpoint**: 数据集工具可用，分页、限额、脱敏、注入测试通过。

---

## Phase 5: User Story 3 — 评测结果洞察（Priority: P1）

**Goal**: Agent 能查询 Run、下钻失败样本、对比两次 Run。

**Independent Test**: 使用两次已完成 Run，调用 `get_run`、`get_run_items`、`compare_runs`，结果与 Web 端一致。

- [X] T040 [P] [US3] 实现 `list_evaluators`
- [X] T041 [US3] 实现 `get_run`（状态、进度、manifest_hash、统计、成本）
- [X] T042 [US3] 实现 `get_run_items`（分页、筛选、默认不含 IO）
- [X] T043 [US3] 实现 `include_io` 的 scope 校验（`mcp:eval:read_content`）与脱敏摘录
- [X] T044 [US3] 实现 `compare_runs`（差值、劣化/改善、显著性标记）
- [X] T045 [US3] 读取走只读副本，响应标注 `as_of`
- [X] T046 [P] [US3] 集成测试 `backend/tests/integration/test_eval_tools.py`
- [X] T047 [P] [US3] 一致性测试：MCP 返回与 REST 返回的同一 Run 指标一致

**Checkpoint**: 评测工具可用，IO 权限与一致性测试通过。

---

## Phase 6: User Story 4 — Badcase 与门禁（Priority: P2）

**Goal**: Agent 能检索相似 Badcase、查询门禁结果。

**Independent Test**: 调用 `search_badcases` 与 `check_gate`，结果符合契约。

**Dependency**: `search_badcases` 依赖 `SRC-05`（语义检索/降级）；`check_gate` 依赖 `GAT-04`（门禁结果）。依赖未就绪时返回 `UPSTREAM_UNAVAILABLE`，工具仍保持注册。

- [X] T048 [P] [US4] 实现 `search_badcases`（调用 `search.SemanticSearch`；MCP 内不实现检索/降级；依赖 SRC-05）
- [X] T049 [US4] 实现 `check_gate`（调用 `gate.GateReader`；MCP 内不实现门禁判定；依赖 GAT-04）
- [X] T050 [P] [US4] 降级测试：Qdrant 不可用 → `degraded=true`，不返回 5xx
- [X] T051 [P] [US4] 集成测试 `backend/tests/integration/test_badcase_gate_tools.py`

**Checkpoint**: 全部 10 个只读工具可用（US4 依赖 SRC-05 / GAT-04 就绪）。

---

## Phase 7: Polish & 上线准备

- [X] T052 [P] 跨租户越权测试：读/导出/资源读取三类，全部 403/404 且时序一致
- [X] T053 [P] 只读承诺测试：尝试调用 `start_eval_run` 等写工具 → 工具不存在；DB 层写操作 → 拒绝
- [X] T054 [P] OAuth 切换测试：`MCP_AUTH_MODE=oauth` + fake provider，工具代码零改动
- [X] T055 [P] 压测：50 QPS × 30 分钟，P95 达标、无 5xx、内存增长 <10%
- [X] T056 [P] 审计失败行为测试：审计库不可用时主请求仍成功且告警
- [X] T057 校验 `quickstart.md` 全流程可复现
- [X] T058 新增看板与告警：调用量、错误率、P95、鉴权失败、限流、审计失败
- [X] T059 发布检查：TLS、WAF/IP allowlist、DB 授权、密钥轮换、回滚脚本

---

## Phase 8: Analysis Remediation（体检补强）

**Purpose**: 关闭 `/speckit.analyze` 发现的 HIGH 覆盖缺口。

- [X] T060 [P] [US1] 实现 `resources/list` / `resources/read` 路由与 Schema
- [X] T061 [P] [US2] 注册 3 个 Resource：dataset schema、run summary、run report；校验 scope
- [X] T062 [P] [US2] Resource 读取的租户隔离、大小上限、scope 测试
- [X] T063 [ALL] 优雅停机：SIGTERM → 停止接收新请求 → 等待 in-flight ≤30s → 退出
- [X] T064 [ALL] 日志与审计脱敏测试：断言 Key / 完整 Prompt / 样本正文 / PII 不出现在日志

- [X] T065 [P] [US1] 限流功能测试：Key 120/min、Tenant 600/min、重工具 30/min；超限 429 + `Retry-After`；Redis 故障时本地兜底

**Checkpoint**: 资源、停机、日志脱敏、限流均有自动化证据。

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 → Phase 2 → Phase 3/4/5/6 → Phase 7 → Phase 8
- Phase 2 完成前，任何用户故事不得开始
- Phase 3 是 MVP 门槛；Phase 4/5 可并行；Phase 6 依赖 Phase 5 的 Run 查询能力

### User Story Dependencies

- US1：无依赖
- US2：依赖 US1 的协议与认证
- US3：依赖 US1；与 US2 并行
- US4：依赖 US1；`search_badcases` 依赖 `SRC-05`（P1 语义检索），`check_gate` 依赖 `GAT-04` 与 US3 的 Run 查询

### Parallel Opportunities

- T005/T006、T009/T010、T015/T016/T017、T021、T026–T029、T032/T033、T036–T039、T040、T046/T047、T048/T050、T052–T056、T060–T064 可并行
- US2 与 US3 可由不同开发者并行推进

---

## Implementation Strategy

### MVP First

1. Phase 1 + Phase 2
2. Phase 3（US1）
3. **STOP & VALIDATE**：用真实 IDE 连接，确认 10 个只读工具可见
4. 再进入 Phase 4/5

### Incremental Delivery

1. 连接与发现 → 可演示
2. 数据集工具 → Agent 能理解数据
3. 评测工具 → Agent 能解释结果（核心价值）
4. Badcase/Gate → 闭环
5. 安全与压测 → 可上线

---

## Notes

- [P] = 不同文件、无依赖，可并行
- 所有测试任务必须先确认失败，再实现
- 禁止在 `app/mcp` 中直接写 SQL；统一走 `app/services`
- 禁止注册任何写工具；`registry.py` 启动断言是硬门禁
- 提交前必须跑：契约快照、越权测试、DB 授权测试、`ruff`、`mypy`

---

## Phase 9: Convergence

- [X] T066 [CRITICAL] 为每次 `tools/call` 强制执行 `mcp_tool_timeout_seconds`（默认 25s，`asyncio.wait_for`），超时返回稳定错误码并写审计 per Constitution MCP §4 / plan §1 (missing)
- [X] T067 [CRITICAL] 修复 Compose 初始化与授权：不要用 `MYSQL_USER` 创建具备写权限的 `pingce_mcp_ro`；改用 root 初始化并执行受限 GRANT，审计 DSN 使用 `pingce_mcp_audit`；增加迁移/授权 init job per Constitution MCP §5 / T009-T010 (contradicts)
- [X] T068 [CRITICAL] 增加依赖 lockfile 与镜像 digest 固定（Python 依赖、`python:3.12-slim`、`mysql:8.0`、`redis:7-alpine`），并记录升级流程 per Constitution IV (missing)
- [X] T069 [HIGH] 将 `contracts/tools.yaml` 打入 backend 镜像或在 Compose 中挂载，并增加容器启动 smoke test per plan §11 / T005 (missing)
- [X] T070 [HIGH] 生产模式强制要求 `PINGCE_MCP_DB_DSN` / `PINGCE_MCP_AUDIT_DSN`，禁止 `InMemoryApiKeyStore` 与本地限流兜底 per plan B' / Constitution MCP §5 (partial)
- [X] T071 [HIGH] 为 `resources/list`、`resources/templates/list`、`resources/read` 应用与 tools 相同的 Key/Tenant 限流，并补测试 per FR-020 / plan §8 (partial)
- [X] T072 [MEDIUM] 将 MCP 异步回调中的同步 SQLAlchemy/Redis 调用移出事件循环（线程池或异步客户端），并补并发 smoke test per plan §1 (partial)

---

## Phase 10: Convergence

- [X] T073 [CRITICAL] 增加 CI 流水线并执行宪法硬门禁：架构边界、`tools/list` 契约快照、迁移 `up → down → up`、跨租户测试、`ruff`、`mypy`、完整 `pytest` per Constitution §4 (missing)
- [X] T074 [CRITICAL] 增加生产 `ServiceRegistry` 装配：由只读 DSN 构造平台业务服务并在 `pingce mcp serve` 注入；生产环境缺少真实服务时启动失败，禁止静默使用空内存仓储 per plan Structure Decision / T032–T051 (partial)
- [X] T075 [HIGH] 修复 CLI 优雅停机：`pingce mcp serve` 复用 `server.run()` 或显式传入 `timeout_graceful_shutdown=30`，确保 SIGTERM 后等待 in-flight ≤ 30s per FR-029 / T063 (partial)
- [X] T076 [MEDIUM] `parse_datetime` 捕获非法日期并抛出 `InvalidArgumentError`，避免被映射为可重试的 `INTERNAL`；补非法 `updated_after` 测试 per FR-021 / T033 (partial)
- [X] T077 [MEDIUM] 为业务只读数据库引擎应用会话级保护：`MAX_EXECUTION_TIME=5000`、`SET SESSION TRANSACTION READ ONLY`、`time_zone='+00:00'`；审计引擎保持可写 per plan §4 / data-model §3 / Constitution MySQL (missing)
- [X] T078 [MEDIUM] 在游标校验失败时递增 `mcp_cursor_invalid_total`，使 `McpCursorInvalidSpike` 告警可用，并补测试 per FR-024 / T058 (partial)
- [X] T079 [MEDIUM] 在限流中间件缓冲前执行请求体大小上限（`Content-Length`/累计字节），超限返回 413，避免绕过 SDK 的 256KB 限制 per plan §11 / Constitution IV (missing)
- [X] T080 [MEDIUM] `/readyz` 同时检查审计数据库（暴露 audit engine）与 Redis；任一依赖不可用返回 503 per FR-025 / T019 (partial)
- [X] T081 [MEDIUM] 将 `/metrics`、`/healthz`、`/readyz` 限制到内部 Ingress 或增加 IP allowlist/WAF 配置，避免运维端点公网暴露 per plan §11 (partial)
- [X] T082 [LOW] 增加 `mcp_tool_call` 分区维护脚本/运行手册：按月预建分区并删除 90 天前分区 per data-model §2 (missing)

---

## Phase 11: Convergence

- [X] T083 [MEDIUM] `resources/read` 捕获未预期异常并映射为稳定 `INTERNAL` + `trace_id`，不得把 SDK 的 `code=0` 或内部异常消息返回给客户端 per FR-021 (partial)
- [X] T084 [MEDIUM] 限流中间件捕获 `ServiceUnavailableError` 并返回 HTTP 503（带 `Retry-After`），避免生产环境 Redis/限流依赖故障时返回 500 per plan §8 / T070 (partial)
- [X] T085 [LOW] 增加 `requirements-dev.lock`（pytest/pytest-asyncio/httpx/ruff/mypy/testcontainers），CI 与本地 lockfile venv 使用固定版本 per Constitution IV (partial)

---

## Phase 12: Convergence

- [X] T086 [LOW] `scripts/load-mcp.py` 增加进程内存采集（`/metrics` 的 `process_resident_memory_bytes`）与 `--max-memory-growth-pct`，并输出 P95 是否达标的判定；超阈值时非零退出 per SC-003 / SC-010 / T055 (partial)

