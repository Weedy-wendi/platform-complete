# Feature Specification: model_gateway（M10）

**Feature**: `009-model-gateway` | **Phase**: P0b | **Status**: Implemented

**任务**: MGW-01 ~ MGW-05（`docs/planning/tasks/02-evaluation.md`）

---

## 1. 模块职责

统一模型调用出口：Provider 配置、LiteLLM 适配、超时/重试/熔断、Token/成本核算。

## 2. 为什么做

评测的 Judge、Agent 调用、Embedding 都需要统一模型出口；避免各模块直接依赖厂商 SDK，并保证成本可核算。

## 3. 功能需求

- **FR-001** Provider 配置：密钥引用 `secret_ref`，不落明文；可启停。
- **FR-002** `ModelGateway` + LiteLLM：统一接口，可切换 Provider。
- **FR-003** 超时/重试/熔断：connect/read/total 三层；429/5xx 可重试；4xx 不重试；熔断可恢复。
- **FR-004** Token/成本核算：每次调用写 `model_call`；账目一致。
- **FR-005** Provider 契约测试：正常/超时/限流行为一致。
- **FR-006** 原始响应可存 artifact（`raw_ref`）供 Replay。

## 4. 验收场景

1. **Given** 一个 Provider，**When** 调用模型，**Then** 返回统一响应 + usage + cost。
2. **Given** 429/5xx，**When** 调用，**Then** 按策略重试；最终明确错误。
3. **Given** 超时，**When** 调用，**Then** 在 total 超时内失败。
4. **Given** 熔断打开，**When** 调用，**Then** 快速失败；半开后恢复。
5. **Given** 配置密钥，**When** 查看数据库/日志，**Then** 无明文。

## 5. 关键实体

`provider_config`、`model_call`。

## 6. 边界与异常

- Provider 漂移、429、超时、熔断、成本超限、密钥泄露、大响应。

## 7. 不在范围

- 具体模型训练/微调。
- 评测评分逻辑（`010-evaluation`）。

## 8. 依赖

`002-core`、`005-assets`（raw response）、`004-audit`。
