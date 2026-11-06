# 模块开发规范（Module Conventions）

**版本**: 1.0.0 | **日期**: 2026-11-05 | **关联**: `module-map.md`、`constitution.md` v1.3.0

本文件规定「一个模块长什么样、代码放哪里、边界怎么守」。所有子 Agent 必须遵守。

---

## 1. 目录结构

```text
backend/app/modules/<module>/
├── __init__.py
├── public.py          # 唯一对外入口：Protocol + 不可变 DTO + 事件
├── models.py          # SQLAlchemy 模型（仅本模块的表）
├── schemas.py         # 请求/响应 DTO（API / MCP）
├── repository.py      # 数据访问，强制 tenant_id 过滤
├── service.py         # 用例编排，框架无关，不依赖 FastAPI
├── policies.py        # 授权规则（scope / role / 租户）
├── events.py          # 领域事件定义
├── handlers.py        # JobHandler / 事件消费者
├── api.py             # FastAPI Router（薄适配层）
├── migrations/        # 本模块的 Alembic revision（可放在全局 migrations）
├── README.md          # 职责、表、公开接口、负责人
└── tests/             # 模块内测试（也可放全局 tests/，二选一）
```

**分层依赖方向**：`api → service → repository → models`。禁止反向依赖。

---

## 2. 命名规范

| 对象 | 规范 | 示例 |
|---|---|---|
| 模块目录 | 小写、单数 | `catalog`、`evaluation` |
| 表 | 小写下划线，全局唯一 | `dataset_version`、`run_item` |
| 公开 DTO | `<Entity>View` / `<Entity>Ref` | `DatasetView`、`RunRef` |
| 公开服务 | `<Module>Service` / `<Module>Reader` | `CatalogService`、`RunReader` |
| 领域事件 | `<module>.<entity>.<action>` | `evaluation.run.completed` |
| 错误码 | 大写下划线 | `DATASET_VERSION_IMMUTABLE` |
| 任务 ID | `<MODULE>-<NN>` | `CAT-03`、`MCP-09` |

---

## 3. 各文件职责

### `public.py`

- 只放：Protocol、不可变 DTO、枚举、领域事件类型。
- 不放：ORM、SQL、Repository、内部 helper。
- 所有方法显式接收 `TenantContext`。
- 分页统一 `Page[T]`。

### `models.py`

- 只定义本模块拥有的表。
- 禁止定义其他模块的表或跨模块外键。
- 高频表不建外键（遵循宪法）。
- 必须包含 `tenant_id`（除全局字典表）与 `created_at` / `updated_at`。

### `repository.py`

- 所有查询必须带 `tenant_id` 条件；建议基类自动注入。
- 禁止返回 ORM 对象给其他模块；转换为 DTO。
- 禁止在 Repository 里做业务判断。
- 复杂查询必须附 `EXPLAIN` 结论（索引是否命中）。

### `service.py`

- 一个方法 = 一个用例。
- 不依赖 FastAPI / Request / Depends。
- 不直接开事务；由 `UnitOfWork` 管理。
- 跨模块协作只调用 `public.py`。
- 副作用通过事件或 Job 投递，禁止同步调用其他模块写操作。

### `policies.py`

- 纯函数：`can(ctx, action, resource) -> bool`。
- 不查库；所需数据由 service 传入。
- 权限不足抛 `ForbiddenError`，不返回布尔值给上层自行处理。

### `api.py`

- 只做：参数校验、调用 service、映射响应。
- 禁止写业务逻辑、禁止直接访问 repository。
- 统一异常由全局 handler 转换为 HTTP 响应。

### `handlers.py`

- 每个 JobHandler 必须幂等。
- 必须声明 `max_retries`、`timeout`、`dead_letter` 行为。
- 失败时抛领域异常，由 jobs 模块统一重试/入 DLQ。

---

## 4. 错误处理

```python
# app/core/errors.py
class AppError(Exception):
    code: str
    http_status: int
    retryable: bool = False

class NotFoundError(AppError): ...
class ForbiddenError(AppError): ...
class ConflictError(AppError): ...
class ValidationError(AppError): ...
class UpstreamError(AppError): ...
```

规则：

- 业务代码只抛领域异常，不抛 `HTTPException`。
- API 层统一映射为 HTTP；MCP 层统一映射为 JSON-RPC 错误。
- 错误响应不得包含堆栈、SQL、文件路径。
- 每个错误码必须在 `contracts/errors.md` 或模块 README 登记。

---

## 5. 迁移规范

- 一个迁移只做一个 DDL；禁止一个 revision 里跨多个模块建表。
- 文件名带模块前缀：`20261105_01_catalog_create_dataset.py`。
- 必须附 `downgrade()`；不可逆迁移需在 PR 说明并附数据快照方案。
- 大表变更使用 `ALGORITHM=INPLACE, LOCK=NONE` 或 gh-ost。
- 迁移前必须备份；禁止业务高峰执行。
- 迁移后必须跑：`alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head`。

---

## 6. 测试规范

| 层 | 位置 | 要求 |
|---|---|---|
| 单元 | `tests/unit/<module>/` | 纯逻辑，无 DB；覆盖分支与边界 |
| 集成 | `tests/integration/<module>/` | 真实 MySQL/Redis（testcontainers）；覆盖租户隔离 |
| 契约 | `tests/contract/<module>/` | 公开接口、API Schema、MCP 工具 Schema |
| 安全 | `tests/security/` | 越权、注入、密钥泄露、SQL 注入 |
| 架构 | `tests/architecture/` | 跨模块导入、循环依赖、分层违规 |
| 性能 | `tests/load/` | 关键路径 P95 |

最低要求：

- 核心域（evaluation / catalog / jobs / mcp）行覆盖率 ≥ 85%。
- 其他模块 ≥ 70%。
- 每个公开方法至少 1 个正常路径 + 1 个错误路径测试。
- 每个迁移至少 1 个 upgrade/downgrade 测试。
- 每个越权风险点至少 1 个跨租户测试。

---

## 7. 模块 README 模板

```markdown
# 模块：<名称>

- **ID**: Mxx
- **负责人 Agent**: agent-xxx
- **阶段**: P0a / P0b / P0c / P1 / P2

## 职责
## 拥有的表
## 公开接口（public.py）
## 依赖模块
## 禁止事项
## 关键决策（ADR 链接）
## 测试与验证命令
```

---

## 8. Definition of Done（每个任务必须全部满足）

- [ ] 代码在正确模块内，未跨边界 import
- [ ] `public.py` 变更已评审并记录版本
- [ ] 单元 + 集成 + 契约测试通过
- [ ] 跨租户越权测试通过（如涉及数据）
- [ ] `ruff` / `mypy` 通过
- [ ] 架构测试通过（`lint-imports`）
- [ ] 迁移可 upgrade/downgrade（如涉及）
- [ ] 结构化日志 + 关键指标已加
- [ ] 错误码已登记
- [ ] 文档/README 已更新
- [ ] 交付报告包含验证证据

---

## 9. 禁止事项（Reviewer 直接打回）

- 跨模块 import `models` / `repository` / `service`
- 跨模块 JOIN 或直接查别人的表
- 在 `api.py` 写业务逻辑
- 在 `service.py` 使用 FastAPI 对象
- 捕获所有异常后静默返回 `None`
- 用 `try/except` 吞掉事务错误
- 迁移里包含多个不相关 DDL
- 新增依赖未走供应链审查
- 测试里使用真实外部服务（OSS/LLM/Qdrant 必须 fake 或容器）
- 日志打印完整 Prompt / 样本 / 密钥
- 修改其他模块的迁移或测试夹具
