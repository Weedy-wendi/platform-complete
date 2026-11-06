# Agent 应用接入模型

**版本**: 1.0.0 | **日期**: 2026-11-05 | **关联**: `module-map.md`、`edge-cases.md`、`specs/001-mcp-server/`

---

## 1. 结论

**不需要为每个 Agent 应用重做一套系统。**

需要的是：

1. **一套规范契约**（平台内部统一的数据模型）
2. **两层薄适配**（Invoke 调用 / Observe 观测）
3. **一套一致性测试**（每个适配器都必须通过）

评测核心、数据资产、指标、Judge、Run、对比、门禁、报告、MCP、权限、审计、存储、队列、成本、可观测性**全部通用**。

每个 Agent 只适配 4 件事：

- 怎么调（请求构造、认证、协议）
- 怎么解析（响应、流式、工具调用）
- 怎么拿 trace（OTLP / SDK / 日志）
- 怎么重置状态（session / 多轮 / 清理）

> 目标：新增一个 Agent ≤ 1 人日；OpenAI 兼容或标准 HTTP Agent ≤ 30 分钟。

---

## 2. 两个方向

```text
                 ┌──────────────────────────────┐
Dataset ────────▶│  TargetAdapter.invoke()      │──▶ Agent Under Test
                 └──────────────┬───────────────┘
                                │ response / trace
                                ▼
                 ┌──────────────────────────────┐
                 │  AgentResponse + TraceSpan   │
                 └──────────────┬───────────────┘
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │  评测核心（通用，不随 Agent 变） │
                 │  metrics / judge / run / gate │
                 └──────────────────────────────┘
```

| 方向 | 含义 | 典型场景 |
|---|---|---|
| **Invoke** | 平台主动调用 Agent | 黑盒评测、回归、门禁 |
| **Observe** | Agent 主动上报 trace | 线上观测、轨迹评测、离线复盘 |

两者可以独立使用。很多 Agent 只需要 Observe（已经有线上流量），不需要平台调用。

---

## 3. 六种接入模式

| 模式 | 适用 | 平台侧实现 | 适配成本 | 局限 |
|---|---|---|---|---|
| **A. OpenAI 兼容 HTTP** | 提供 `/v1/chat/completions` 或兼容接口 | 配置 | 5 分钟 | 只能拿最终输出 |
| **B. 自定义 HTTP + JSON 映射** | 自有 REST API | 声明式配置（JSONPath/JMESPath） | 30 分钟 | 复杂流式/多轮需代码 |
| **C. MCP Client** | Agent 暴露 MCP 工具 | MCP 客户端适配器 | 1–2 天 | 只能评测工具调用面 |
| **D. Trace 接入（OTLP/OpenInference）** | 已接 OpenTelemetry 或可发 trace | TraceSource 适配器 | 1–2 天 | 只能离线/线上观测 |
| **E. SDK / CLI 上报** | 深度集成、内部应用 | Python SDK + CLI | 2–3 天 | 需要改 Agent 代码 |
| **F. 浏览器 / UI** | 只有 Web 界面 | Playwright + 视觉差异 | 1–2 天 | 慢、脆弱 |
| **G. 批量文件** | 离线跑批、第三方交付 | 文件适配器 | 0.5 天 | 无法实时 |

推荐顺序：**A → B → D → C → E → F**。能用 A 就不用 B，能用 B 就不用 E。

---

## 4. 通用层 vs 适配层

### 4.1 通用层（不随 Agent 变）

| 能力 | 说明 |
|---|---|
| 数据模型 | Project / Dataset / DatasetVersion / Sample |
| 评测资产 | Evaluator / Metric / Rubric / Suite / Baseline |
| 执行编排 | Run / RunItem / 状态机 / 重试 / 幂等 / 取消 |
| 打分 | 规则指标、Judge、人工复核、聚合 |
| 对比与门禁 | 差值、显著性、基线、Gate |
| 报告 | Run 报告、对比报告、导出、快照 |
| MCP | 只读查询（数据集、Run、Badcase、Gate） |
| 权限与租户 | 租户、RBAC、API Key、scope |
| 存储 | OSS / MinIO、artifact、checksum |
| 队列 | Celery / Redis、DLQ、重放 |
| 可观测 | trace_id、run_id、指标、成本 |
| 审计 | append-only、调用留痕 |

### 4.2 适配层（每个 Agent 才需要）

| 能力 | 说明 |
|---|---|
| 请求构造 | body 模板、字段映射、文件/多模态 |
| 认证 | Bearer / API Key / OAuth / 签名 |
| 协议 | HTTP / SSE / WebSocket / MCP / gRPC |
| 响应解析 | JSONPath、文本、流式、工具调用 |
| 多轮 | session、history、上下文重置 |
| 异步 | job handle、轮询、webhook |
| Trace | OTLP、OpenInference、日志、SDK |
| 状态重置 | `reset()`、session 隔离、幂等 |
| 错误映射 | 超时、429、5xx、业务错误 |

**适配层只做映射，不做评分，不做业务判断。**

---

## 5. 规范契约

平台内部统一使用以下模型，所有适配器负责把 Agent 的私有格式转换成它们。

```python
@dataclass(frozen=True)
class ContentPart:
    type: Literal["text", "image", "file", "json"]
    text: str | None = None
    artifact_ref: str | None = None
    mime_type: str | None = None

@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant", "tool", "system"]
    content: list[ContentPart]
    tool_call_id: str | None = None

@dataclass(frozen=True)
class Conversation:
    turns: list[Turn]

@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None

@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict
    result: Any | None = None
    error: str | None = None

@dataclass(frozen=True)
class AgentResponse:
    output: ContentPart
    finish_reason: Literal["stop", "length", "tool_call", "error", "timeout"]
    usage: Usage
    tool_calls: list[ToolCall] = field(default_factory=list)
    trace_id: str | None = None
    raw_ref: str | None = None       # 原始响应存 artifact，供重放

@dataclass(frozen=True)
class TraceSpan:
    trace_id: str
    span_id: str
    parent_id: str | None
    name: str
    kind: Literal["agent", "llm", "tool", "retriever", "other"]
    start_time: datetime
    end_time: datetime
    attributes: Mapping[str, Any]
    status: Literal["ok", "error"]
```

关键点：

- `raw_ref` 必须保存原始响应。**没有原始响应，就无法在不重跑 Agent 的情况下重算指标。**
- `trace_id` 用于把输出和轨迹关联起来。
- `usage` 由适配器解析；如果 Agent 不返回，标记 `unknown`，不要伪造。
- `finish_reason` 必须区分 `length` / `tool_call` / `timeout`，否则无法解释低分。

---

## 6. 适配器 SPI

```python
class TargetAdapter(Protocol):
    name: str
    version: str
    async def invoke(self, ctx: InvocationContext, item: TargetInvocation) -> AgentResponse: ...
    async def healthcheck(self, ctx: InvocationContext) -> Health: ...

class TraceSource(Protocol):
    name: str
    version: str
    async def collect(self, ctx: InvocationContext, run_id: str) -> AsyncIterator[TraceSpan]: ...
```

规则：

- 适配器通过 `entry_points` 注册，平台不 import 具体实现。
- 适配器版本写入 Run Manifest，保证可复现。
- 适配器不得写评测表、不得直接写 DB；只返回规范模型。
- 用户自定义适配器必须跑在沙箱（资源限制 + 网络白名单）。

---

## 7. 声明式 Target 配置

70% 的 Agent 不需要写代码，只需要配置：

```yaml
target:
  id: support-agent
  protocol: http_json
  endpoint: https://agent.example.com/v1/chat
  auth:
    type: bearer
    secret_ref: secret://tenant/acme/support-agent
  request:
    method: POST
    headers:
      Content-Type: application/json
    body:
      query: "{{ input.text }}"
      session_id: "{{ run_id }}-{{ item_id }}"
      stream: false
  response:
    output: "$.data.answer"
    trace_id: "$.data.trace_id"
    finish_reason: "$.data.finish_reason"
    usage:
      input_tokens: "$.usage.prompt_tokens"
      output_tokens: "$.usage.completion_tokens"
  timeout_ms: 30000
  retry:
    max_attempts: 2
    backoff_ms: 500
  reset:
    method: POST
    path: /session/reset
    body:
      session_id: "{{ run_id }}-{{ item_id }}"
```

约束：

- 模板只允许白名单变量：`input.text`、`item_id`、`run_id`、`tenant_id`、`seed`。
- 映射只允许 JSONPath / JMESPath，不允许执行任意表达式。
- `secret_ref` 只存引用，不存明文。
- 配置必须版本化；版本写入 Manifest。
- 声明式配置无法表达时，才写代码适配器。

---

## 8. 决策树

```text
Agent 有 OpenAI 兼容接口？
├─ 是 → 模式 A：配置即可
└─ 否
   ├─ 有 HTTP JSON 接口？
   │  ├─ 是 → 模式 B：声明式映射
   │  └─ 否
   │     ├─ 有 MCP？ → 模式 C
   │     ├─ 能发 OTel/OpenInference？ → 模式 D
   │     ├─ 能改代码接 SDK？ → 模式 E
   │     ├─ 只有 UI？ → 模式 F
   │     └─ 只能批量文件？ → 模式 G
```

---

## 9. 适配成本

| 模式 | 代码量 | 时间 | 后续维护 |
|---|---|---|---|
| A. OpenAI 兼容 | 0 | 5 分钟 | 极低 |
| B. HTTP + 映射 | 0 | 30 分钟 | 低 |
| C. MCP | 小 | 1–2 天 | 中 |
| D. Trace | 中 | 1–2 天 | 中 |
| E. SDK/CLI | 中 | 2–3 天 | 中 |
| F. 浏览器 | 中 | 1–2 天 | 高（UI 变化） |
| G. 批量文件 | 小 | 0.5 天 | 低 |

---

## 10. 适配器一致性测试

每个适配器必须通过同一套 conformance suite，否则不允许上线：

| 用例 | 要求 |
|---|---|
| 正常请求 | 返回规范 `AgentResponse` |
| 空输入 | 明确错误或空输出，不崩溃 |
| 超时 | 在预算内失败，标记 `timeout` |
| 429/5xx | 退避重试，最终明确错误 |
| 认证失败 | 401/403，不泄露细节 |
| 大响应 | 不 OOM；超限拒绝或截断 |
| 流式（如支持） | 中断可恢复；最终输出正确 |
| 多轮/session | 样本间状态隔离；reset 生效 |
| Unicode/多模态 | 正常解析 |
| Trace 关联 | `trace_id` 能关联到 span |
| 幂等/重放 | 同一 item 重复调用无副作用 |
| 租户隔离 | 不串租户 |
| usage 解析 | token/成本准确或标记 unknown |
| 错误映射 | 统一错误码 |

---

## 11. Record / Replay：迭代的关键

**评测必须与调用解耦。**

```text
Record 模式：调用 Agent → 保存原始响应到 artifact → 打分
Replay 模式：读取原始响应 → 用新指标/新 Judge 重新打分（不调用 Agent）
```

为什么重要：

- 换 Judge、改 Rubric、加指标时，**不需要重跑 Agent**，成本从“几小时 + 几百美元”降到“几分钟 + 几美元”。
- 线上 trace 可以直接进入离线重算，不需要复现 Agent。
- 不同 Agent 的输出可以放在同一套指标下比较。

要求：

- 每次调用必须保存 `raw_ref`（原始响应）。
- Replay 必须记录使用的 `adapter_version` 与 `target_config_version`。
- Replay 结果与 Record 结果必须可区分（`mode: record|replay`）。
- 原始响应保留策略与数据集版本一致，至少覆盖基线生命周期。

---

## 12. 版本与复现

Run Manifest 必须包含：

- `target_id`
- `target_config_version`
- `adapter_name` / `adapter_version`
- `protocol`
- `endpoint_hash`（不存明文 URL，避免泄露内部地址）
- `trace_source` / `trace_version`
- `record_mode`（record/replay）

任何一项变化，都必须视为新的运行条件；对比时标记 `not_comparable`，除非重新冻结基线。

---

## 13. 反模式

1. 为每个 Agent 复制一套评测逻辑
2. 在适配器里做评分/业务判断
3. 为每个框架写专用集成（LangChain / CrewAI / AutoGen）
4. 把 Agent 特定字段加到核心表
5. 让 Agent 直接写平台数据库
6. Target 配置无版本
7. 不保存原始响应，导致无法重放
8. 不隔离 session，样本之间互相污染
9. 只支持同步，忽略流式/异步
10. 信任 Agent 上报的 usage/成本，不做校验
11. 只做黑盒，不接 trace，导致无法解释失败
12. 把“适配”做成“分叉”（fork）

---

## 14. 接入边界情况

集成层特有的边界（其余见 `edge-cases.md`）：

| 场景 | 期望 |
|---|---|
| HTTP 200 但 body 是错误 | 解析业务错误码，标记 item error |
| 流式中断 | 保留已收内容，标记 `truncated` |
| 多轮上下文污染 | 每个样本独立 session，必须 reset |
| 工具调用失败 | 记录 tool error，不吞掉 |
| trace 缺失 | 标记 `trace_missing`，降级为黑盒评分 |
| trace 重复 | 以 `trace_id` 去重 |
| trace 超长 | 截断 span 属性，保留关键节点 |
| session 泄漏 | run 结束清理；TTL 兜底 |
| 认证过期 | 刷新或明确失败，不无限重试 |
| 限流 | 退避 + `Retry-After`，不重复计费 |
| 大文件/多模态 | 走 artifact，不进 DB |
| Agent 返回超长输出 | 截断并标记，不 OOM |

---

## 15. 结论

| 层 | 占比 | 是否随 Agent 变 |
|---|---|---|
| 评测核心、数据、指标、门禁、报告、MCP、权限、存储、队列、审计 | 80–90% | **不变** |
| Target 配置 / Adapter / TraceSource | 10–20% | **每个 Agent 薄适配** |

**正确做法不是“为每个 Agent 改系统”，而是“让每个 Agent 通过同一组契约接进来”。**

目标指标：

- 新增 OpenAI 兼容 Agent ≤ 30 分钟
- 新增自定义 HTTP Agent ≤ 1 人日
- 新增 Trace 接入 ≤ 2 人日
- 适配器一致性测试 100% 通过才允许上线
