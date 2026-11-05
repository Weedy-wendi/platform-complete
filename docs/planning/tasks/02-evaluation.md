# P0b/P0c 任务卡：评测域

**覆盖模块**: M06 evaluation、M07 jobs、M09 gate、M10 model_gateway、M08 reporting

**负责 Agent**: `agent-eval`、`agent-qa`

**通用协议**: 按 `docs/planning/subagent-protocol.md` 执行。

---

## M07 jobs

### 模块职责

任务状态机、队列、重试、幂等、调度、死信。业务模块只注册 Handler，不直接操作 Celery。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| JOB-01 | job/job_event 模型 | CORE-03 | `job`、`job_event`、状态机 | CORE-03 | 状态迁移合法；事件 append-only | UT：状态机；IT：事件回放 | agent-eval |
| JOB-02 | TaskRunner SPI + Celery | JOB-01 | `TaskRunner`、Celery 适配、配置 | JOB-01 | 业务不依赖 Celery；可替换 | 契约：fake runner | agent-eval |
| JOB-03 | 重试/幂等/DLQ | JOB-02 | 重试策略、幂等键、DLQ、重放 | JOB-02 | 重复投递不重复执行；失败入 DLQ | IT：重复/失败/重放 | agent-eval |
| JOB-04 | 调度器单例 | JOB-02 | leader election、定时任务 | JOB-02 | 多副本只一个调度器 | IT：双副本竞争 | agent-eval |
| JOB-05 | 进度与 SSE | JOB-01 | 进度快照、SSE 推送 | JOB-01 | 断线可回放；进度准确 | IT：SSE 重连 | agent-eval |
| JOB-06 | 故障与恢复测试 | JOB-03/04 | 故障注入测试 | JOB-03/04 | 崩溃后任务可恢复/重放 | IT：kill worker | agent-qa |

### 详细任务卡：JOB-03 重试/幂等/DLQ

- **Agent**: `agent-eval`
- **目标**: 保证异步任务在重复投递、Worker 崩溃、超时重投下不产生重复副作用。
- **输入**: `constitution.md`（Redis broker 护栏）、JOB-02
- **输出**: `retry.py`、`idempotency.py`、`dead_letter.py`、`pingce job replay` CLI
- **依赖**: JOB-02
- **验收条件**:
  1. `acks_late=True`、`task_reject_on_worker_lost=True`、`prefetch_multiplier=1`。
  2. `visibility_timeout = 6h`，大于单 Run 上限。
  3. 幂等键 `hash(job_id, item_id, attempt)` 建唯一索引；重复执行无重复写入。
  4. 最多重试 3 次，指数退避 + 抖动；不可重试错误直接入 DLQ。
  5. DLQ 记录可查询、可重放、可标记忽略。
  6. Redis 不可用时任务不丢失（持久化 + 告警）。
- **测试用例**:
  - IT：同一任务投递两次 → 只执行一次副作用
  - IT：Worker 在事务中崩溃 → 任务重新投递且幂等
  - IT：超过重试上限 → DLQ 有记录
  - IT：重放 DLQ → 成功且不重复
- **执行步骤**:
  1. 定义幂等键与唯一索引。
  2. 实现重试策略与错误分类。
  3. 实现 DLQ 表与重放命令。
  4. 配置 Redis broker 参数。
  5. 写故障注入测试。
- **禁止**: 无限重试；吞掉异常；用 Celery result backend 存大结果；无幂等键的写任务。
- **验证命令**:
  ```bash
  pytest backend/tests/integration/jobs/test_retry.py -q
  pytest backend/tests/integration/jobs/test_dlq.py -q
  ```
- **完成定义**: 重复/崩溃/重放测试通过；DLQ CLI 可用。
- **预估**: L

---

## M10 model_gateway

### 模块职责

统一模型调用出口：Provider 配置、LiteLLM 适配、超时/重试/熔断、Token/成本核算。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| MGW-01 | Provider 配置 | CORE-02、AST-01 | `provider_config`、密钥引用 | CORE-02、AST-01 | 密钥不落明文；可启停 | IT：配置 CRUD；SEC：密文 | agent-eval |
| MGW-02 | LiteLLM 适配 | MGW-01、ADR-005 | `ModelGateway`、LiteLLM 客户端 | MGW-01 | 统一接口；可切换 Provider | 契约：fake provider | agent-eval |
| MGW-03 | 超时/重试/熔断 | MGW-02 | 策略中间件 | MGW-02 | 每调用三层超时；熔断可恢复 | IT：超时/熔断 | agent-eval |
| MGW-04 | Token/成本核算 | MGW-02 | `model_call`、成本聚合 | MGW-02 | 每次调用记录 token/成本 | IT：账目一致 | agent-eval |
| MGW-05 | Provider 契约测试 | MGW-02~04 | `tests/contract/gateway/` | MGW-02~04 | 多 Provider 行为一致 | 契约：正常/超时/限流 | agent-qa |

---

## M06 evaluation

### 模块职责

评分器、指标、套件、目标、Run、样本结果、基线。平台的核心域。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| EVL-01 | 评分器/指标模型 | CORE-03 | `evaluator`、`evaluator_version`、`metric` | CORE-03 | 版本不可变；指标方向明确 | UT：模型；IT：版本 | agent-eval |
| EVL-02 | 规则评分器 | EVL-01 | 精确匹配/F1/正则等 | EVL-01 | 结果确定；边界清晰 | UT：边界用例 | agent-eval |
| EVL-03 | Judge 评分器 | EVL-01、MGW-02 | Rubric、结构化输出、裁判调用 | EVL-01、MGW-02 | 输出 Schema 校验；留痕 | UT：解析；IT：调用留痕 | agent-eval |
| EVL-04 | Suite/Target/Baseline | EVL-01 | `eval_suite`、`suite_version`、`target`、`baseline` | EVL-01 | 版本绑定；基线冻结 | IT：绑定/冻结 | agent-eval |
| EVL-05 | Run 创建与 Manifest | CAT-03、EVL-04 | `run`、manifest、幂等 | CAT-03、EVL-04 | Manifest 完整；可重放；重复创建幂等 | UT：manifest hash；IT：重放 | agent-eval |
| EVL-06 | Run 执行器 | EVL-05、JOB-02、MGW-02 | JobHandler、批量推理/打分 | EVL-05、JOB-02、MGW-02 | 并发可控；部分失败可统计 | IT：端到端；PERF：1000 条 | agent-eval |
| EVL-07 | 状态机/重试/幂等 | EVL-06、JOB-03 | 状态迁移、重试、取消 | EVL-06、JOB-03 | 合法迁移；取消生效 | IT：状态/取消 | agent-eval |
| EVL-08 | Run 查询接口 | EVL-05 | `public.RunReader` | EVL-05 | 状态/进度/明细/分页 | 契约：接口；IT：分页 | agent-eval |
| EVL-09 | 对比与统计 | EVL-08 | 差值、置信区间、显著性 | EVL-08 | 不把噪声当提升 | UT：统计；IT：对比 | agent-eval |
| EVL-10 | 复现测试 | EVL-05/06 | 重放测试套件 | EVL-05/06 | 同 manifest 结果一致 | IT：重放 5 次 | agent-qa |
| EVL-11 | Judge 校准流程 | EVL-03 | 人工标注 → 一致率报告 | EVL-03 | κ ≥ 0.7 才可用于门禁 | IT：校准报告 | agent-eval |
| EVL-12 | 成本预算与熔断 | EVL-06、MGW-04 | 预算上限、暂停/告警 | EVL-06、MGW-04 | 超预算暂停；可恢复 | IT：超预算 | agent-eval |
| EVL-13 | TargetAdapter SPI 与注册表 | `agent-integration.md`、EVL-04 | `targets/` SPI、Registry、Config Schema | EVL-04 | 适配器可插拔；配置版本化；不写业务表 | 契约：Registry/Config | agent-eval |
| EVL-14 | 声明式 HTTP / OpenAI 适配器 | EVL-13、`agent-integration.md` | HTTP JSON + OpenAI 兼容适配器 | EVL-13 | A/B 模式零代码；超时/重试；保存 raw_ref | 契约：A/B 模式 | agent-eval |
| EVL-15 | TraceSource（OTLP/OpenInference） | EVL-13、OBS-02、AST-03 | Span 归一化、trace 关联 | EVL-13、OBS-02、AST-03 | OTLP 接入；去重；缺失降级；租户隔离 | IT：OTLP/去重/缺失 | agent-eval |
| EVL-16 | 适配器一致性 + Record/Replay | EVL-14/15、`edge-cases.md` | Conformance Suite、Replay 模式、Manifest 字段 | EVL-14、EVL-15 | 所有适配器通过；Replay 不调用 Agent | 契约/IT：重放与版本 | agent-qa |

### 详细任务卡：EVL-05 Run 创建与 Manifest

- **Agent**: `agent-eval`
- **目标**: 每次 Run 都有完整、不可变、可重放的 Manifest。
- **输入**: CAT-03、EVL-04、宪法「可复现优先」
- **输出**: `run` 表、`manifest.py`、`EvaluationService.start_run()`
- **依赖**: CAT-03、EVL-04
- **验收条件**:
  1. Manifest 必含：`dataset_hash`、`evaluator_versions[]`、`metric_configs`、`target_config`（model/temperature/seed/prompt_version）、采样策略与 seed、`code_version`、`env`。
  2. `manifest_hash` 稳定；同输入同哈希。
  3. 重复提交（同 `client_request_id`）返回同一 `run_id`。
  4. Run 创建后 Manifest 不可修改。
  5. 预算上限在创建前校验。
- **测试用例**:
  - UT：Manifest 序列化稳定 → 哈希稳定
  - UT：缺字段 → 创建失败
  - IT：重复请求 → 同一 run_id
  - IT：按 manifest_hash 重放 → 结果一致
- **执行步骤**:
  1. 定义 Manifest Schema。
  2. 实现快照与哈希。
  3. 实现幂等创建。
  4. 接入预算校验。
  5. 写重放测试。
- **禁止**: Manifest 引用可变对象；用时间戳参与哈希；允许修改历史 Manifest。
- **验证命令**:
  ```bash
  pytest backend/tests/unit/evaluation/test_manifest.py -q
  pytest backend/tests/integration/evaluation/test_run_replay.py -q
  ```
- **完成定义**: 重放 5 次结果一致；幂等测试通过。
- **预估**: M

### 详细任务卡：EVL-06 Run 执行器

- **Agent**: `agent-eval`
- **目标**: 批量执行推理与打分，支持并发控制、部分失败、成本统计与证据留存。
- **输入**: EVL-05、JOB-02、MGW-02
- **输出**: `handlers.py` 的 `EvalRunHandler`、`run_item` 写入、进度更新
- **依赖**: EVL-05、JOB-02、MGW-02
- **验收条件**:
  1. 按 Provider 限流并发；并发可配。
  2. 每条样本独立记录状态（`succeeded`/`failed`/`skipped`/`error`），单条失败不拖垮整 Run。
  3. 结果写 `run_item` + `score`；Judge 调用写 `judge_call`。
  4. 进度、成本、失败数实时可查。
  5. 取消后已完成的 item 保留。
  6. 1000 条 × 1 指标在 10 分钟内完成（本地基准）。
- **测试用例**:
  - IT：端到端 100 条 → 结果完整
  - IT：单条超时 → 标记 error，其余继续
  - IT：取消 → 不再取新 item
  - PERF：1000 条基准
  - IT：成本累计与 mgw 记录一致
- **执行步骤**:
  1. 读取 Manifest，拉取样本分页。
  2. 并发调用模型网关。
  3. 逐条打分并写结果。
  4. 更新进度/成本。
  5. 处理取消与超时。
- **禁止**: 全量加载样本到内存；无上限并发；单条失败导致整 Run 失败；重复计费。
- **验证命令**:
  ```bash
  pytest backend/tests/integration/evaluation/test_run_executor.py -q
  pytest backend/tests/load/evaluation/test_run_benchmark.py -q
  ```
- **完成定义**: 端到端/失败/取消/性能测试通过。
- **预估**: L

### 详细任务卡：EVL-13 TargetAdapter SPI 与注册表

- **Agent**: `agent-eval`
- **目标**: 让不同 Agent 应用通过统一 SPI 接入，评测核心不感知具体协议。
- **输入**: `docs/architecture/agent-integration.md`、EVL-04
- **输出**:
  - `app/modules/evaluation/targets/base.py`：`TargetAdapter`、`TraceSource`、规范 DTO
  - `targets/registry.py`：entry_points 注册
  - `targets/config.py`：Target Config JSON Schema
- **依赖**: EVL-04
- **验收条件**:
  1. 新增适配器不需要改评测核心代码。
  2. 适配器只能返回 `AgentResponse` / `TraceSpan`，不得写业务表。
  3. Target Config 必须版本化，并写入 Run Manifest。
  4. 适配器异常统一映射为领域错误，不泄露内部细节。
  5. 自定义适配器可在沙箱执行。
- **测试用例**:
  - 契约：注册/发现/加载
  - 契约：Config Schema 校验（必填/未知字段/非法协议）
  - SEC：适配器无法访问 DB
  - IT：fake adapter 跑通 Run
- **执行步骤**:
  1. 定义规范 DTO 与 Protocol。
  2. 实现注册表与 entry_points 加载。
  3. 实现 Config Schema 与版本字段。
  4. 写 fake adapter 与契约测试。
- **禁止**: 在核心代码里 `if target == "xxx"`；适配器直接写 DB；配置无版本。
- **验证命令**:
  ```bash
  pytest backend/tests/contract/evaluation/test_target_registry.py -q
  pytest backend/tests/unit/evaluation/test_target_config.py -q
  ```
- **完成定义**: 契约测试通过；fake adapter 可跑通；Manifest 记录版本。
- **预估**: M

### 详细任务卡：EVL-14 声明式 HTTP / OpenAI 适配器

- **Agent**: `agent-eval`
- **目标**: 让 70% 的 Agent 通过配置接入，无需写代码。
- **输入**: EVL-13、`agent-integration.md` 第 7 节
- **输出**:
  - `targets/http_json.py`：请求模板 + JSONPath/JMESPath 映射
  - `targets/openai_compat.py`：OpenAI 兼容适配
  - 配置示例与文档
- **依赖**: EVL-13
- **验收条件**:
  1. 配置可定义 method/headers/body/response mapping/auth/timeout/retry/reset。
  2. 模板变量白名单；禁止任意表达式执行。
  3. 响应映射支持 output/trace_id/usage/finish_reason。
  4. 原始响应保存到 artifact（`raw_ref`）。
  5. 429/5xx/超时按策略重试，最终明确错误。
- **测试用例**:
  - 契约：OpenAI 兼容请求/响应
  - 契约：自定义 JSON 映射
  - IT：429/超时/大响应/Unicode
  - SEC：模板注入/secret 泄露
- **执行步骤**:
  1. 实现模板渲染（白名单变量）。
  2. 实现 JSONPath/JMESPath 映射。
  3. 实现认证与 secret 引用。
  4. 保存原始响应。
  5. 写 conformance 用例。
- **禁止**: 执行任意表达式；在配置里存明文密钥；不保存原始响应。
- **验证命令**:
  ```bash
  pytest backend/tests/contract/evaluation/test_http_adapter.py -q
  pytest backend/tests/integration/evaluation/test_openai_adapter.py -q
  ```
- **完成定义**: A/B 模式配置即可跑通；原始响应可重放。
- **预估**: M

### 详细任务卡：EVL-16 适配器一致性 + Record/Replay

- **Agent**: `agent-qa`
- **目标**: 所有适配器通过同一套测试；评测与调用解耦，支持只重算不重跑。
- **输入**: EVL-14、EVL-15、`edge-cases.md`
- **输出**:
  - `tests/conformance/adapters/`：统一测试套件
  - `targets/replay.py`：从 artifact 读取原始响应
  - Manifest 增加 `adapter_version` / `target_config_version` / `mode`
- **依赖**: EVL-14、EVL-15
- **验收条件**:
  1. 任一适配器上线前必须通过 conformance suite。
  2. Replay 模式不调用 Agent，只读 `raw_ref` 重新打分。
  3. Record 与 Replay 结果可区分；Replay 结果标注 `mode=replay`。
  4. 版本不一致时，对比标记 `not_comparable`。
  5. Replay 成本接近 0（仅 Judge/规则计算）。
- **测试用例**:
  - 契约：所有适配器跑同一套 conformance
  - IT：Record → Replay → 指标一致
  - IT：Replay 不产生外部调用
  - IT：版本不一致 → `not_comparable`
- **执行步骤**:
  1. 抽取 conformance 测试夹具。
  2. 实现 Replay 读取与打分。
  3. 扩展 Manifest 字段。
  4. 写版本兼容测试。
- **禁止**: Replay 时重新调用 Agent；用 Replay 结果冒充 Record；跳过版本校验。
- **验证命令**:
  ```bash
  pytest backend/tests/conformance/adapters -q
  pytest backend/tests/integration/evaluation/test_replay.py -q
  ```
- **完成定义**: 所有适配器通过；Replay 零调用；版本校验生效。
- **预估**: M

---

## M09 gate

### 模块职责

门禁规则、基线对比、判定与证据。只读评测结果，不修改。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| GAT-01 | Gate/Rule 模型 | EVL-04 | `gate`、`gate_rule` | EVL-04 | 规则可组合；版本化 | UT：规则模型 | agent-eval |
| GAT-02 | 判定引擎 | GAT-01、EVL-09 | 规则求值、结果 | GAT-01、EVL-09 | 结果确定；可解释 | UT：规则矩阵；IT：端到端 | agent-eval |
| GAT-03 | 基线集成 | GAT-02 | 基线选择、冻结 | GAT-02 | 基线不可变；可追溯 | IT：基线对比 | agent-eval |
| GAT-04 | 结果与证据 | GAT-02 | `gate_result`、证据链接 | GAT-02 | 每条规则有 expected/actual | IT：证据可下钻 | agent-eval |
| GAT-05 | 门禁测试 | GAT-02~04 | 误拦/漏拦测试 | GAT-02~04 | 误拦 <5%；漏拦有告警 | IT：阈值边界 | agent-qa |

### 详细任务卡：GAT-02 判定引擎

- **Agent**: `agent-eval`
- **目标**: 把「指标是否劣化」变成可解释、可复现、可审计的判定。
- **输入**: GAT-01、EVL-09、EVL-05
- **输出**: `evaluate_gate(run_id, gate_id) -> GateResult`
- **依赖**: GAT-01、EVL-09
- **验收条件**:
  1. 支持：绝对阈值、相对基线、统计显著性、样本量下限。
  2. 样本量不足时返回 `insufficient_data`，不判定通过。
  3. 每条规则输出 `expected` / `actual` / `passed` / `evidence_ref`。
  4. 判定结果绑定 `manifest_hash`；Manifest 不可复现则拒绝判定。
  5. 误拦率可观测。
- **测试用例**:
  - UT：规则矩阵（通过/不通过/数据不足）
  - IT：端到端 Run → GateResult
  - IT：样本量不足 → 不通过
  - SEC：跨租户 Gate → NotFound
- **禁止**: 用平均值掩盖长尾；无样本量提示；修改历史判定。
- **验证命令**:
  ```bash
  pytest backend/tests/unit/gate/test_rules.py -q
  pytest backend/tests/integration/gate/test_evaluate.py -q
  ```
- **完成定义**: 规则矩阵全绿；证据可下钻。
- **预估**: M

---

## M08 reporting

### 模块职责

读模型、报告生成、对比报告、导出、快照。只读，不写业务表。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| REP-01 | 读模型 | EVL-08 | `read_model_*` / 物化视图 | EVL-08 | 查询 P95 <300ms；不跨模块 JOIN | IT：读模型刷新 | agent-eval |
| REP-02 | Run 报告 | REP-01 | `report_snapshot`、Markdown/JSON | REP-01 | 内容与 Run 一致；可分享 | IT：报告生成 | agent-eval |
| REP-03 | 对比报告 | REP-01、EVL-09 | 对比表、劣化 Top N | REP-01、EVL-09 | 差异可解释 | IT：对比报告 | agent-eval |
| REP-04 | 导出 | REP-02 | JSON/CSV/JUnit | REP-02 | 格式正确；大数据流式导出 | IT：导出校验 | agent-eval |
| REP-05 | 快照与分享链接 | REP-02、AST-01 | 快照、签名链接 | REP-02、AST-01 | TTL 可控；不可枚举 | SEC：链接越权 | agent-eval |

---

## 交付检查

- [ ] JOB-01 ~ JOB-06 完成
- [ ] MGW-01 ~ MGW-05 完成
- [ ] EVL-01 ~ EVL-12 完成
- [ ] GAT-01 ~ GAT-05 完成
- [ ] REP-01 ~ REP-05 完成
- [ ] Manifest 重放 5 次一致
- [ ] 1000 条评测基准达标
- [ ] Judge 校准 κ ≥ 0.7
- [ ] 门禁误拦率 < 5%
