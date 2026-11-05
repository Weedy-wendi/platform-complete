# Feature Specification: observability（M14）

**Feature**: `006-observability` | **Phase**: P0a | **Status**: Implemented

**任务**: OBS-01 ~ OBS-05（`docs/planning/tasks/00-foundation.md`）

---

## 1. 模块职责

结构化日志、OpenTelemetry Trace、Prometheus 指标、健康检查、告警规则。

## 2. 为什么做

没有可观测性，评测不可复现、故障无法定位、成本不可控。MCP 已有日志/指标/健康检查子集，本规格扩展到平台所有模块。

## 3. 功能需求

- **FR-001** 结构化 JSON 日志：含 `trace_id`/`tenant_id`；脱敏 API Key、邮箱、手机号、Prompt/样本正文。
- **FR-002** OpenTelemetry Trace：跨 API/Worker 传播；采样可配；Run → item → model call 链路。
- **FR-003** Prometheus 指标：请求、错误、延迟、队列、成本；`/metrics`。
- **FR-004** `/healthz`（liveness）与 `/readyz`（DB/Redis/对象存储依赖检查）。
- **FR-005** 告警：队列积压、错误率、P95 延迟、成本超限；审计失败 critical。

## 4. 验收场景

1. **Given** DB 或 Redis 不可用，**When** `/readyz`，**Then** 503 并标注依赖。
2. **Given** 一次 Run，**When** 查看 Trace，**Then** API→Job→Model 调用可串联。
3. **Given** 日志包含 API Key/邮箱/Prompt，**When** 输出，**Then** 已脱敏。
4. **Given** 队列积压/错误率/成本超阈值，**When** 指标持续，**Then** 告警触发。

## 5. 关键实体

无（指标/日志/Trace）。

## 6. 边界与异常

- 依赖故障、采样丢失、日志泄露、告警噪声、指标基数爆炸。

## 7. 不在范围

- 具体监控平台部署（Prometheus/Grafana 默认）。
- 业务指标定义（由各模块提供）。

## 8. 依赖

`002-core`。
