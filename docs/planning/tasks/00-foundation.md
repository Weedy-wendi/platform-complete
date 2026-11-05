# P0a 任务卡：基础设施

**覆盖模块**: M00 core、M01 identity、M02 audit、M03 assets、M14 observability

**负责 Agent**: `agent-core`、`agent-identity`、`agent-data`

**通用协议**: 所有任务按 `docs/planning/subagent-protocol.md` 执行。下表只写任务特有信息。

---

## M00 core

### 模块职责

配置、数据库会话、租户上下文、错误模型、ID/分页/时钟、测试夹具、架构测试。不包含任何业务逻辑。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| CORE-01 | 项目骨架与模块加载 | `module-map.md`、`module-conventions.md` | `backend/app/core/`、`backend/app/modules/`、`pyproject.toml`、ruff/mypy 配置、模块注册表 | — | `import app` 成功；模块可枚举；无循环依赖 | UT：模块注册；架构：无环 | agent-core |
| CORE-02 | 配置与密钥管理 | 宪法安全条款、`.env.example` | `app/core/config.py`、Secret 加载器、启动校验 | CORE-01 | 缺必填配置启动失败；密钥不入日志；支持环境覆盖 | UT：校验；安全：脱敏 | agent-core |
| CORE-03 | DB 会话与租户上下文 | `module-map.md`、宪法 MySQL 规则 | `app/core/db.py`、`TenantContext`、`UnitOfWork`、读写会话工厂 | CORE-01/02 | 无租户请求被拒；会话必关闭；查询强制租户过滤；支持只读副本 | UT：上下文；IT：回滚；安全：跨租户 | agent-core |
| CORE-04 | 错误模型与错误码 | 宪法、`contracts/errors.md` | `app/core/errors.py`、错误码注册表 | CORE-01 | 领域异常可映射 HTTP 与 MCP；不泄露堆栈 | UT：映射表全覆盖 | agent-core |
| CORE-05 | ID/分页/时钟工具 | 模块规范 | `app/core/ids.py`、`pagination.py`、`clock.py` | CORE-01 | ULID 唯一；keyset 稳定；时间统一 UTC | UT：唯一性、分页边界、时区 | agent-core |
| CORE-06 | 架构测试 | `module-map.md` | `import-linter` 配置、`tests/architecture/` | CORE-01 | 跨模块内部 import 使 CI 失败；循环依赖失败 | 自测：注入违规样例必须失败 | agent-core |
| CORE-07 | 测试夹具 | CORE-03 | `tests/conftest.py`、testcontainers MySQL/Redis、工厂 | CORE-03 | 每个测试隔离；自动清理；可并行 | 冒烟：起容器、建表、回滚 | agent-core |

### 详细任务卡：CORE-03 数据库会话与租户上下文

- **Agent**: `agent-core`
- **目标**: 提供统一的 DB 会话、事务边界与租户上下文，确保任何数据访问都不可能绕过 `tenant_id`。
- **输入**:
  - `docs/architecture/module-map.md`
  - `.specify/memory/constitution.md`（MySQL 12 条、租户隔离条款）
  - `specs/001-mcp-server/data-model.md`（双 DSN 参考）
- **输出**:
  - `app/core/db.py`：`SessionFactory`、`read_session()`、`write_session()`、`UnitOfWork`
  - `app/core/context.py`：`TenantContext`（`tenant_id`、`subject_id`、`scopes`、`trace_id`）
  - `app/core/repository.py`：自动注入 `tenant_id` 的基类
- **依赖**: CORE-01、CORE-02
- **验收条件**:
  1. 未提供 `TenantContext` 的 Repository 调用直接抛异常，不执行 SQL。
  2. 同一请求内读写会话可复用；请求结束自动关闭。
  3. 只读查询默认走只读会话；写操作必须显式使用 `write_session()`。
  4. 事务异常自动回滚；禁止吞异常。
  5. 所有 SQL 日志包含 `trace_id` 与 `tenant_id`，但不含参数值。
- **测试用例**:
  - UT：`TenantContext` 缺失 → `TenantRequiredError`
  - UT：Repository 基类自动追加 `tenant_id` 条件
  - IT：事务内异常 → 回滚，数据未写入
  - IT：只读会话执行写 SQL → MySQL 拒绝
  - SEC：租户 A 上下文查询租户 B 数据 → 0 行
- **执行步骤**:
  1. 定义 `TenantContext` 与 `UnitOfWork` 协议。
  2. 实现 session factory（主库/只读副本两个 DSN）。
  3. 实现 Repository 基类，强制注入租户过滤。
  4. 接入 FastAPI 依赖（后续模块使用）。
  5. 写测试并确认先失败。
- **禁止**:
  - 在 Repository 之外直接 `session.execute` 业务 SQL
  - 使用全局单例 session
  - 在 `TenantContext` 里放 ORM 对象
- **验证命令**:
  ```bash
  pytest backend/tests/unit/core/test_context.py -q
  pytest backend/tests/integration/core/test_uow.py -q
  pytest backend/tests/security/test_tenant_isolation.py -q
  ```
- **完成定义**: 上述测试全绿；架构测试通过；README 更新。
- **预估**: M

---

## M01 identity

### 模块职责

租户、用户、角色、权限、API Key、认证适配。所有模块的租户上下文来源。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| IDN-01 | 租户/用户/角色模型 | `module-map.md`、MySQL 规则 | `models.py`、迁移、Repository | CORE-03 | 租户 slug 唯一；用户可多角色；软删除；审计字段 | UT：约束；IT：迁移 up/down | agent-identity |
| IDN-02 | RBAC 策略引擎 | IDN-01 | `policies.py`、权限矩阵 | IDN-01 | 角色/权限可组合；默认拒绝；越权抛 `ForbiddenError` | UT：allow/deny 矩阵 | agent-identity |
| IDN-03 | API Key 生命周期 | ADR-005、`data-model.md` | 签发/校验/吊销、HMAC、缓存 | IDN-01 | Key 只显示一次；HMAC 校验；吊销 ≤60s；scope 可校验 | UT：哈希/校验；IT：吊销；SEC：明文不落库 | agent-identity |
| IDN-04 | 认证适配器 | IDN-02/03 | FastAPI 依赖、`Principal` | IDN-02/03 | 支持 API Key；JWT 预留；401/403 正确 | IT：401/403/过期/吊销 | agent-identity |
| IDN-05 | 租户隔离测试 | IDN-01~04 | `tests/security/identity/` | IDN-01~04 | 跨租户读/写/导出 100% 拒绝 | SEC：四类操作 | agent-qa |
| IDN-06 | 身份审计钩子 | IDN-03、AUD-01 | 登录/签发/吊销事件 | IDN-03、AUD-01 | 事件含 actor、target、trace_id | IT：事件落库 | agent-identity |

### 详细任务卡：IDN-03 API Key 生命周期

- **Agent**: `agent-identity`
- **目标**: 提供可签发、可校验、可吊销的 API Key，供 REST 与 MCP 共用。
- **输入**:
  - `docs/adr/ADR-005-mcp-access-layer.md`
  - `specs/001-mcp-server/data-model.md`（`api_key` 表）
  - `constitution.md`（密钥、审计、租户隔离）
- **输出**:
  - `app/modules/identity/api_key.py`：`issue()`、`verify()`、`revoke()`、`rotate()`
  - 迁移：`api_key` 表
  - `public.py`：`ApiKeyVerifier` 协议与 `Principal`
- **依赖**: IDN-01
- **验收条件**:
  1. Key 格式 `pk_<env>_<key_id>_<secret>`；明文只在签发响应出现一次。
  2. 数据库只存 `HMAC-SHA256(pepper, secret)`。
  3. `verify()` 使用常量时间比较；过期/吊销返回统一失败。
  4. 吊销后 ≤ 60 秒生效（缓存 TTL 上限）。
  5. scope 为白名单子集；未知 scope 拒绝签发。
- **测试用例**:
  - UT：格式解析、HMAC 校验、常量时间比较
  - UT：过期/吊销/未知 key_id → 统一失败
  - IT：签发 → 校验成功 → 吊销 → 校验失败
  - SEC：数据库与日志中不出现明文 secret
  - SEC：租户 A 的 Key 不能访问租户 B
- **执行步骤**:
  1. 定义 `Principal` 与 scope 常量。
  2. 写迁移与模型。
  3. 实现签发/校验/吊销。
  4. 加缓存与失效策略。
  5. 写测试并先确认失败。
- **禁止**:
  - 使用 Argon2/bcrypt（高熵令牌不需要慢哈希）
  - 在日志/审计中记录 secret
  - 允许通配 scope
- **验证命令**:
  ```bash
  pytest backend/tests/unit/identity/test_api_key.py -q
  pytest backend/tests/integration/identity/test_api_key_lifecycle.py -q
  pytest backend/tests/security/identity/test_api_key_leak.py -q
  ```
- **完成定义**: 测试全绿；迁移可回滚；`public.py` 评审通过。
- **预估**: M

---

## M02 audit

### 模块职责

append-only 审计日志，覆盖安全事件与 MCP 工具调用。只写不改。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| AUD-01 | audit_log 表与写入器 | 宪法、`data-model.md` | 表、`AuditWriter`、批量写入 | CORE-03 | append-only；含 actor/action/resource/trace_id；不含 PII | UT：字段校验；IT：写入/查询 | agent-identity |
| AUD-02 | append-only 与保留策略 | AUD-01 | 权限限制、分区、清理任务 | AUD-01 | 无 UPDATE/DELETE 授权；保留 180 天；分区可 drop | IT：更新/删除被拒；保留任务 | agent-identity |
| AUD-03 | 审计查询接口 | AUD-01 | `AuditReader`（时间/actor/resource） | AUD-01 | 租户隔离；分页；只读 | IT：过滤与分页；SEC：跨租户 | agent-identity |

---

## M03 assets

### 模块职责

统一对象存储抽象（云 OSS / MinIO），负责预签名、校验、生命周期。业务模块不直接依赖厂商 SDK。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| AST-01 | Storage SPI + OSS 适配 | 宪法、`module-map.md` | `Storage` 协议、OSS 适配、配置 | CORE-02 | put/get/delete/presign；禁止 public bucket；错误可重试 | 契约：fake + OSS mock | agent-data |
| AST-02 | 预签名与校验 | AST-01 | 预签名 URL、sha256 校验 | AST-01 | TTL ≤15min；读时校验 checksum | UT：TTL；IT：篡改检测 | agent-data |
| AST-03 | artifact 元数据 | AST-01、CORE-03 | `artifact` 表、`ArtifactService` | AST-01、CORE-03 | 记录 s3_key/大小/sha256/mime；租户隔离 | IT：创建/查询；SEC：跨租户 | agent-data |
| AST-04 | MinIO 适配 | AST-01 | MinIO 适配器 | AST-01 | 与 OSS 行为一致；私有化可切换 | 契约：同一套用例跑两适配器 | agent-data |
| AST-05 | 存储契约测试 | AST-01~04 | `tests/contract/assets/` | AST-01~04 | 所有适配器通过同一契约 | 契约：put/get/presign/delete | agent-qa |

### 详细任务卡：AST-01 Storage SPI + OSS 适配

- **Agent**: `agent-data`
- **目标**: 用统一接口屏蔽云 OSS 与 MinIO，业务代码零厂商依赖。
- **输入**: 宪法（对象存储条款）、`module-map.md`
- **输出**:
  - `app/modules/assets/storage.py`：`Storage` Protocol
  - `app/modules/assets/oss.py`：OSS 适配
  - 配置项：`OSS_ENDPOINT`、`OSS_BUCKET`、`OSS_ACCESS_KEY`、`OSS_SECRET_KEY`
- **依赖**: CORE-02
- **验收条件**:
  1. 业务代码只 import `Storage`，不 import 厂商 SDK。
  2. Key 规范 `tenant/{tenant_id}/{asset_type}/{asset_id}/{version}/{filename}`。
  3. 禁止 public bucket；读取一律预签名。
  4. 写入计算并返回 `sha256`。
  5. 网络错误可重试；4xx 不重试。
- **测试用例**:
  - 契约：put → get → checksum 一致
  - 契约：presign → 过期后 403
  - SEC：跨租户 key 前缀不可访问
  - IT：OSS mock 超时 → 可重试错误
- **禁止**: 在业务模块直接 `import oss2`；把 bucket 设为 public；在 DB 存二进制。
- **验证命令**:
  ```bash
  pytest backend/tests/contract/assets -q
  pytest backend/tests/security/assets -q
  ```
- **完成定义**: 契约测试通过；OSS 与 MinIO 均可切换；README 更新。
- **预估**: M

---

## M14 observability

### 模块职责

结构化日志、OpenTelemetry Trace、Prometheus 指标、健康检查、告警规则。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| OBS-01 | 结构化日志 | 宪法 | `app/core/logging.py` | CORE-01 | JSON；含 trace_id/tenant_id；脱敏 | UT：脱敏；IT：字段完整 | agent-core |
| OBS-02 | OpenTelemetry Trace | OBS-01 | tracer、FastAPI/Celery 注入 | OBS-01 | 跨 API/Worker 传播；采样可配 | IT：trace 串联 | agent-core |
| OBS-03 | Prometheus 指标 | OBS-01 | `/metrics`、核心指标 | OBS-01 | 队列/延迟/错误/成本可采集 | IT：指标暴露 | agent-core |
| OBS-04 | 健康检查 | CORE-03 | `/healthz`、`/readyz` | CORE-03 | readiness 检查 DB/Redis | IT：依赖故障时 not ready | agent-core |
| OBS-05 | 告警规则 | OBS-03 | Prometheus 规则、看板 JSON | OBS-03 | 队列/错误/延迟/成本四类告警 | 规则语法校验 | agent-core |

---

## 交付检查

- [ ] CORE-01 ~ CORE-07 完成
- [ ] IDN-01 ~ IDN-06 完成
- [ ] AUD-01 ~ AUD-03 完成
- [ ] AST-01 ~ AST-05 完成
- [ ] OBS-01 ~ OBS-05 完成
- [ ] 架构测试在 CI 中生效
- [ ] 所有模块 README 已创建
- [ ] `task-index.md` 状态已更新
