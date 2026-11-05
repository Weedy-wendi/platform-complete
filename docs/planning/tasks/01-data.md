# P0b/P1 任务卡：数据域

**覆盖模块**: M04 catalog、M05 ingestion、M11 search

**负责 Agent**: `agent-data`、`agent-search`

**通用协议**: 按 `docs/planning/subagent-protocol.md` 执行。

---

## M04 catalog

### 模块职责

项目、数据源、数据集、不可变版本、样本、血缘。是评测与 MCP 的数据入口。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| CAT-01 | 项目 CRUD | CORE-03 | `project` 表、Service、API | CORE-03 | 租户隔离；软删除；名称租户内唯一 | UT：唯一性；IT：CRUD；SEC：跨租户 | agent-data |
| CAT-02 | 数据源模型与密钥引用 | CAT-01、AST-01 | `datasource` 表、`secret_ref` | CAT-01、AST-01 | 不存明文密钥；类型可扩展；连接测试 | IT：创建/连接测试；SEC：密文 | agent-data |
| CAT-03 | 数据集与不可变版本 | CAT-01、AST-03 | `dataset`、`dataset_version`、`content_hash` | CAT-01、AST-03 | 版本发布后不可变；同内容哈希去重 | UT：哈希；IT：不可变；SEC：隔离 | agent-data |
| CAT-04 | 样本批量写入 | CAT-03 | `sample` 表、批量写入、schema 校验 | CAT-03 | 10 万条可批量写入；部分失败回滚；行数一致 | IT：批量/去重/回滚；PERF：写入吞吐 | agent-data |
| CAT-05 | 目录查询接口 | CAT-03/04 | `public.CatalogReader` | CAT-03/04 | 检索/分页/Schema/预览；只读 | 契约：接口快照；IT：分页 | agent-data |
| CAT-06 | 数据血缘 | CAT-03 | `lineage_edge` 表、写入/查询 | CAT-03 | 记录上游/下游；可追溯 | IT：链路查询 | agent-data |
| CAT-07 | 目录测试 | CAT-03~06 | `tests/{unit,integration,security}/catalog/` | CAT-03~06 | 版本、隔离、分页、血缘全覆盖 | 见任务卡 | agent-qa |

### 详细任务卡：CAT-03 数据集与不可变版本

- **Agent**: `agent-data`
- **目标**: 数据集版本一经发布不可修改，内容哈希可复现，供评测与 MCP 引用。
- **输入**: `module-map.md`、`constitution.md`（可复现优先）、`data-model.md`
- **输出**:
  - `app/modules/catalog/models.py`：`dataset`、`dataset_version`
  - `service.py`：`create_dataset()`、`publish_version()`、`get_version()`
  - `public.py`：`DatasetVersionRef`、`CatalogReader`
- **依赖**: CAT-01、AST-03
- **验收条件**:
  1. `dataset_version` 发布后禁止 UPDATE；只能新建版本。
  2. `content_hash` 由样本内容规范化后计算；同内容重复发布返回已有版本。
  3. 版本号在数据集内单调递增，无空洞。
  4. 大文件样本走 `artifact` 引用，不直接入库。
  5. 所有查询强制 `tenant_id`。
- **测试用例**:
  - UT：内容规范化 → 哈希稳定
  - UT：同内容 → 返回已有版本
  - IT：发布后 UPDATE → 数据库/服务拒绝
  - IT：并发发布两个版本 → 版本号不冲突
  - SEC：租户 A 读取租户 B 版本 → NotFound
- **执行步骤**:
  1. 定义模型与迁移（唯一键 `(tenant_id, dataset_id, version)`）。
  2. 实现内容规范化与哈希。
  3. 实现发布事务：写样本 → 计算行数/哈希 → 插入版本 → 提交。
  4. 提供 `CatalogReader` 只读接口。
  5. 写测试并先确认失败。
- **禁止**: 允许原地更新版本；用时间戳当版本号；在版本表存样本正文。
- **验证命令**:
  ```bash
  pytest backend/tests/unit/catalog/test_dataset_version.py -q
  pytest backend/tests/integration/catalog/test_immutability.py -q
  pytest backend/tests/security/catalog/test_tenant_isolation.py -q
  ```
- **完成定义**: 测试全绿；迁移可回滚；`public.py` 评审通过。
- **预估**: L

### 详细任务卡：CAT-04 样本批量写入

- **Agent**: `agent-data`
- **目标**: 支持 10 万级样本高效、可回滚、可去重地写入。
- **输入**: CAT-03、MySQL 批量写入规范
- **输出**: `bulk_insert_samples()`、校验器、去重策略
- **依赖**: CAT-03
- **验收条件**:
  1. 10 万条样本在 5 分钟内写入（本地基准）。
  2. 任一条 schema 校验失败 → 整批回滚。
  3. 以 `(dataset_version_id, sample_key)` 去重；重复样本不报错但计数。
  4. 写入完成后 `row_count` 与实际行数一致。
  5. 单条 payload > 1MB → 走 artifact 引用。
- **测试用例**:
  - IT：10 万条批量写入 + 行数校验
  - IT：中途失败 → 回滚，无残留
  - IT：重复样本 → 去重计数正确
  - IT：非法 schema → 整批拒绝
  - SEC：跨租户写入 → 拒绝
- **执行步骤**:
  1. 实现分批 `executemany`（每批 1000–5000）。
  2. 写 schema 校验器。
  3. 实现去重键与计数。
  4. 实现事务边界与回滚。
  5. 跑基准并记录。
- **禁止**: 逐条 INSERT；在事务里做外部 IO；忽略部分失败。
- **验证命令**:
  ```bash
  pytest backend/tests/integration/catalog/test_bulk_insert.py -q
  pytest backend/tests/load/catalog/test_bulk_benchmark.py -q
  ```
- **完成定义**: 基准达标；回滚测试通过；无 N+1。
- **预估**: M

---

## M05 ingestion

### 模块职责

连接器、同步任务、Schema 推断/漂移、清洗、质检。把外部数据变成 catalog 的版本。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| ING-01 | Connector SPI | CAT-03 | `Connector` 协议、注册表 | CAT-03 | discover/read/cursor；可插拔 | 契约：fake connector | agent-data |
| ING-02 | CSV/JSONL 连接器 | ING-01、AST-01 | 本地/OSS 文件连接器 | ING-01 | 编码/分隔符/大文件流式读 | IT：UTF-8/GBK/大文件 | agent-data |
| ING-03 | REST 连接器 | ING-01 | HTTP 连接器 | ING-01 | 分页/鉴权/超时/重试 | IT：分页与超时 | agent-data |
| ING-04 | 同步任务与水位 | ING-02、JOB-02 | JobHandler、`sync_cursor` | ING-02、JOB-02 | 断点续传；不重复；可取消 | IT：续传/重复/取消 | agent-data |
| ING-05 | Schema 推断/漂移 | ING-04 | 推断器、漂移检测 | ING-04 | 新/删/改字段分别告警 | UT：推断；IT：漂移 | agent-data |
| ING-06 | 清洗规则 | ING-04 | 去重/脱敏/格式转换 | ING-04 | 规则可配置；可预览 | IT：规则生效 | agent-data |
| ING-07 | 质检规则与结果 | ING-04、CAT-03 | `quality_rule`、`quality_result` | ING-04、CAT-03 | 规则可配；结果可追 | IT：质检报告 | agent-data |
| ING-08 | 接入测试 | ING-02~07 | 集成/安全测试 | ING-02~07 | 端到端可复现 | 见任务卡 | agent-qa |

### 详细任务卡：ING-04 同步任务与水位

- **Agent**: `agent-data`
- **目标**: 让接入任务可中断、可续传、可重试，且不产生重复样本。
- **输入**: ING-02、JOB-02、CAT-03
- **输出**: `handlers.py` 的 `SyncDatasetHandler`、`sync_cursor` 表
- **依赖**: ING-02、JOB-02
- **验收条件**:
  1. 中断后从 `sync_cursor` 续传，不从头开始。
  2. 同一批次重复执行不产生重复样本（幂等键）。
  3. 取消信号在 5 秒内生效。
  4. 失败进入 DLQ，可人工重放。
  5. 水位只在批次成功后推进。
- **测试用例**:
  - IT：中断 → 续传 → 行数正确
  - IT：重复投递 → 不重复写入
  - IT：取消 → 任务停止且水位不推进
  - IT：失败 → DLQ 有记录
- **执行步骤**:
  1. 定义 `sync_cursor` 与幂等键。
  2. 实现分批读取 → 校验 → 写入 → 推进水位。
  3. 接入 Job 重试与取消。
  4. 写故障注入测试。
- **禁止**: 先推进水位再写数据；吞掉部分失败；无限重试。
- **验证命令**:
  ```bash
  pytest backend/tests/integration/ingestion/test_sync_resume.py -q
  pytest backend/tests/integration/ingestion/test_sync_idempotency.py -q
  ```
- **完成定义**: 续传/幂等/取消测试通过；DLQ 可重放。
- **预估**: L

---

## M11 search

### 模块职责

Qdrant 向量索引、Embedding 版本管理、语义检索、关键词降级。MySQL 不存向量。

### 任务清单

| ID | 任务 | 输入 | 输出 | 依赖 | 验收条件 | 测试用例 | Agent |
|---|---|---|---|---|---|---|---|
| SRC-01 | VectorIndex SPI | CORE-01 | `VectorIndex` 协议 | CORE-01 | upsert/search/delete；可替换 | 契约：fake index | agent-search |
| SRC-02 | Qdrant 适配 | SRC-01 | Qdrant 适配器 | SRC-01 | collection/payload 索引；租户过滤 | IT：Qdrant 容器 | agent-search |
| SRC-03 | Embedding 版本管理 | SRC-02、MGW-02 | `embedding_model`/`version`/`dim` | SRC-02、MGW-02 | 换模型可重建；双写切换 | IT：版本切换 | agent-search |
| SRC-04 | 索引任务与重建 | SRC-02、JOB-02 | 索引 JobHandler | SRC-02、JOB-02 | 全量/增量；失败可重试 | IT：重建/增量 | agent-search |
| SRC-05 | 语义检索 + 关键词降级 | SRC-02/03 | `SemanticSearch` | SRC-02/03 | top-k；score；Qdrant 挂了降级 | IT：检索/降级 | agent-search |
| SRC-06 | 租户隔离与降级测试 | SRC-05 | 安全/集成测试 | SRC-05 | 跨租户 0 结果；降级可用 | SEC：隔离；IT：降级 | agent-qa |

### 详细任务卡：SRC-05 语义检索 + 关键词降级

- **Agent**: `agent-search`
- **目标**: 为 Badcase 检索提供语义能力，并在 Qdrant 不可用时自动降级，不阻塞主流程。
- **输入**: SRC-02、SRC-03、`module-map.md`
- **输出**: `app/modules/search/service.py`、`public.py`
- **依赖**: SRC-02、SRC-03
- **验收条件**:
  1. 查询必须带 `tenant_id` 过滤，跨租户结果恒为空。
  2. 返回 top-k（默认 10，最大 50）与相似度分数。
  3. payload 只存引用 ID，不存完整 Prompt/样本正文。
  4. Qdrant 超时/不可用 → 降级为 MySQL 关键词检索，响应标注 `degraded=true`。
  5. 降级时 P95 不超过 1s。
- **测试用例**:
  - IT：语义检索返回相关结果与 score
  - SEC：租户 A 查询 → 不返回租户 B
  - IT：Qdrant 停止 → 降级成功
  - SEC：payload 不含 PII/正文
- **执行步骤**:
  1. 定义 `SemanticSearch` 协议。
  2. 实现 Qdrant 查询与过滤。
  3. 实现关键词降级。
  4. 加超时与熔断。
  5. 写故障注入测试。
- **禁止**: 无租户过滤的向量查询；把正文写入 payload；Qdrant 故障时返回 5xx。
- **验证命令**:
  ```bash
  pytest backend/tests/integration/search/test_semantic.py -q
  pytest backend/tests/security/search/test_tenant_isolation.py -q
  ```
- **完成定义**: 检索/降级/隔离测试通过；README 更新。
- **预估**: M

---

## 交付检查

- [ ] CAT-01 ~ CAT-07 完成
- [ ] ING-01 ~ ING-08 完成（P1）
- [ ] SRC-01 ~ SRC-06 完成（P1）
- [ ] 数据集版本不可变有自动化证明
- [ ] 批量写入有基准数据
- [ ] 同步任务有续传/幂等/取消测试
- [ ] 语义检索有降级与隔离测试
