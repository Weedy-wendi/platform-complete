# Implementation Plan: gate（M09）

**Feature**: `011-gate` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- 规则 DSL：`absolute` / `relative` / `significance` / `min_samples`。
- 判定只读 Run/Manifest/Comparison；结果落 `gate_result`。
- 证据引用 `run_item` / artifact；判定绑定 `manifest_hash`。

## 2. 数据模型

`gate`、`gate_rule`、`gate_result`（含 `manifest_hash`、`passed`、`status`、`evaluated_at`）。

## 3. 公开接口

`GateReader`、`GateResult`、`GateRule`。

## 4. 测试策略

- 单元：规则矩阵（通过/不通过/数据不足）。
- 集成：Run → GateResult；证据下钻；误拦/漏拦。
- 安全：跨租户 NotFound。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 误拦/漏拦 | 阈值边界测试 + 指标 |
| 不可复现 | 绑定 Manifest |
| 证据缺失 | 每条规则 required evidence |
| 跨租户 | Repository 过滤 |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | Manifest 绑定 |
| II 五原语 | Gate |
| III API/CLI First | GateReader 供 REST/MCP |
| IV Boring Tech | 规则引擎 |
| V 控制/执行分离 | 只读短任务 |
| VI 证据驱动 | 规则证据/误拦率 |
| VII 模块化单体 | 独立模块 |
