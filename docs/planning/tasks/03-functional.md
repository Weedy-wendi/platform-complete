# P2 任务卡：可视化功能测试

**覆盖模块**: M12 functional

**负责 Agent**: `agent-functional`、`agent-qa`

**通用协议**: 按 `docs/planning/subagent-protocol.md` 执行。

---

## M12 functional

### 模块职责

用例与套件、API/UI 执行、断言、视觉差异、证据采集。与评测域共享 `Evidence` / `Run` / `Gate` 抽象，但不复用 evaluation 的表。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| FUN-01 | 用例/套件模型 | CORE-03 | `test_case`、`test_suite`、`test_run`、`test_step` | CORE-03 | 版本化；租户隔离；步骤可排序 | UT：模型；IT：迁移 | agent-functional |
| FUN-02 | API 断言执行器 | FUN-01、JOB-02 | HTTP 执行器、断言 DSL | FUN-01、JOB-02 | 支持状态码/JSONPath/耗时断言 | IT：正常/失败/超时 | agent-functional |
| FUN-03 | 浏览器沙箱执行 | FUN-01、JOB-02 | Playwright Worker、沙箱 | FUN-01、JOB-02 | 隔离；资源限制；超时强杀 | IT：崩溃/超时/内存 | agent-functional |
| FUN-04 | 视觉差异 | FUN-03、AST-01 | 截图对比、差异图 | FUN-03、AST-01 | 阈值可配；差异图可下钻 | IT：像素差异 | agent-functional |
| FUN-05 | 证据采集 | FUN-03、AST-03 | 截图/录屏/网络日志/trace | FUN-03、AST-03 | 证据完整；可回放 | IT：证据落库 | agent-functional |
| FUN-06 | 功能测试与安全测试 | FUN-02~05 | 集成/安全/稳定性测试 | FUN-02~05 | 端到端可复现 | 见任务卡 | agent-qa |

### 详细任务卡：FUN-03 浏览器沙箱执行

- **Agent**: `agent-functional`
- **目标**: 在隔离环境中执行浏览器用例，崩溃/超时不影响其他任务。
- **输入**: FUN-01、JOB-02、宪法沙箱条款
- **输出**: `browser_worker.py`、容器配置、资源限制
- **依赖**: FUN-01、JOB-02
- **验收条件**:
  1. 每个 Run 在独立容器/进程中执行，资源受限（CPU/内存/磁盘）。
  2. 网络默认禁止，按用例白名单放行。
  3. 超时强杀；崩溃自动重试一次，仍失败入 DLQ。
  4. 截图/录屏/console/network 写入 `artifact`。
  5. 浏览器版本锁定；镜像 digest 固定。
- **测试用例**:
  - IT：正常用例 → 证据完整
  - IT：页面卡死 → 超时强杀
  - IT：内存爆炸 → 容器限制生效
  - IT：网络白名单外请求 → 拒绝
- **执行步骤**:
  1. 定义执行器协议与容器配置。
  2. 实现 Playwright 执行与证据采集。
  3. 接入 Job 重试/超时/取消。
  4. 写故障注入测试。
- **禁止**: 在 API 进程内跑浏览器；无资源限制；默认放开全部网络；把视频存 MySQL。
- **验证命令**:
  ```bash
  pytest backend/tests/integration/functional/test_browser_worker.py -q
  pytest backend/tests/security/functional/test_sandbox.py -q
  ```
- **完成定义**: 崩溃/超时/隔离测试通过；证据可回放。
- **预估**: L

---

## 交付检查

- [ ] FUN-01 ~ FUN-06 完成
- [ ] 浏览器执行有沙箱与资源限制
- [ ] 视觉差异阈值可配
- [ ] 证据可在 Web 端下钻
- [ ] 与 evaluation 共享 Evidence 展示，不共享表
