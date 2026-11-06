# Feature Specification: core（M00）

**Feature**: `002-core` | **Phase**: P0a | **Status**: Implemented

**任务**: CORE-01 ~ CORE-07（`docs/planning/tasks/00-foundation.md`）

---

## 1. 模块职责

配置、数据库会话、租户上下文、错误模型、ID/分页/时钟、测试夹具、架构测试。**不包含任何业务逻辑**。

## 2. 为什么做

所有模块都依赖统一的租户上下文、事务边界、错误模型和工具函数。MCP 特性已有 `app/core` 子集，本规格负责把它提升为平台级 core，并补齐 Repository 租户过滤、只读副本、架构硬门禁。

## 3. 功能需求

- **FR-001** 项目骨架与模块加载：`import app` 成功；模块可枚举；无循环依赖。
- **FR-002** 配置与密钥：缺失必填项启动失败；密钥不入日志；支持环境覆盖。
- **FR-003** `TenantContext`：`tenant_id`、`subject_id`、`scopes`、`trace_id`；缺失时拒绝数据访问。
- **FR-004** 读写会话：主库/只读副本两套 SessionFactory；写操作显式 `write_session()`；请求结束关闭。
- **FR-005** Repository 基类自动注入 `tenant_id`；禁止业务代码手写跨租户查询。
- **FR-006** 错误模型：`code`/`message`/`trace_id`/`details`；HTTP/MCP 映射；不泄露堆栈。
- **FR-007** ID/分页/时钟：ULID 唯一；keyset 分页稳定；UTC。
- **FR-008** 架构测试：跨模块内部 import、循环依赖、业务模块 import `app.api` 必须让 CI 失败。
- **FR-009** 测试夹具：testcontainers MySQL/Redis；每个测试隔离、自动清理、可并行。

## 4. 验收场景

1. **Given** 没有 `TenantContext` 的 Repository 调用，**When** 执行，**Then** 抛 `TenantRequiredError`，不执行 SQL。
2. **Given** 租户 A 上下文查询租户 B 数据，**When** 执行，**Then** 返回 0 行。
3. **Given** 事务内异常，**When** 回滚，**Then** 数据未写入。
4. **Given** 只读会话执行写 SQL，**When** 执行，**Then** MySQL 拒绝。
5. **Given** 临时注入跨模块内部 import，**When** CI 运行，**Then** 架构测试失败。

## 5. 关键实体

无（core 不拥有业务表）。

## 6. 边界与异常

- 缺少租户、事务异常、只读副本延迟、配置缺失、密钥泄露、循环依赖。

## 7. 不在范围

- 业务模块、REST 路由、前端。
- 具体 Repository 实现（由各模块负责）。

## 8. 依赖

无前置模块；是 P0a/P0b/P0c/P1/P2/P0d/P3 的基础。
