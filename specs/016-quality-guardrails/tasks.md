# Tasks: 质量护栏（P0q）

**Source of truth**: `docs/planning/task-index.md`；任务明细见 `docs/planning/tasks/05-quality.md`。

- [X] QUAL-01 架构与契约护栏（import-linter、AST、`public.py`/OpenAPI/`tools.yaml` 快照、前端类型生成）
- [X] QUAL-02 可复现护栏（重放 CI、Golden Set、Judge 校准、不可变版本）
- [X] QUAL-03 数据演进护栏（`up/down/up`、破坏性 DDL、N-1 兼容、恢复演练）
- [X] QUAL-04 运行与迭代护栏（四张看板、三个 kill switch、灰度/回滚、技术债账本、DORA）
- [X] QUAL-05 边界与异常路径测试套件（14 类；CI <10 分钟）

## 交付检查

- [X] 所有负例都能让 CI 失败
- [X] 契约快照纳入版本控制
- [X] 迁移回滚与恢复演练有记录
- [X] 看板、kill switch、回滚 Runbook 可用
- [X] `edge-suite` 覆盖 14 类场景

## Phase 2: Convergence

- [X] QUAL-06 ????? `tests/repro`??? 5 ??Judge ? <=0.05?kappa>=0.7???????FR-002?missing?
- [X] QUAL-07 N-1 ???????FR-003?partial?
- [X] QUAL-08 kill switch ?? model/evaluation/MCP ?????FR-004?partial?
- [X] QUAL-09 ?? 14 ????????FR-005?partial?
- [X] QUAL-10 ?? Grafana ?? + ?????? + ?? Runbook?FR-004?partial?
