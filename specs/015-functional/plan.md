# Implementation Plan: functional（M12）

**Feature**: `015-functional` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- API 断言（httpx）+ 浏览器（Playwright）双执行器；通过 `TaskRunner` 异步调度。
- 沙箱：独立容器/进程；资源限制；网络白名单；超时强杀。
- 视觉差异：像素对比 + 阈值；差异图存 artifact。
- 证据：截图/录屏/console/network/trace → artifact。

## 2. 数据模型

`test_case`、`test_suite`、`test_run`、`test_step`、`assertion`、`visual_diff`。

## 3. 公开接口

`FunctionalTestService`、`TestRunView`、`TestStepResult`。

## 4. 测试策略

- 集成：API 正常/失败/超时；浏览器崩溃/超时/内存；网络白名单；证据回放。
- 安全：沙箱逃逸、网络越权、跨租户。
- 稳定性：并发 Run、artifact 清理。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 浏览器 Flaky | 重试一次、固定版本、隔离容器 |
| 视觉误报 | 阈值/遮罩/DPR 归一化 |
| 证据过大 | 压缩/分片/生命周期 |
| 沙箱逃逸 | 容器隔离 + 网络白名单 |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | 版本 + 浏览器版本 + 证据 |
| II 五原语 | Run/Evidence |
| III API/CLI First | Service/REST |
| IV Boring Tech | Playwright |
| V 控制/执行分离 | 浏览器在 Worker/沙箱 |
| VI 证据驱动 | 截图/录屏/差异图 |
| VII 模块化单体 | 独立模块 |
