# Implementation Plan: model_gateway（M10）

**Feature**: `009-model-gateway` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- LiteLLM 统一适配；Provider 配置 + `secret_ref`。
- 策略中间件：超时/重试/熔断；成本累计。
- `model_call` 记录 token/成本/延迟/状态；原始响应可存 artifact。

## 2. 数据模型

`provider_config`、`model_call`。

## 3. 公开接口

`ModelGateway`、`ModelRequest`、`ModelResponse`、`ModelCallRecord`。

## 4. 测试策略

- 契约：fake provider；正常/超时/限流。
- 集成：成本账目、重试、熔断恢复、raw_ref。
- 安全：密钥不落库/日志。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| Provider 漂移 | 版本锁定 + 契约测试 |
| 成本失控 | 预算 + 熔断 |
| 超时挂起 | 三层超时 |
| 密钥泄露 | secret_ref + 脱敏 |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | 模型/版本/参数入 Manifest |
| II 五原语 | Run 的模型调用 |
| III API/CLI First | Service 供评测/REST |
| IV Boring Tech | LiteLLM |
| V 控制/执行分离 | Worker 调用 |
| VI 证据驱动 | 契约/成本测试 |
| VII 模块化单体 | 独立模块 |
