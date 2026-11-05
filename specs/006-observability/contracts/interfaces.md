# observability 公开契约

**模块**: M14 observability | **Owner**: agent-core

## 接口

```python
def get_logger(name: str) -> Logger: ...
def tracer(name: str) -> Tracer: ...

# Prometheus 指标（示例）
http_requests_total{route, method, status}
http_request_duration_seconds{route, method}
job_queue_depth{queue}
model_cost_usd_total{provider, model}
audit_write_failed_total
```

## 端点

| 端点 | 用途 | 检查 |
|---|---|---|
| `/healthz` | liveness | 进程存活 |
| `/readyz` | readiness | DB、Redis、对象存储（按部署） |
| `/metrics` | Prometheus | 文本格式 |

## 日志

- JSON；必含 `ts`、`level`、`logger`、`message`、`trace_id`、`tenant_id`。
- 脱敏：Bearer、`sk_`/`pk_`、邮箱、手机号、Prompt/样本正文。
- 禁止记录完整 API Key、完整 Prompt、完整样本。

## 告警

- 队列积压、错误率、P95 延迟、成本超限。
- 审计写入失败、依赖不可用必须 critical。
