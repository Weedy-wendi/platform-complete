# Implementation Plan: observability（M14）

**Feature**: `006-observability` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- 标准 logging + JSON formatter；`trace_id`/`tenant_id` 从上下文注入。
- OpenTelemetry SDK；FastAPI/Celery 自动注入；OTLP exporter。
- Prometheus client；按模块/路由/工具标签；避免高基数。
- 健康检查：DB/Redis/对象存储探测。
- 告警：Prometheus rules + Grafana dashboards。

## 2. 公开接口

`get_logger(name)`、`tracer(name)`、指标注册；`/healthz`、`/readyz`、`/metrics`。

## 3. 测试策略

- 单元：脱敏、字段完整、指标标签。
- 集成：Trace 串联、健康检查故障、告警规则语法。
- 安全：日志不泄露 Key/Prompt/PII。

## 4. 风险

| 风险 | 缓解 |
|---|---|
| 日志泄露 | 统一脱敏 + 测试 |
| 指标基数爆炸 | 标签白名单 |
| Trace 缺失 | 采样/降级 |
| 告警噪声 | 阈值/抑制/分级 |

## 5. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | trace/版本 |
| II 五原语 | 横切能力 |
| III API/CLI First | 运维端点 |
| IV Boring Tech | OTel/Prometheus |
| V 控制/执行分离 | 不执行任务 |
| VI 证据驱动 | 指标/告警/测试 |
| VII 模块化单体 | 独立模块 |
