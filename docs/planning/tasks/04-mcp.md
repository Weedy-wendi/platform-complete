# P0c 任务卡：MCP 只读接入

**覆盖模块**: M13 mcp

**负责 Agent**: `agent-mcp`、`agent-qa`

**关联文档**: `docs/adr/ADR-005-mcp-access-layer.md`、`specs/001-mcp-server/{spec,plan,research,data-model,quickstart}.md`、`specs/001-mcp-server/contracts/`

**通用协议**: 按 `docs/planning/subagent-protocol.md` 执行。

> 本文件是任务卡；执行状态以 `specs/001-mcp-server/tasks.md` 与 `docs/planning/task-index.md` 为准；不要在此维护 T 状态。

---

## M13 mcp

### 模块职责

Streamable HTTP 协议适配、API Key 认证、OAuth 预留、10 个只读工具、3 个 Resource、限流、审计、错误映射。不实现业务逻辑，不注册写工具。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| MCP-01 | 模块骨架/配置/CLI | `plan.md`、`module-conventions.md`、宪法 MCP 章节 | `app/mcp/**`、`pingce mcp serve`、配置项 | CORE-02 | 进程可启动；`/healthz` 可访问；配置缺失启动失败 | 冒烟：启动/健康检查 | agent-mcp |
| MCP-02 | AuthProvider + API Key | ADR-005、`data-model.md`、IDN-03 | `auth/base.py`、`auth/api_key.py`、`Principal` | MCP-01、IDN-03 | 401/403 正确；HMAC 校验；吊销 ≤60s（含时间断言）；scope 生效 | UT/IT/SEC：认证矩阵 + 时钟注入 | agent-mcp |
| MCP-03 | OAuth 预留 | ADR-005 | `auth/oauth_stub.py`、配置开关、metadata 端点 | MCP-02 | 切换不成功则启动失败；工具代码零改动 | IT：fake provider | agent-mcp |
| MCP-04 | 工具注册表/allowlist | `contracts/tools.yaml`、`plan.md` | `registry.py`、scope 映射、启动断言 | MCP-01 | 仅 10 个只读工具；快照一致；四个 annotation 全部匹配；未知工具启动失败 | 契约：快照；SEC：无写工具 | agent-mcp |
| MCP-05 | 游标/限额/脱敏 | `research.md`、`contracts/tools.yaml` | `cursor.py`、`limits.py` | MCP-01、AST-01 | 64KB/4KB/20/100 上限；游标签名/TTL；脱敏 | UT/IT：游标/限额/脱敏 | agent-mcp |
| MCP-06 | 限流 | `research.md` | Redis 令牌桶、本地兜底 | MCP-01 | Key/Tenant/重工具三级；429+Retry-After；Redis 故障本地兜底；功能测试 | IT：阈值/降级/429 | agent-mcp |
| MCP-07 | 审计 | AUD-01、`data-model.md` | `audit.py`、`mcp_tool_call` 写入 | MCP-01、AUD-01 | 100% 覆盖；无参数/PII；日志不含完整 Key/Prompt/样本；失败不阻塞 | IT：覆盖/失败/脱敏 | agent-mcp |
| MCP-08 | 错误/可观测/健康 | `contracts/errors.md`、OBS-02 | `errors.py`、`observability.py`、`/healthz`、`/readyz` | MCP-01、OBS-02 | 错误映射完整；trace_id；readiness 检查 DB/Redis | IT：错误矩阵/健康 | agent-mcp |
| MCP-09 | 协议装配 | MCP-02/04/05/06/07/08、`research.md` | `server.py`：initialize/tools/list/tools/call/resources | MCP-02/04/05/06/07/08 | MCP Inspector/curl 可连通；无状态；版本协商 | 契约：握手/列表/调用 | agent-mcp |
| MCP-10 | 数据集工具 | MCP-09、CAT-05、`contracts/tools.yaml` | `tools/projects.py`、`tools/datasets.py` | MCP-09、CAT-05 | 4 个工具符合契约；租户过滤；分页/脱敏 | IT/SEC：数据集工具 | agent-mcp |
| MCP-11 | 评测工具 | MCP-09、EVL-08/09 | `tools/evaluation.py` | MCP-09、EVL-08/09 | 4 个工具；默认无 IO；`include_io` 需 scope | IT/SEC：评测工具 | agent-mcp |
| MCP-12 | Badcase/Gate 工具 | MCP-09、GAT-04、SRC-05 | `tools/badcases.py` | MCP-09、GAT-04、SRC-05 | 调用 `SemanticSearch` / `GateReader`；MCP 内不实现检索/门禁；依赖未就绪返回 `UPSTREAM_UNAVAILABLE`；租户过滤 | IT：降级/门禁 | agent-mcp |
| MCP-13 | Resources | MCP-09、CAT-05、REP-02 | `resources/datasets.py`、`reports.py` | MCP-09、CAT-05、REP-02 | `resources/list` / `resources/read` 可用；3 个 Resource；scope；大对象不塞 tool result | IT：读取/越权/大小 | agent-mcp |
| MCP-14 | 安全测试 | MCP-10~13 | `tests/security/mcp/` | MCP-10~13 | 跨租户 100% 拒绝；无写工具；DB 授权生效；日志无泄露 | SEC：全套 | agent-qa |
| MCP-15 | 压测与部署 | MCP-14 | 压测报告、compose、ingress、看板、runbook | MCP-14 | 50 QPS×30min；P95 达标；无 5xx；优雅停机；可回滚 | PERF/冒烟/停机 | agent-qa |

---

### 详细任务卡：MCP-02 AuthProvider + API Key

- **Agent**: `agent-mcp`
- **目标**: 用 API Key 完成 HTTP MCP 认证，同时把 OAuth 作为可替换实现预留。
- **输入**:
  - `docs/adr/ADR-005-mcp-access-layer.md`
  - `specs/001-mcp-server/data-model.md`
  - `specs/001-mcp-server/spec.md` FR-005 ~ FR-010
  - `IDN-03` 的 `ApiKeyVerifier`
- **输出**:
  - `app/mcp/auth/base.py`：`Principal`、`AuthProvider` 协议
  - `app/mcp/auth/api_key.py`：Bearer 解析、HMAC 校验、缓存
  - `app/mcp/auth/factory.py`：`MCP_AUTH_MODE` 工厂
- **依赖**: MCP-01、IDN-03
- **验收条件**:
  1. `Authorization: Bearer pk_...` 可认证；缺失/格式错误 → 401。
  2. 过期、吊销、未知 key_id → 统一 401，不泄露原因。
  3. scope 不足 → 403，并返回 `required_scope`。
  4. Principal 含 `tenant_id`、`subject`、`scopes`、`auth_method`、`expires_at`。
  5. 吊销后 ≤ 60 秒生效（缓存 TTL）。
  6. 业务工具代码不直接读取 `Authorization` 头。
- **测试用例**:
  - UT：Bearer 解析、HMAC 常量时间比较
  - IT：有效 Key → 200；过期/吊销/未知 → 401
  - SEC：scope 不足 → 403；跨租户 → 403/404
  - SEC：日志/审计不含完整 Key
- **执行步骤**:
  1. 定义 `Principal` 与 scope 常量。
  2. 复用 `ApiKeyVerifier`，不要重复实现 HMAC。
  3. 实现缓存与失效。
  4. 实现 FastAPI/Starlette 认证依赖。
  5. 写认证矩阵测试。
- **禁止**: 在 MCP 模块重复实现 Key 校验；把 Key 写入日志；使用通配 scope；信任客户端自报租户。
- **验证命令**:
  ```bash
  pytest backend/tests/unit/mcp/test_auth_api_key.py -q
  pytest backend/tests/integration/mcp/test_auth_matrix.py -q
  pytest backend/tests/security/mcp/test_auth_leak.py -q
  ```
- **完成定义**: 认证矩阵全绿；OAuth 工厂可切换；README 更新。
- **预估**: M

---

### 详细任务卡：MCP-04 工具注册表/allowlist

- **Agent**: `agent-mcp`
- **目标**: 保证 MCP 永远只暴露 10 个只读工具，任何写工具都无法注册。
- **输入**:
  - `specs/001-mcp-server/contracts/tools.yaml`
  - `specs/001-mcp-server/plan.md`（只读三层保障）
- **输出**:
  - `app/mcp/registry.py`：工具元数据、scope 映射、handler 绑定
  - 启动断言：注册表 ⊆ allowlist
  - `tests/contract/test_tools_snapshot.py`
- **依赖**: MCP-01
- **验收条件**:
  1. 工具名集合与 `tools.yaml` 完全一致（10 个）。
  2. 每个工具 `readOnlyHint=true`、`destructiveHint=false`。
  3. 注册任何不在 allowlist 的工具 → 进程启动失败。
  4. 工具名包含 `create/update/delete/start/cancel/run` 等写动词 → CI 失败。
  5. `tools/list` 输出与契约快照一致。
- **测试用例**:
  - 契约：`tools/list` 快照
  - UT：注册未知工具 → 启动异常
  - SEC：断言无写工具
  - UT：scope 映射完整
- **执行步骤**:
  1. 定义 `ToolSpec`（name/version/scopes/input/output/handler）。
  2. 从 `tools.yaml` 生成或手写元数据，二者必须一致。
  3. 实现启动断言与快照测试。
  4. 加 CI 检查。
- **禁止**: 动态扫描装饰器自动注册（难以审计）；允许运行时注册；工具名使用写动词。
- **验证命令**:
  ```bash
  pytest backend/tests/contract/test_tools_snapshot.py -q
  pytest backend/tests/unit/mcp/test_registry_allowlist.py -q
  ```
- **完成定义**: 快照测试通过；写工具无法注册；契约同步。
- **预估**: S

---

### 详细任务卡：MCP-09 协议装配

- **Agent**: `agent-mcp`
- **目标**: 按 MCP `2025-06-18` 实现 Streamable HTTP 服务端，完成握手、工具调用与资源读取。
- **输入**:
  - `research.md`（协议事实、SDK 选择）
  - `contracts/tools.yaml`、`contracts/errors.md`
  - MCP-02/04/05/06/07/08 的产物
- **输出**:
  - `app/mcp/server.py`
  - `app/cli/mcp.py`（`pingce mcp serve --http`）
  - 路由：`POST /mcp`、`GET /healthz`、`GET /readyz`
- **依赖**: MCP-02/04/05/06/07/08
- **验收条件**:
  1. `initialize` 返回协议版本、`serverInfo`、`capabilities.tools/resources`。
  2. `notifications/initialized` 正常处理。
  3. `tools/list` 返回 10 个工具；`tools/call` 正确路由。
  4. `resources/list` / `resources/read` 可用。
  5. 无状态；不依赖 `Mcp-Session-Id` 粘滞。
  6. `MCP-Protocol-Version` 不支持 → 明确错误。
  7. 非法 JSON-RPC → 正确错误码。
- **测试用例**:
  - 契约：initialize / tools list / tools call
  - 契约：resources read
  - IT：协议版本不支持
  - IT：畸形 JSON / 未知方法
  - 冒烟：MCP Inspector 或 curl
- **执行步骤**:
  1. 用官方 `mcp` SDK 低层 Server 显式注册工具。
  2. 接入认证、限流、审计、错误映射。
  3. 实现 Starlette 应用与 CLI。
  4. 写契约测试夹具。
- **禁止**: 使用装饰器隐式扫描；引入会话粘滞；在协议层写业务逻辑；返回堆栈。
- **验证命令**:
  ```bash
  pytest backend/tests/contract/mcp/test_initialize.py -q
  pytest backend/tests/contract/mcp/test_tools_list.py -q
  pytest backend/tests/integration/mcp/test_protocol_errors.py -q
  ```
- **完成定义**: 契约测试全绿；MCP Inspector 可连接；quickstart 可复现。
- **预估**: L

---

### 详细任务卡：MCP-10 数据集工具

- **Agent**: `agent-mcp`
- **目标**: 交付 `list_projects`、`search_datasets`、`get_dataset_schema`、`preview_samples` 四个只读工具。
- **输入**:
  - `contracts/tools.yaml`
  - `CAT-05` 的 `CatalogReader`
  - MCP-05 的游标/限额/脱敏
- **输出**:
  - `app/mcp/tools/projects.py`
  - `app/mcp/tools/datasets.py`
- **依赖**: MCP-09、CAT-05
- **验收条件**:
  1. 四个工具的输入/输出与契约一致。
  2. 所有查询强制租户过滤；跨租户返回 NotFound。
  3. 列表工具使用签名游标；页大小上限生效。
  4. `preview_samples` ≤ 20 条、单条 ≤ 4KB、PII 脱敏。
  5. 结果 > 64KB → 截断 + `next_cursor` 或 `RESULT_TOO_LARGE`。
  6. 样本中的指令文本仅作为数据返回，不触发任何动作。
- **测试用例**:
  - IT：四个工具正常路径
  - SEC：跨租户 403/404
  - IT：游标翻页、篡改、过期
  - IT：大结果截断
  - SEC：PII 脱敏、注入文本
- **执行步骤**:
  1. 为每个工具定义 Pydantic 输入/输出模型。
  2. 调用 `CatalogReader`，不直接查表。
  3. 统一走游标/限额/脱敏中间件。
  4. 写集成与安全测试。
- **禁止**: 直接 SQL；绕过 `CatalogReader`；返回未脱敏样本；无上限分页。
- **验证命令**:
  ```bash
  pytest backend/tests/integration/mcp/test_dataset_tools.py -q
  pytest backend/tests/security/mcp/test_dataset_isolation.py -q
  ```
- **完成定义**: 四个工具契约测试通过；越权/脱敏/限额测试通过。
- **预估**: L

### 详细任务卡：MCP-12 Badcase/Gate 工具

- **Agent**: `agent-mcp`
- **目标**: 交付 `search_badcases` 与 `check_gate`，但所有检索与门禁逻辑委托给 `search` / `gate` 模块。
- **输入**:
  - `specs/001-mcp-server/contracts/tools.yaml`
  - `SRC-05` 的 `SemanticSearch`
  - `GAT-04` 的 `GateReader`
- **输出**:
  - `app/mcp/tools/badcases.py`
- **依赖**: MCP-09、SRC-05、GAT-04
- **验收条件**:
  1. `search_badcases` 只调用 `SemanticSearch`；MCP 内不得 import Qdrant 客户端。
  2. `check_gate` 只调用 `GateReader`；MCP 内不得实现规则求值。
  3. 依赖未就绪 → 返回 `UPSTREAM_UNAVAILABLE`，工具仍保持注册（10 工具契约稳定）。
  4. 租户过滤、分页、`degraded` 标注符合契约。
  5. 不注册任何写工具。
- **测试用例**:
  - IT：语义检索正常路径 + `degraded=true`
  - IT：依赖不可用 → `UPSTREAM_UNAVAILABLE`
  - SEC：跨租户 → 404
  - 契约：工具 I/O 与 `tools.yaml` 一致
- **执行步骤**:
  1. 定义 Pydantic 输入/输出模型。
  2. 注入 `SemanticSearch` / `GateReader`，不直接访问其数据源。
  3. 映射 `degraded` 与门禁证据。
  4. 写集成/依赖失败/越权测试。
- **禁止**:
  - 在 MCP 内实现向量检索、关键词降级或门禁规则
  - 直接 import `qdrant_client`
  - 依赖不可用时返回 5xx 或从 allowlist 移除工具
- **验证命令**:
  ```bash
  pytest backend/tests/integration/mcp/test_badcase_gate_tools.py -q
  pytest backend/tests/security/mcp/test_badcase_isolation.py -q
  ```
- **完成定义**: 契约/降级/依赖失败/越权测试通过；MCP 模块无检索/门禁实现。
- **预估**: M

---

## 交付检查

- [ ] MCP-01 ~ MCP-15 完成
- [ ] `tools/list` 快照与 `contracts/tools.yaml` 一致
- [ ] 无任何写工具
- [ ] 跨租户越权测试 100% 拒绝
- [ ] 数据库受限账号验证通过
- [ ] OAuth 切换测试通过（工具代码零改动）
- [ ] 50 QPS × 30 分钟压测通过
- [ ] quickstart 全流程可复现
- [ ] 看板/告警/回滚 runbook 就绪
