# 子 Agent 任务执行协议（Sub-agent Protocol）

**版本**: 1.0.0 | **日期**: 2026-11-05 | **适用**: 所有由子 Agent 执行的 `docs/planning/tasks/*` 任务

本协议规定「接到一个任务后，子 Agent 应该怎么做到可验收」。任务卡只写差异，通用流程以本文件为准。

---

## 1. Agent 角色与所有权

| 角色 | 负责模块 | 典型任务 |
|---|---|---|
| `agent-core` | M00 core、M14 observability | 配置、DB 会话、错误模型、日志/Trace |
| `agent-identity` | M01 identity、M02 audit | 租户、RBAC、API Key、审计 |
| `agent-data` | M03 assets、M04 catalog、M05 ingestion | 存储、数据集、接入 |
| `agent-eval` | M06 evaluation、M07 jobs、M09 gate、M10 model_gateway、M08 reporting | 评测闭环、任务、门禁、报告 |
| `agent-search` | M11 search | Qdrant、Embedding、语义检索 |
| `agent-mcp` | M13 mcp | MCP 适配层 |
| `agent-functional` | M12 functional | 可视化功能测试 |
| `agent-qa` | 跨模块 | 契约测试、安全测试、压测、E2E |
| `agent-reviewer` | 跨模块 | 只读审查，不直接改代码 |

**所有权规则**：

- 同一模块同一时间只允许一个实现 Agent 修改。
- `agent-qa` 可以新增测试，但不得修改业务实现。
- `agent-reviewer` 只输出问题清单，修复由原 Agent 执行。
- 跨模块改动必须由协调者拆成多个任务，禁止一个 Agent 同时改两个模块的内部实现。

---

## 2. 任务卡契约

每个任务卡必须包含以下字段（缺失即视为任务未就绪）：

| 字段 | 说明 |
|---|---|
| ID | `MODULE-NN`，全局唯一 |
| 名称 | 动词开头，一句话 |
| 模块 / 阶段 | 属于哪个模块、哪个阶段 |
| 负责 Agent | 上表中的角色 |
| 目标 | 这个任务交付什么能力 |
| 输入 | 必读文档、依赖产物、契约文件 |
| 输出 | 新增/修改的文件、迁移、接口 |
| 依赖 | 必须先完成的任务 ID |
| 验收条件 | 可判定、可测试 |
| 测试用例 | 单元/集成/契约/安全/性能 |
| 执行步骤 | 该任务特有的步骤 |
| 禁止事项 | 该任务特有的红线 |
| 验证命令 | 可复制执行 |
| 完成定义 | DoD 勾选项 |
| 预估 | S / M / L |

---

## 3. 标准执行流程（10 步）

### Step 1：加载上下文

必读顺序：

1. 本任务卡
2. `docs/architecture/module-map.md`
3. `docs/architecture/module-conventions.md`
4. `.specify/memory/constitution.md`
5. 所属模块 `README.md`
6. 相关契约：`contracts/*.yaml`、`contracts/*.md`、ADR
7. 依赖任务的实际产物（代码/迁移/接口）

**禁止**在没有读依赖产物的情况下开始实现。

### Step 2：校验依赖

- 在 `docs/planning/task-index.md` 确认依赖任务状态为 Done。
- 若依赖未完成：停止，输出「阻塞报告」，不要用 mock 跨模块替代。
- 若依赖已完成但接口与任务卡不一致：停止，输出「契约冲突报告」，不要自行改契约。

### Step 3：建立工作区

```bash
git switch -c task/<TASK-ID>
# 或在 OpenCode 中创建 worktree
```

要求：

- 一个任务一个分支/worktree。
- 不与其他 Agent 共用工作区。
- 开工前 `git status` 必须干净。

### Step 4：读现有代码

- 读目标文件、相邻模块的 `public.py`、相关测试。
- 确认没有未提交的他人改动。
- 发现未知改动：不得覆盖、不得回滚，先报告。

### Step 5：先写失败测试（TDD）

顺序：

1. 单元测试（正常 + 边界 + 错误路径）
2. 集成测试（真实 MySQL/Redis，testcontainers）
3. 契约测试（公开接口 / API / MCP Schema）
4. 安全测试（跨租户、越权、注入）

**必须先运行并确认失败**，再写实现。测试通过后再补实现视为无效。

### Step 6：最小实现

- 只改本模块文件 + 本模块测试 + 本模块迁移。
- 不重构无关代码。
- 不引入新依赖（需先走供应链审查）。
- `public.py` 变更必须先更新 DTO/Protocol，再改调用方。
- 跨模块副作用走事件/Job，不同步调用写方法。

### Step 7：运行验证

```bash
# 通用
ruff check backend
ruff format --check backend
mypy backend/app
pytest backend/tests/unit/<module> -q
pytest backend/tests/integration/<module> -q
pytest backend/tests/contract/<module> -q
pytest backend/tests/security -q
lint-imports

# 涉及迁移
alembic upgrade head
alembic downgrade -1
alembic upgrade head

# 涉及 MCP
pytest backend/tests/contract/test_tools_snapshot.py -q
```

任何一项失败 → 回到 Step 5/6，不得跳过。

### Step 8：自审

按 `module-conventions.md` 的 Definition of Done 逐项打勾，并额外检查：

- [ ] 是否有跨模块内部 import？
- [ ] 是否有未处理的异常路径？
- [ ] 是否有硬编码租户/密钥/URL？
- [ ] 是否有日志泄露 PII/密钥/完整 Prompt？
- [ ] 是否有 N+1 或全表扫描？
- [ ] 是否有未登记的错误码？
- [ ] 是否有未更新的 README/契约？

### Step 9：交付报告

使用固定模板（见第 6 节），必须包含命令与输出片段。

### Step 10：更新任务状态

- 在 `docs/planning/task-index.md` 将任务标记为 Done/Blocked。
- 如有接口变更，更新 `CHANGELOG` 与相关契约。
- 通知依赖该任务的下游 Agent。

---

## 4. 文件所有权与并行规则

| 范围 | 允许修改 |
|---|---|
| 本模块 `app/modules/<module>/**` | ✅ |
| 本模块测试 `tests/**/<module>/**` | ✅ |
| 本模块迁移 | ✅ |
| 本模块 `README.md` | ✅ |
| 其他模块任何文件 | ❌（需新任务） |
| `app/core/**` | 仅 `agent-core` |
| `docs/architecture/**` | 仅协调者/评审者 |
| `contracts/**` | 仅契约负责人，且需 ADR |

并行条件：

- 两个任务修改的文件集合不相交。
- 两个任务不属于同一模块。
- 无依赖关系。
- 否则串行。

---

## 5. 阻塞与升级

| 情况 | 动作 |
|---|---|
| 依赖未完成 | 标记 Blocked，输出依赖 ID，不实现 |
| 契约冲突 | 标记 Blocked，列冲突点与 2 个选项 |
| 同一测试连续失败 2 次 | 停止，列 2–3 个方案 + 推荐项 + 风险 |
| 需要改其他模块 | 停止，申请协调者拆任务 |
| 需要新依赖 | 停止，提交供应链审查清单 |
| 需要改公共契约 | 停止，提 ADR |
| 发现安全漏洞 | 立即停止，私下报告，不在 PR 描述中写利用细节 |

**禁止**：为了让测试通过而删除测试、放宽断言、捕获异常后返回空值。

---

## 6. 交付报告模板

```markdown
## Handoff: <TASK-ID> <任务名>

- **状态**: Done / Blocked
- **分支/Worktree**: task/<TASK-ID>
- **摘要**: 一句话说明交付了什么

### 变更文件
- `path/to/file.py` — 说明
- `path/to/migration.py` — 说明

### 公开接口变更
- 无 / `CatalogReader.page_samples` 新增 `cursor` 参数（向后兼容）

### 测试
- 新增：`tests/integration/catalog/test_dataset_version.py`（8 个用例）
- 修改：无
- 结果：`8 passed in 1.2s`

### 验证证据
```text
$ ruff check backend
All checks passed!

$ pytest backend/tests/integration/catalog -q
8 passed in 1.2s
```

### 已知限制 / 风险
- 只读副本延迟未处理，留待 CAT-07

### 后续任务
- CAT-05 可以开始

### 需要协调者决策
- 无
```

---

## 7. 质量门禁（Reviewer 检查表）

- [ ] 任务卡字段完整，验收条件可测试
- [ ] 只改本模块文件
- [ ] 测试先失败后通过（有证据）
- [ ] 覆盖正常/边界/错误/越权路径
- [ ] 无跨模块内部 import
- [ ] 无循环依赖
- [ ] `public.py` 变更已记录
- [ ] 迁移可回滚
- [ ] 日志/指标已加且脱敏
- [ ] 错误码已登记
- [ ] 文档已更新
- [ ] 交付报告含命令与输出

---

## 8. 反模式（立即打回）

1. 「先实现，后补测试」
2. 「这个测试太难写，先跳过」
3. 「先 import 别的模块的 repository，后面再改」
4. 「先加个全局单例，后面再解耦」
5. 「异常先 catch 住，返回空列表」
6. 「为了跑通，先把 tenant 过滤去掉」
7. 「这个迁移不能回滚，先这样」
8. 「日志先打印完整请求，后面再脱敏」
9. 「依赖没完成，我先 mock 一下」
10. 「接口对不上，我直接改契约」
