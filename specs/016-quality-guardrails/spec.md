# Feature Specification: 质量护栏（P0q）

**Feature**: `003-quality-guardrails` | **Phase**: P0q | **Status**: Implemented

**覆盖范围**: 跨模块（架构、契约、可复现、数据演进、运行、边界）

**任务卡**: `docs/planning/tasks/05-quality.md`（QUAL-01 ~ QUAL-05）

---

## 1. 为什么做

平台的正确性不能依赖人工记忆。把架构边界、契约、可复现、迁移、运行与边界场景写成 CI 硬门禁，才能防止“接口悄悄漂移、结果不可复现、迁移无法回滚”。

MCP 特性已经落地了部分基础：CI、架构边界测试、迁移 `up/down/up`、受限账号验证、契约快照。本规格负责把护栏扩展到全部模块。

## 2. 功能需求

- **FR-001 架构与契约护栏**：跨模块内部 import、循环依赖、业务模块 import `app.api` 必须让 CI 失败；`public.py`、OpenAPI、MCP `tools.yaml` 必须有快照；前端类型必须由 OpenAPI 生成。
- **FR-002 可复现护栏**：同一 Manifest 重放 5 次结果一致；Judge 结果差 ≤0.05；Judge 校准 κ ≥0.7 才能用于门禁；数据集版本不可变。
- **FR-003 数据演进护栏**：迁移必须 `up → down → up`；破坏性 DDL 必须显式豁免；N-1 应用兼容；季度恢复演练。
- **FR-004 运行与迭代护栏**：四张看板（队列/错误/延迟/成本）；三个 kill switch（模型/评测/MCP）；灰度与回滚 Runbook；技术债账本；依赖安全更新；DORA 指标。
- **FR-005 边界与异常路径套件**：覆盖 `docs/architecture/edge-cases.md` 的 14 类场景；P0/P1 场景 100% 自动化；CI <10 分钟；无外部依赖（fake/容器）。
- **FR-006 权限**：架构/契约/迁移/越权测试在 CI 中是**阻断**而非告警。

## 3. 验收场景

1. **Given** 临时加入 `from app.modules.evaluation.models import Run`，**When** CI 运行，**Then** 架构测试失败。
2. **Given** 修改 `public.py` 签名但未升版本，**When** CI 运行，**Then** 契约快照失败。
3. **Given** 同一 Manifest 重放 5 次，**When** 比较指标，**Then** 规则评分 100% 一致，Judge 差 ≤0.05。
4. **Given** 一个破坏性迁移，**When** 未提供豁免与回滚，**Then** CI 失败。
5. **Given** 14 类边界场景，**When** 运行 `edge-suite`，**Then** 全部自动化且 <10 分钟。
6. **Given** 修改 OpenAPI，**When** 前端未重新生成类型，**Then** CI 失败。

## 4. 现有基础与缺口

| 能力 | 现状 | 缺口 |
|---|---|---|
| CI | MCP 的 `.github/workflows/ci.yml` 已存在 | 需加入 QUAL-01~05 的全部 Job |
| 架构测试 | `tests/architecture` 已有模块边界 | 需覆盖 `app.api`、`public.py` 快照 |
| 契约快照 | MCP `tools.yaml` 快照已有 | OpenAPI/前端类型快照未建 |
| 迁移往返 | MCP CI 已有 | 破坏性 DDL/N-1/恢复演练未建 |
| 可复现 | MCP 无 Run 概念 | EVL-05/10 完成后接入 |
| 运行护栏 | MCP 告警规则已有 | 看板/kill switch/技术债账本未建 |
| 边界套件 | 部分 MCP 用例 | 14 类完整矩阵未建 |

## 5. 不在范围

- 具体业务功能实现。
- 生产环境的具体监控平台选型（Prometheus/Grafana 为默认）。

## 6. 依赖

CORE-01、CORE-06、CORE-07、EVL-05、EVL-10、EVL-03、CAT-03、OBS-03、OBS-05。可与其他阶段并行，但完整门禁需在对应模块完成后启用。
