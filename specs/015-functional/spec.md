# Feature Specification: functional（M12）

**Feature**: `015-functional` | **Phase**: P2 | **Status**: Implemented

**任务**: FUN-01 ~ FUN-06（`docs/planning/tasks/03-functional.md`）

---

## 1. 模块职责

用例与套件、API/UI 执行、断言、视觉差异、证据采集。与评测域共享 `Evidence`/`Run` 抽象，但不复用 evaluation 的表。

## 2. 为什么做

平台除了评测 Agent 回答，还要验证真实应用的 API 与浏览器行为，并产出可回放证据。

## 3. 功能需求

- **FR-001** 用例/套件模型：`test_case`/`test_suite`/`test_run`/`test_step`；版本化；租户隔离；步骤可排序。
- **FR-002** API 断言执行器：状态码、JSONPath、耗时；正常/失败/超时。
- **FR-003** 浏览器沙箱执行：独立容器/进程；CPU/内存/磁盘限制；网络白名单；超时强杀；崩溃重试一次后入 DLQ。
- **FR-004** 视觉差异：截图对比；阈值可配；差异图可下钻。
- **FR-005** 证据采集：截图/录屏/console/network/trace 写入 artifact；可回放。
- **FR-006** 与 evaluation 共享 Evidence 展示，不共享表。
- **FR-007** 浏览器版本锁定；镜像 digest 固定；端到端可复现。

## 4. 验收场景

1. **Given** API 用例，**When** 断言失败，**Then** 步骤失败并保留响应证据。
2. **Given** 浏览器卡死，**When** 执行，**Then** 超时强杀，其他用例不受影响。
3. **Given** 两张截图差异超阈值，**When** 对比，**Then** 生成差异图。
4. **Given** 网络白名单外请求，**When** 浏览器执行，**Then** 拒绝并记录。
5. **Given** 一次功能 Run，**When** 查看证据，**Then** 截图/录屏/console/network 可回放。

## 5. 关键实体

`test_case`、`test_suite`、`test_run`、`test_step`、`assertion`、`visual_diff`。

## 6. 边界与异常

- 浏览器崩溃/超时/内存爆炸/网络越权、视觉误报、证据过大、跨租户。

## 7. 不在范围

- 评测评分/门禁。
- 负载/性能测试。

## 8. 依赖

`002-core`、`005-assets`、`008-jobs`、`004-audit`。
