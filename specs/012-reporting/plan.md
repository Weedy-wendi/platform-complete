# Implementation Plan: reporting（M12/M08）

**Feature**: `012-reporting` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- 读模型/物化视图由 Run 查询接口驱动；定时/事件刷新。
- 报告渲染：Markdown/JSON；对比报告复用 EVL-09 统计。
- 导出：JSON/CSV/JUnit，流式。
- 快照：artifact + 签名链接 + TTL。

## 2. 数据模型

`report_snapshot`、`read_model_*`；正文在 artifact。

## 3. 公开接口

`ReportReader`、`RunReport`、`ComparisonReport`。

## 4. 测试策略

- 集成：报告生成、对比、导出、快照 TTL。
- 安全：跨租户、分享链接越权。
- 性能：读模型 P95 <300ms。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 报告与 Run 不一致 | 绑定 manifest_hash |
| 读模型延迟 | 刷新策略 + 主库兜底 |
| 大导出 OOM | 流式 |
| 链接泄露 | 签名 + TTL + 不可枚举 |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | 快照/Manifest |
| II 五原语 | Evidence/报告 |
| III API/CLI First | REST 导出 |
| IV Boring Tech | 标准格式 |
| V 控制/执行分离 | 只读投影 |
| VI 证据驱动 | 导出/报告测试 |
| VII 模块化单体 | 独立模块 |
