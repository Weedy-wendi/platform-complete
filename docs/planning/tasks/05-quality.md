# 质量护栏任务卡：QUAL-01 ~ QUAL-04

**覆盖范围**: 跨模块（架构、契约、可复现、数据演进、运行）

**负责 Agent**: `agent-core`、`agent-qa`、`agent-eval`

**关联文档**: `docs/architecture/maintainability.md`、`constitution.md` v1.4.0、`subagent-protocol.md`

**通用协议**: 按 `docs/planning/subagent-protocol.md` 执行。

---

## 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| QUAL-01 | 架构与契约护栏 | `module-map.md`、`module-conventions.md`、`public.py`、OpenAPI、`tools.yaml` | import-linter 配置、AST 架构测试、契约快照、类型生成校验 | CORE-01、CORE-06 | 跨模块内部 import / 循环依赖 / 契约漂移 / 手写类型 → CI 阻断 | 架构负例、契约快照、类型 diff | agent-qa |
| QUAL-02 | 可复现护栏 | EVL-05、EVL-10、EVL-03、CAT-03 | 重放 CI Job、Golden Set、Judge 校准门禁、不可变测试 | EVL-10、EVL-03、CAT-03 | 重放 5 次规则 100%；Judge 差 ≤0.05；κ ≥0.7；版本不可变 | 重放、校准、不可变、漂移 | agent-qa |
| QUAL-03 | 数据演进护栏 | 迁移脚本、`data-model.md`、宪法 MySQL 规则 | 迁移回滚 CI、破坏性 DDL 检查、N-1 兼容测试、恢复演练 Runbook | CORE-07 | up/down/up 通过；破坏性 DDL 需豁免；N-1 兼容；季度演练 | 迁移往返、破坏性检查、恢复演练 | agent-core |
| QUAL-04 | 运行与迭代护栏 | OBS-03、OBS-05、发布流程、维护指标 | 四张看板、三个 kill switch、灰度/回滚 Runbook、技术债账本、依赖自动化、DORA 指标 | OBS-03、OBS-05 | 看板可用；开关可切；回滚演练；债账本；20% 预算 | 开关切换、回滚演练、告警测试 | agent-core |
| QUAL-05 | 边界与异常路径测试套件 | `edge-cases.md`、各模块 | `tests/edge/`、表驱动夹具、CI Job `edge-suite` | CORE-07、QUAL-01 | P0/P1 场景 100% 自动化；14 类全覆盖；无外部依赖；CI <10 分钟 | 表驱动、故障注入、越权 | agent-qa |

---

## QUAL-01 架构与契约护栏

- **Agent**: `agent-qa`（架构测试与契约测试部分由 `agent-core` 提供支持）
- **目标**: 让「跨模块乱 import」「契约悄悄改」「前端手写类型」在 CI 阶段直接失败。
- **输入**:
  - `docs/architecture/module-map.md`
  - `docs/architecture/module-conventions.md`
  - 各模块 `public.py`
  - `specs/001-mcp-server/contracts/tools.yaml`
  - OpenAPI 导出文件
- **输出**:
  - `backend/pyproject.toml` 的 `import-linter` 契约
  - `backend/tests/architecture/test_module_boundaries.py`
  - `backend/tests/contract/test_public_interfaces.py`
  - `backend/tests/contract/test_openapi_snapshot.py`
  - `backend/tests/contract/test_tools_snapshot.py`
  - 前端 `openapi-typescript` 生成校验脚本
- **依赖**: CORE-01、CORE-06
- **验收条件**:
  1. 跨模块 import `models` / `repository` / `service` → CI 失败。
  2. 循环依赖 → CI 失败。
  3. `public.py` 删除/改名/改签名未升版本 → CI 失败。
  4. OpenAPI 或 `tools.yaml` 与实现不一致 → CI 失败。
  5. 前端存在手写 API 镜像类型 → CI 失败。
  6. 架构 + 契约测试总时长 < 5 分钟。
- **测试用例**:
  - 架构负例：临时注入 `from app.modules.evaluation.models import Run` → 必须失败
  - 架构负例：临时制造循环依赖 → 必须失败
  - 契约：`public.py` 快照 diff
  - 契约：OpenAPI 快照 diff
  - 契约：MCP `tools/list` 快照 diff
  - 类型：`openapi-typescript` 生成后再 diff，必须无变化
- **执行步骤**:
  1. 配置 `import-linter` 分层与禁止契约。
  2. 编写 AST 测试，检查跨模块 import 只允许 `.public`。
  3. 为每个模块 `public.py` 建立快照。
  4. 导出 OpenAPI，与快照比对。
  5. 校验 MCP `tools/list` 与 `tools.yaml` 一致。
  6. 前端 CI 增加类型生成 + diff。
- **禁止**:
  - 用 `# noqa` 绕过架构检查
  - 把架构测试改成 `skip`
  - 契约变更只改快照不评审
  - 前端手写 `types/api.ts`
- **验证命令**:
  ```bash
  lint-imports
  pytest backend/tests/architecture -q
  pytest backend/tests/contract -q
  pnpm --dir frontend run gen:api && git diff --exit-code frontend/src/types/api.ts
  ```
- **完成定义**: 所有负例都能让 CI 失败；契约快照纳入版本控制；README 说明如何更新快照。
- **预估**: M

---

## QUAL-02 可复现护栏

- **Agent**: `agent-qa`
- **目标**: 让「这次分数变化不可解释」无法合入。
- **输入**:
  - EVL-05（Manifest）
  - EVL-10（复现测试）
  - EVL-03（Judge）
  - CAT-03（不可变版本）
- **输出**:
  - `backend/tests/repro/test_manifest_replay.py`
  - `backend/tests/repro/test_dataset_immutability.py`
  - `backend/tests/repro/test_judge_stability.py`
  - `backend/tests/repro/test_judge_calibration_gate.py`
  - CI Job：`repro-gate`
- **依赖**: EVL-10、EVL-03、CAT-03
- **验收条件**:
  1. 同一 Manifest 重放 5 次，规则类指标 100% 一致。
  2. Judge 类指标同模型同版本重放，分数差 ≤ 0.05。
  3. 已发布数据集版本 UPDATE → 失败。
  4. Judge 与人工一致率 κ < 0.7 → 不允许进入门禁配置。
  5. 重放失败时，PR 必须附差异原因与版本变更说明。
- **测试用例**:
  - 重放：同 Manifest × 5 → 规则指标全等
  - 重放：Judge 分数差统计 ≤ 0.05
  - 不可变：UPDATE/DELETE 已发布版本 → 拒绝
  - 校准：κ 低于阈值 → 门禁配置被拒
  - 漂移：模拟模型版本变化 → 必须要求重冻结基线
- **执行步骤**:
  1. 建立最小 Golden Set（20–50 条）。
  2. 编写重放脚本与断言。
  3. 接入 CI，失败阻断合并。
  4. 增加 Judge 校准报告与阈值检查。
  5. 记录每次重放的 Manifest 与结果。
- **禁止**:
  - 用随机采样做重放断言
  - 用平均值掩盖单条差异
  - 允许“这次先跳过”
  - 修改历史 Manifest 让测试通过
- **验证命令**:
  ```bash
  pytest backend/tests/repro -q
  pytest backend/tests/repro/test_manifest_replay.py -q --count=5
  ```
- **完成定义**: 重放/不可变/校准测试全绿；CI Job 生效；失败时有明确诊断信息。
- **预估**: L

---

## QUAL-03 数据演进护栏

- **Agent**: `agent-core`
- **目标**: 让数据库变更可控、可回滚、可恢复。
- **输入**:
  - 所有 Alembic 迁移
  - `specs/001-mcp-server/data-model.md`
  - 宪法 MySQL 12 条
- **输出**:
  - `backend/tests/migrations/test_roundtrip.py`
  - `backend/tests/migrations/test_destructive_ddl.py`
  - `backend/tests/compat/test_n_minus_one.py`
  - `docs/runbooks/db-restore.md`
  - 季度恢复演练记录模板
- **依赖**: CORE-07
- **验收条件**:
  1. 每个迁移 `upgrade head → downgrade -1 → upgrade head` 通过。
  2. 破坏性 DDL（DROP/TRUNCATE/改类型）必须显式标记并附豁免说明。
  3. N-1 应用版本可对 N schema 正常读写。
  4. 恢复演练可在 2 小时内完成并产出报告。
  5. 迁移执行时间超过阈值（如 30s）必须走在线 DDL 方案。
- **测试用例**:
  - 迁移往返：全量迁移链
  - 破坏性检查：无标记的 DROP → CI 失败
  - N-1 兼容：上一版本应用 + 当前 schema
  - 恢复演练：从备份 + binlog 恢复到指定时间点
- **执行步骤**:
  1. 编写迁移往返测试。
  2. 编写破坏性 DDL 静态检查。
  3. 建立 N-1 兼容测试环境。
  4. 编写恢复 Runbook。
  5. 完成第一次演练并记录耗时。
- **禁止**:
  - 一个迁移多个不相关 DDL
  - 无 `downgrade()`
  - 在业务高峰执行大表变更
  - 用“手工执行 SQL”替代迁移
- **验证命令**:
  ```bash
  alembic upgrade head
  alembic downgrade -1
  alembic upgrade head
  pytest backend/tests/migrations -q
  ```
- **完成定义**: 往返/破坏性/N-1 测试通过；恢复 Runbook 可执行；演练记录归档。
- **预估**: M

---

## QUAL-04 运行与迭代护栏

- **Agent**: `agent-core` + `agent-qa`
- **目标**: 让系统「发得出去、退得回来、看得见、债有人还」。
- **输入**:
  - OBS-03（指标）
  - OBS-05（告警）
  - 发布流程
  - 维护指标定义
- **输出**:
  - 四张看板：队列、Run 成功率、P95、成本
  - 三个 kill switch：Judge / 语义检索 / MCP
  - `docs/runbooks/release.md`、`docs/runbooks/rollback.md`
  - `docs/planning/tech-debt.md`（账本）
  - 依赖自动升级 PR + CVE 扫描
  - DORA 指标看板
- **依赖**: OBS-03、OBS-05
- **验收条件**:
  1. 四张看板可访问，数据延迟 < 1 分钟。
  2. 三个 kill switch 可在 1 分钟内生效，且有操作审计。
  3. 灰度发布：内部 → 10% → 全量，每步有观察窗口。
  4. 回滚演练可在 15 分钟内完成。
  5. 技术债账本每条有主人、利息、到期时间。
  6. 每季度 15–20% 容量用于还债。
  7. 依赖升级 PR 自动创建，CVE 高危阻断合并。
- **测试用例**:
  - 开关：切换 kill switch → 行为降级，恢复后正常
  - 回滚：发布后回滚 → 版本与数据一致
  - 告警：注入故障 → 告警在 5 分钟内触发
  - 债账本：字段完整性校验
- **执行步骤**:
  1. 建四张看板与告警规则。
  2. 实现三个 kill switch 与审计。
  3. 写发布/回滚 Runbook 并演练。
  4. 建技术债账本与季度评审。
  5. 接入依赖自动升级与 CVE 扫描。
- **禁止**:
  - 无回滚方案发布
  - 关闭告警“降噪”
  - 技术债只记不排期
  - 依赖长期不升级
- **验证命令**:
  ```bash
  pytest backend/tests/ops/test_kill_switches.py -q
  pytest backend/tests/ops/test_rollback.py -q
  ```
- **完成定义**: 看板/开关/Runbook/债账本/自动化全部就绪；完成一次回滚演练与一次故障注入。
- **预估**: L

### 详细任务卡：QUAL-05 边界与异常路径测试套件

- **Agent**: `agent-qa`
- **目标**: 把 `docs/architecture/edge-cases.md` 中所有 P0/P1 场景变成确定性、可重复的自动化测试，并在 CI 中阻断回归。
- **输入**:
  - `docs/architecture/edge-cases.md`
  - 各模块的 `public.py` 与测试夹具
  - `QUAL-01` 的契约测试基础设施
- **输出**:
  - `backend/tests/edge/`：按域拆分（data/eval/mcp/auth/storage/search/report/functional/security/general/ops）
  - `backend/tests/edge/fixtures/`：可控时钟、故障注入、fake provider/OSS/Qdrant
  - CI Job：`edge-suite`
  - `docs/architecture/edge-cases.md` 的覆盖状态列（可选）
- **依赖**: CORE-07、QUAL-01
- **验收条件**:
  1. `edge-cases.md` 中所有 P0/P1 场景都有对应用例，命名 `test_ec_<domain>_<id>_<scenario>`。
  2. 14 个分类每类至少 3 个用例。
  3. 测试不依赖真实 LLM / OSS / Qdrant；使用 fake 或 testcontainers。
  4. 无 `sleep`；时钟可注入；随机种子固定；可并行执行。
  5. CI `edge-suite` < 10 分钟，失败阻断合并。
  6. 新增边界场景必须先登记 `edge-cases.md`，再写测试。
- **测试用例**:
  - 数据域：空/单条/重复/超限/中断续传
  - 评测域：全失败/部分失败/超时/取消/超预算/不可比
  - MCP：401/403/404/429/协议错误/游标/限额/注入
  - 认证：跨租户/禁用租户/吊销/通配 scope
  - 存储：OSS 故障/checksum/路径穿越/引用缺失
  - 检索：Qdrant 故障降级/跨租户/模型切换
  - 报告门禁：无数据/样本不足/除零/不可比
  - 安全：SQL 注入/SSRF/Zip bomb/ReDoS/Prompt 注入
  - 通用：时区/NaN/Emoji/整数溢出
  - 运维：滚动发布/回滚/迁移失败
- **执行步骤**:
  1. 建 EC ID → 测试文件映射表。
  2. 先实现 P0 用例并确认失败。
  3. 补齐 fake/fixture（时钟、故障、限流）。
  4. 接入 CI Job，设置超时与并行。
  5. 每周补 P2/P3 用例。
- **禁止**:
  - 用真实外部服务跑边界测试
  - 用 `sleep` 等待
  - 对 P0 场景标 `skip`
  - 只测正常路径就宣称完成
  - 测试之间共享可变状态
- **验证命令**:
  ```bash
  pytest backend/tests/edge -q
  pytest backend/tests/edge -q -k "p0"
  pytest backend/tests/edge -q -n auto
  ```
- **完成定义**: P0/P1 全覆盖；14 类全覆盖；CI 通过；无 flaky；覆盖表更新。
- **预估**: L

---

## 交付检查

- [ ] QUAL-01 ~ QUAL-04 全部完成
- [ ] 架构、契约、重放、迁移、运行五类门禁在 CI 生效
- [ ] 所有门禁都有负例测试（证明会失败）
- [ ] 回滚与恢复各完成一次演练
- [ ] 技术债账本与季度预算生效
- [ ] 维护指标看板可访问
