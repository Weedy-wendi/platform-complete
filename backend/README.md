# Pingce Backend

MCP Streamable HTTP adapter + platform backend skeleton.

## Requirements

- Python 3.12+
- MySQL 8.0 (production)
- Redis 7+ (production rate limiting / queue)
- Docker (optional, for compose)

## Install

```bash
cd backend
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
```

For a reproducible test environment, use the lockfile venv described in
`docs/runbooks/dependency-upgrade.md`.

## Run

```bash
pingce mcp serve --http --host 0.0.0.0 --port 8765
```

Health:

```bash
curl http://127.0.0.1:8765/healthz
curl http://127.0.0.1:8765/readyz
```

## Test

```bash
pytest -q
ruff check app tests
mypy app
```

The suite covers protocol discovery, authentication/scope matrix, all ten read-only tools, cursor pagination, result limits, redaction, rate limiting, resources, OAuth switching, audit resilience, and MySQL migrations/grants (via the verification script).

## Read-only surface

Tools (all `readOnlyHint=true`):

`list_projects`, `search_datasets`, `get_dataset_schema`, `preview_samples`, `list_evaluators`, `get_run`, `get_run_items`, `compare_runs`, `search_badcases`, `check_gate`.

Resources:

- `pingce://datasets/{dataset_id}/versions/{version}/schema`
- `pingce://runs/{run_id}/summary.json`
- `pingce://runs/{run_id}/report.md`

`search_badcases` and `check_gate` delegate to `app.services.search.SemanticSearch` and `app.services.gate.GateReader`. If those platform services are not wired, the tools stay registered and return `UPSTREAM_UNAVAILABLE`.

## Production service wiring

In production the adapter must not use empty in-memory services. Provide a dotted
`module:callable` factory that receives `Settings` and returns a
`ServiceRegistry` backed by the platform read-only tables:

```bash
export PINGCE_ENV=prod
export PINGCE_MCP_SERVICES_FACTORY="pingce_platform.mcp_services:build_readonly_services"
```

`create_app` fails fast when `PINGCE_ENV=prod` and no factory is configured.
Development and tests may omit it and use the deterministic in-memory services.

## Audit partition maintenance

```bash
pingce mcp maintain-partitions --dsn "$PINGCE_MAINT_DSN" --months-ahead 3 --retention-days 90 --dry-run
```

Run it monthly with an admin DDL account. See
`docs/runbooks/mcp-partition-maintenance.md`.

## Load test

```powershell
python ..\scripts\load-mcp.py --url http://127.0.0.1:8765/mcp --api-key $env:PINGCE_LOAD_KEY --qps 50 --duration 1800
```

Use a dedicated load-test key with a raised rate limit; 429s are counted separately from 5xx.

## Container smoke test

```powershell
powershell -ExecutionPolicy Bypass -File ..\scripts\smoke-container.ps1
```

Builds the image, verifies `/app/contracts/tools.yaml` exposes all ten tools, and checks `/healthz`.

## Monitoring

Prometheus alert rules: `../deploy/prometheus/alerts.yaml`. Security checklist: `../docs/security/mcp-security-checklist.md`.

## CI

`.github/workflows/ci.yml` runs `ruff`, `ruff format --check`, `mypy`,
`lint-imports`, the full `pytest` suite (architecture, contract snapshot,
security/tenancy, tools), and a MySQL job that performs
`alembic upgrade → downgrade → upgrade` and verifies the restricted grants.

## Issue a development API key

```python
from app.modules.identity.public import ALLOWED_SCOPES, ApiKeyService, InMemoryApiKeyStore

service = ApiKeyService(InMemoryApiKeyStore(), pepper="dev-pepper", key_env="test")
issued = service.issue(tenant_id="tenant-a", name="local", scopes=ALLOWED_SCOPES)
print(issued.raw_key)
```

The in-memory store is process-local; for production use `SqlApiKeyStore` and persist the key.

## Identity and audit

`IdentityService` owns tenants, users, roles and audited API-key operations. It
requires a `TenantContext` whose `scopes` contain the explicit identity
permission (`identity:user:create`, `identity:role:assign`, ...); unknown
roles/permissions are denied by default.

```python
from app.core.context import TenantContext
from app.core.db import make_session_factory
from app.modules.audit.writer import InMemoryAuditLogWriter
from app.modules.identity.public import (
    ApiKeyService,
    IDENTITY_PERMISSIONS,
    IdentityService,
    InMemoryApiKeyStore,
)

factory = make_session_factory(engine)
service = IdentityService(
    factory,
    ApiKeyService(InMemoryApiKeyStore(), pepper="dev-pepper"),
    InMemoryAuditLogWriter(),
)
ctx = TenantContext(
    tenant_id="tenant-a",
    subject_id="admin",
    scopes=frozenset(IDENTITY_PERMISSIONS),
    trace_id="trace-1",
)
```

Role changes, logins, key issuance and revocation are written to `audit_log`
through `AuditLogWriter`; `SqlAuditLogWriter` is the production implementation.
Use `IdentityService.set_tenant_status(..., "disabled")` to disable a tenant;
its API keys then fail authentication and its management operations are rejected.

## Object storage and assets

`ArtifactService` stores bytes through the `Storage` SPI and keeps only
metadata in MySQL. Local storage is the development default; OSS/MinIO use the
S3-compatible adapters and require the optional extra:

```bash
pip install '.[storage]'
export PINGCE_STORAGE_BACKEND=s3
export PINGCE_OSS_ENDPOINT=https://minio.example.com
export PINGCE_OSS_BUCKET=pingce
export PINGCE_OSS_ACCESS_KEY=...
export PINGCE_OSS_SECRET_KEY=...
export PINGCE_OSS_PATH_STYLE=true   # MinIO; false for virtual-host OSS
```

Buckets are private by construction; presigned URLs are capped at 15 minutes.

## Migrations

```bash
export PINGCE_DATABASE_URL="mysql+pymysql://user:pass@127.0.0.1:3306/pingce?charset=utf8mb4"
export PINGCE_READ_REPLICA_URL=""   # optional; empty falls back to DATABASE_URL
export PINGCE_MCP_DB_DSN="mysql+pymysql://user:pass@127.0.0.1:3306/pingce?charset=utf8mb4"
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Platform code gets read/write routing from `app.core.db.get_session_registry()`:
writes always use `PINGCE_DATABASE_URL`, reads use `PINGCE_READ_REPLICA_URL` when set
(with a 5s statement timeout and read-only transaction guards).

## MySQL verification (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File ..\scripts\verify-mysql.ps1
```

The script stores MySQL data on a non-C: bind mount (default `E:\WORKSPACE\Pingce\.local\mysql-verify`), runs the migration round trip, creates restricted accounts, verifies SELECT/INSERT-only grants, starts the MCP server with those accounts, and checks that a `list_projects` call writes an audit row.

> The passwords in the script are for local verification only. Replace them for any shared environment. MySQL data files are on E:; Docker Desktop's own VM/image storage is managed separately by Docker.

## Compose

```bash
docker compose -f ../deploy/compose.yaml up --build
```

The compose file is a development topology; replace all `change-me` secrets before any shared deployment.
