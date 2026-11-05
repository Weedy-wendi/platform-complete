# MCP 安全上线检查清单

适用于 `001-mcp-server`。所有条目在上线前必须有证据；未完成项必须记录例外与到期时间。

## 1. 网络与入口

- [ ] TLS 在 Ingress 终止；仅允许 TLS 1.2+。
- [ ] `/mcp` 默认仅内网 / VPN 可达；公网暴露需独立安全评审。
- [ ] WAF 开启，限制请求体 ≤ 256KB、连接超时 30s。
- [ ] IP allowlist 按租户或团队配置。
- [ ] Ingress 不缓存 `/mcp` 响应。

验证：

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://pingce.example.com/mcp
```

预期：无凭据返回 `401`，且带 `WWW-Authenticate: Bearer`。

## 2. 认证与凭据

- [ ] API Key 仅以 HMAC-SHA256(pepper, secret) 存储；数据库无明文。
- [ ] `MCP_API_KEY_PEPPER` 与 `MCP_CURSOR_SECRET` 来自密钥管理，不写入镜像或 Git。
- [ ] Key 最小 scope；禁止默认签发全量 scope。
- [ ] 吊销后 ≤ 60 秒生效（Redis 缓存 TTL ≤ 60s）。
- [ ] 泄露响应流程：吊销 → 重新签发 → 审计检索 → 通知。
- [ ] OAuth 模式启用时校验 `iss` / `aud` / `exp` / `scope`，拒绝 token passthrough。

验证：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-mysql.ps1
```

覆盖 `api_key` 表、受限账号与吊销路径。

## 3. 数据库授权

- [ ] `pingce_mcp_ro` 仅有业务表 `SELECT`。
- [ ] `pingce_mcp_audit` 仅有 `mcp_tool_call` 的 `INSERT`。
- [ ] 两个账号都不能 `UPDATE` / `DELETE` / DDL。
- [ ] 只读连接设置 `SET SESSION TRANSACTION READ ONLY` 与 `MAX_EXECUTION_TIME`。
- [ ] 审计表 append-only；保留策略通过 `DROP PARTITION`。

验证：

```sql
SHOW GRANTS FOR 'pingce_mcp_ro'@'%';
SHOW GRANTS FOR 'pingce_mcp_audit'@'%';
```

## 4. 日志与审计

- [ ] 日志不记录完整 API Key、完整 Prompt、完整样本或 PII。
- [ ] 审计记录含 `tenant_id`、`api_key_id`、工具名/版本、状态、耗时、字节数、`trace_id`。
- [ ] 审计写入失败触发 `McpAuditWriteFailures` 告警，但不阻塞主请求。
- [ ] 审计日志保留 ≥ 90 天，且可按 `trace_id` 在 1 分钟内检索。

验证：

```powershell
python -m pytest backend/tests/security/mcp/test_log_redaction.py -q
```

## 5. 限流与资源

- [ ] Key 120/min、Tenant 600/min、重工具 30/min。
- [ ] 超限返回 HTTP 429 + `Retry-After`。
- [ ] Redis 不可用时本地令牌桶兜底；生产环境不得静默降级（T070）。
- [ ] 单次结果 ≤ 64KB；单条样本 payload ≤ 4KB。
- [ ] 工具调用 ≤ 25s。

验证：

```powershell
python -m pytest backend/tests/integration/mcp/test_rate_limits.py backend/tests/unit/mcp/test_result_limits.py -q
```

## 6. 依赖与供应链

- [ ] Python 依赖锁定在 `backend/requirements.lock`。
- [ ] 基础镜像与 MySQL/Redis 镜像使用 digest 固定。
- [ ] 升级流程见 `docs/runbooks/dependency-upgrade.md`。
- [ ] CI 运行 `ruff`、`mypy`、完整测试集与契约快照。

## 7. 可观测与应急

- [ ] 指标：`mcp_tool_calls_total`、`mcp_tool_duration_seconds`、`mcp_auth_failures_total`、`mcp_rate_limited_total`、`mcp_audit_write_failed_total`、`mcp_cursor_invalid_total`。
- [ ] 告警规则见 `deploy/prometheus/alerts.yaml`。
- [ ] `/healthz` 与 `/readyz` 接入探针。
- [ ] 优雅停机等待 in-flight ≤ 30s。

## 8. 上线前复检

```powershell
cd backend
python -m pytest -q
python -m ruff check app tests
python -m mypy app

cd ..
powershell -ExecutionPolicy Bypass -File scripts/smoke-container.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify-mysql.ps1
```

全部通过后方可上线。
