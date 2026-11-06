# MCP Read-only Services Factory

The MCP adapter defaults to deterministic in-memory services in development. In
production it must read the platform tables through the read-only account.

## Configuration

```bash
export PINGCE_ENV=prod
export PINGCE_MCP_DB_DSN="mysql+pymysql://pingce_mcp_ro:***@mysql:3306/pingce?charset=utf8mb4"
export PINGCE_MCP_AUDIT_DSN="mysql+pymysql://pingce_mcp_audit:***@mysql:3306/pingce?charset=utf8mb4"
export PINGCE_MCP_SERVICES_FACTORY="app.services.readonly:build_readonly_services"
```

The shipped factory lives in `backend/app/services/readonly.py` and maps:

| MCP service | Source |
|---|---|
| projects | `project` |
| datasets / versions / samples | `dataset`, `dataset_version`, `sample` |
| evaluators / runs / items / scores | `evaluator`, `metric`, `run`, `run_item`, `score` |
| badcases | failed `run_item` rows, keyword fallback (`degraded=true`) |
| gate | latest `gate_result` for suite + run |

- Sessions are opened per call and the engine applies read-only transaction
  guards and a 5s statement timeout.
- Cross-tenant reads are filtered by `tenant_id` and return 404 from the tools.
- `search_badcases` uses a SQL keyword fallback until a live Qdrant index is
  configured; `degraded=true` is returned.

## Verify

```bash
python -m pytest tests/integration/services -q
```

In production, call one tool (e.g. `list_projects`) with a real tenant key and
confirm it returns rows, then check the read-only account cannot write:

```sql
SHOW GRANTS FOR 'pingce_mcp_ro'@'%';
```
