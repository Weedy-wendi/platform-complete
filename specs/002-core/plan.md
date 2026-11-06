# Implementation Plan: core（M00）

**Feature**: `002-core` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- Python 3.12、SQLAlchemy 2.0、PyMySQL、Alembic、Pydantic Settings。
- 模块化单体：`app/core` 无业务依赖；`app/modules/*` 通过 `public.py` 交互。
- 读写分离：主库/只读副本两个 DSN；只读查询默认走副本。
- 架构门禁：`import-linter` + AST 测试。

## 2. 目录结构

```text
backend/app/core/
├── config.py       # Settings、SecretStr、启动校验
├── context.py      # TenantContext、contextvar
├── db.py           # engine/session、readonly session、UnitOfWork
├── repository.py   # 自动 tenant_id 过滤基类
├── errors.py       # AppError、错误码、HTTP/MCP 映射
├── ids.py          # ULID
├── pagination.py   # Page[T]、clamp_limit
├── clock.py        # UTC
└── logging.py      # 结构化日志/脱敏
```

## 3. 与 MCP 现有代码

复用 `backend/app/core` 现有实现；`create_readonly_engine_from_dsn` 保留并扩展。新增 `repository.py`、`TenantContext` 强化、测试夹具；不复制 MCP 模块。

## 4. 测试策略

- 单元：上下文缺失、Repository 租户过滤、错误映射、ID/分页/时区。
- 集成：事务回滚、只读会话写拒绝、测试夹具隔离。
- 安全：跨租户 0 行。
- 架构：负例注入必须失败。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 租户过滤遗漏 | Repository 基类 + 安全测试 |
| 全局 session | 禁止单例；每请求作用域 |
| 只读副本延迟 | 关键写后读走主库 |
| 架构测试被绕过 | CODEOWNERS + 禁止 `noqa` |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | UTC/版本/哈希 |
| II 五原语 | 仅基础设施 |
| III API/CLI First | Service 层供 REST/MCP 复用 |
| IV Boring Tech | LTS/lockfile |
| V 控制/执行分离 | 不执行长任务 |
| VI 证据驱动 | 测试/架构门禁 |
| VII 模块化单体 | `public.py` 边界 |
