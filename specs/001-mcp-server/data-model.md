# Data Model: MCP Server（HTTP 只读接入）

**Feature**: `001-mcp-server` | **Date**: 2026-11-05

本特性不新增业务实体，仅新增两张支撑表：`api_key`（若平台尚未具备）与 `mcp_tool_call`（调用审计）。所有业务实体（Dataset、Run、Badcase、Gate）复用既有模型，MCP 只读。

MySQL 约定遵循宪法：`utf8mb4`、`DATETIME(6)`、UTC、无外键、高频表分区、`READ COMMITTED`。

---

## 1. `api_key`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT UNSIGNED AUTO_INCREMENT | 主键 |
| `tenant_id` | VARCHAR(32) NOT NULL | 租户 |
| `key_id` | CHAR(24) NOT NULL | 公开标识，用于查找 |
| `name` | VARCHAR(128) NOT NULL | 人类可读名称 |
| `secret_hmac` | BINARY(32) NOT NULL | `HMAC-SHA256(pepper, secret)` |
| `scopes` | JSON NOT NULL | 字符串数组 |
| `expires_at` | DATETIME(6) NULL | 为空表示长期有效 |
| `revoked_at` | DATETIME(6) NULL | 非空表示已吊销 |
| `last_used_at` | DATETIME(6) NULL | 最近使用时间（异步更新） |
| `created_by` | VARCHAR(64) NOT NULL | 创建者 |
| `created_at` | DATETIME(6) NOT NULL | 创建时间 |

索引：

```sql
UNIQUE KEY uk_api_key_key_id (key_id),
KEY idx_api_key_tenant (tenant_id, revoked_at),
KEY idx_api_key_expires (expires_at)
```

约束：

- `key_id` 全局唯一，生成规则：`base62(12 bytes random)`。
- `scopes` 只允许白名单值；写入前校验。
- 不存明文 secret；创建时仅返回一次。
- 吊销：写 `revoked_at`；缓存 TTL ≤ 60s。

---

## 2. `mcp_tool_call`

append-only 调用审计。不存完整参数与结果内容。

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT UNSIGNED AUTO_INCREMENT | 主键的一部分 |
| `tenant_id` | VARCHAR(32) NOT NULL | 租户 |
| `api_key_id` | BIGINT UNSIGNED NOT NULL | 关联 `api_key.id`（逻辑关联，无外键） |
| `client_name` | VARCHAR(128) NULL | 客户端自报名称（不可信，仅参考） |
| `tool_name` | VARCHAR(64) NOT NULL | 工具名 |
| `tool_version` | VARCHAR(16) NOT NULL | 工具版本 |
| `status` | ENUM('ok','error','rate_limited','unauthorized') NOT NULL | 结果状态 |
| `error_code` | VARCHAR(64) NULL | 业务错误码 |
| `latency_ms` | INT UNSIGNED NOT NULL | 服务端耗时 |
| `result_bytes` | INT UNSIGNED NOT NULL | 响应字节数 |
| `trace_id` | CHAR(32) NOT NULL | 链路 ID |
| `created_at` | DATETIME(6) NOT NULL | 创建时间 |

索引与分区：

```sql
PRIMARY KEY (id, created_at),
KEY idx_mcp_call_tenant_time (tenant_id, created_at),
KEY idx_mcp_call_tool_time (tool_name, created_at),
KEY idx_mcp_call_trace (trace_id)
PARTITION BY RANGE COLUMNS(created_at) (
  PARTITION p202611 VALUES LESS THAN ('2026-12-01'),
  PARTITION p202612 VALUES LESS THAN ('2027-01-01')
  -- 由迁移脚本按月预建；保留 90 天，过期 DROP PARTITION
);
```

约束：

- 禁止 `UPDATE` / `DELETE`；保留策略通过 `DROP PARTITION` 实现。
- 不记录请求体、响应体、完整 Prompt、完整样本、API Key。
- 写入失败不得阻塞主请求，但必须打日志并触发告警（`mcp_audit_write_failed_total`）。

---

## 3. 数据库账号与授权

MCP 使用两个 DSN：

| DSN | 用途 | 账号权限 |
|---|---|---|
| `MCP_DB_DSN` | 业务只读查询 | 业务表 `SELECT` |
| `MCP_AUDIT_DSN` | 审计写入 | `mcp_tool_call` 仅 `INSERT` |

```sql
-- 业务只读账号（指向只读副本）
CREATE USER 'pingce_mcp_ro'@'%' IDENTIFIED BY '<secret>';
GRANT SELECT ON pingce.* TO 'pingce_mcp_ro'@'%';

-- 审计写入账号（指向主库）
CREATE USER 'pingce_mcp_audit'@'%' IDENTIFIED BY '<secret>';
GRANT INSERT ON pingce.mcp_tool_call TO 'pingce_mcp_audit'@'%';
```

会话级保护：

```sql
SET SESSION MAX_EXECUTION_TIME = 5000;
SET SESSION TRANSACTION READ ONLY;   -- 仅业务只读连接
SET SESSION time_zone = '+00:00';
```

验证用例（必须入库为自动化测试）：

```sql
-- 以下语句在 pingce_mcp_ro 下必须全部失败
INSERT INTO dataset (name) VALUES ('x');
UPDATE dataset SET name = 'x' WHERE id = 1;
DELETE FROM dataset WHERE id = 1;
CREATE TABLE t (id INT);
DROP TABLE dataset;
```

---

## 4. Redis 键设计

| Key | 类型 | TTL | 用途 |
|---|---|---|---|
| `mcp:auth:key:{key_id}` | String(JSON) | 60s | Principal 缓存 |
| `mcp:rl:key:{key_id}` | Hash / Lua | 60s | Key 级令牌桶 |
| `mcp:rl:tenant:{tenant_id}` | Hash / Lua | 60s | 租户级令牌桶 |
| `mcp:rl:tool:{key_id}:{tool}` | Hash / Lua | 60s | 重工具独立桶 |

- 所有 key 必须带 `mcp:` 前缀，避免与平台缓存冲突。
- Redis 故障：降级为本地令牌桶（保守阈值），并告警。

---

## 5. 游标（无表）

游标为自包含签名令牌，不落库：

```json
{
  "v": 1,
  "t": "tenant_a",
  "tool": "search_datasets",
  "q": "sha256(query_params)",
  "k": {"updated_at": "2026-11-05T10:00:00Z", "id": "ds_123"},
  "exp": 1762345678
}
```

- 签名：`HMAC-SHA256(MCP_CURSOR_SECRET, payload)`。
- TTL 15 分钟。
- 校验失败 → `INVALID_CURSOR`，不泄露具体原因。

---

## 6. 与既有实体的只读映射

| MCP 工具 | 读取实体 | 备注 |
|---|---|---|
| `list_projects` | `project` | 按 `tenant_id` 过滤 |
| `search_datasets` | `dataset` + `dataset_version` | 返回 `latest_version`、`sample_count` |
| `get_dataset_schema` | `dataset_version.schema_json` | 默认最新版本 |
| `preview_samples` | `sample` | 脱敏；≤ 20 条 |
| `list_evaluators` | `evaluator` + `evaluator_version` | 只返回已发布版本 |
| `get_run` | `run` | 含 `manifest_hash`、统计、成本 |
| `get_run_items` | `run_item` | 默认不含 IO |
| `compare_runs` | `run` + 聚合指标 | 差值、显著性标记 |
| `search_badcases` | `badcase` + Qdrant | Qdrant 不可用降级关键词 |
| `check_gate` | `gate` + `gate_result` | 只读判定 |

---

## 7. 迁移与回滚

| 迁移 | 回滚 |
|---|---|
| 建 `api_key` | `DROP TABLE api_key`（仅当无数据） |
| 建 `mcp_tool_call` + 分区 | `DROP TABLE mcp_tool_call` |
| 创建 DB 账号与授权 | `REVOKE` + `DROP USER` |
| 初始化分区 | 删除未来分区 |

迁移要求：

- 一次一个 DDL。
- 上线前备份。
- 大表变更使用 `ALGORITHM=INPLACE, LOCK=NONE`。
- 迁移脚本必须附回滚脚本与验证 SQL。
