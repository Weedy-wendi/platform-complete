# Implementation Plan: evaluation（M06）

**Feature**: `010-evaluation` | **Spec**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md)

## 1. 技术方案

- SQLAlchemy + Alembic；Run Manifest 规范化 JSON + `sha256`。
- Run 执行：Celery Handler；分页拉样本；并发调用 `TargetAdapter`/`ModelGateway`；逐条写 `run_item`/`score`。
- 统计：复用 `EVL-09` 置信区间/显著性；门禁消费。
- 适配器：`TargetAdapter`/`TraceSource` SPI + entry_points；HTTP/OpenAI 声明式适配；Replay 从 artifact 读原始响应。
- 成本：`model_call` 累计；预算熔断。

## 2. 数据模型

`evaluator`、`evaluator_version`、`metric`、`eval_suite`、`suite_version`、`target`、`run`、`run_item`、`score`、`judge_call`、`baseline`。

## 3. 公开接口

`EvaluationService`、`RunReader`、`TargetAdapter`、`TraceSource`、`RunManifest`、`ComparisonView`。

## 4. 测试策略

- 单元：Manifest 哈希、规则评分、统计、状态机。
- 集成：Run 端到端、单条失败、取消、重放 5 次、预算熔断。
- 契约：Adapter/Provider conformance；Record/Replay。
- 安全：跨租户、Adapter 无法访问 DB、模板注入。
- 性能：1000 条 Run <10 分钟。

## 5. 风险

| 风险 | 缓解 |
|---|---|
| 不可复现 | Manifest + 不可变版本 + 重放门禁 |
| Provider 漂移 | 适配器版本 + 契约测试 |
| 重复计费 | 幂等键 + model_call 唯一 |
| 长尾噪声 | 置信区间/显著性/样本量 |
| 大样本 OOM | 分页/流式/artifact |

## 6. 宪法检查

| 条款 | 落实 |
|---|---|
| I 可复现 | Manifest/哈希/重放 |
| II 五原语 | Run/Evidence |
| III API/CLI First | Service + REST |
| IV Boring Tech | Celery/LiteLLM |
| V 控制/执行分离 | Worker 执行 |
| VI 证据驱动 | 重放/校准/性能测试 |
| VII 模块化单体 | 独立模块 |
