# Tasks: core（M00）

**Source of truth**: `docs/planning/task-index.md`；明细见 `docs/planning/tasks/00-foundation.md`。

- [X] CORE-01 项目骨架与模块加载
- [X] CORE-02 配置与密钥管理
- [X] CORE-03 DB 会话与租户上下文
- [X] CORE-04 错误模型与错误码
- [X] CORE-05 ID/分页/时钟工具
- [X] CORE-06 架构测试
- [X] CORE-07 测试夹具（MySQL/Redis）

## 交付检查

- [X] `import app` 成功；模块可枚举
- [X] 跨租户查询 0 行
- [X] 事务异常回滚
- [X] 架构负例让 CI 失败

---

## Phase 2: Convergence

- [X] CORE-08 [HIGH] 增加平台级数据库与会话配置：`database_url`（写）、`read_replica_url`（读，缺省回退写）、平台 `redis_url`；提供 `SessionRegistry`/`Database` 默认读写路由与 `read_session`/`write_session`；补配置校验与读写选择测试 per CORE-02 / CORE-03 (partial)
- [X] CORE-09 [LOW] 为 Redis testcontainer 提供每测试唯一的 key namespace（或独立 DB index）并在 teardown flush，确保并行测试隔离 per CORE-07 / plan「每个测试隔离」 (partial)

---

## Phase 3: Convergence

- [X] CORE-10 [HIGH] 为 SQLAlchemy 引擎接入查询日志：记录 SQL 模板、`trace_id`、`tenant_id`，不记录绑定参数；`JsonFormatter` 在无 `Principal` 时回退 `TenantContext`；补单元/集成测试 per 002-core contracts/interfaces.md 规则 3 / CORE-03 AC5 (partial)
- [X] CORE-11 [MEDIUM] 增加 import-linter 架构契约配置（core / mcp / modules / api 分层，业务模块仅 import `.public`）并在 CI 执行 `lint-imports` per plan §1 / CORE-06 (partial)
- [X] CORE-12 [MEDIUM] 增加统一错误码注册表与全覆盖映射测试：注册所有 `AppError` 子类的 HTTP/MCP 映射，覆盖 `NotFoundError` 等未测错误 per CORE-04 输出「错误码注册表」/ UT「映射表全覆盖」 (partial)
- [X] CORE-13 [LOW] 补 `clock.py` 单元测试：`utcnow()` 为 aware UTC、`utcnow_naive()` 为 naive UTC、`to_iso()` 归一化到 UTC per FR-007 / CORE-05 测试用例「时区」 (partial)
