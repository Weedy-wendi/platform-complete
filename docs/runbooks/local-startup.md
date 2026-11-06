# Local Startup

Two supported paths:

- **A. Compose infra + API/MCP** (recommended): MySQL, Redis, migrations,
  read-only accounts, REST API and MCP server in containers; frontend locally.
- **B. Fully local backend**: run each process with `uvicorn`/`pingce` on the
  host; useful for debugging.

## Prerequisites

- Docker Desktop
- Python 3.12+
- Node.js 22+ / npm
- PowerShell (examples below) or an equivalent shell

## A. Compose + frontend

Start MySQL, Redis, the init job, the REST API and the MCP server:

```powershell
cd E:\WORKSPACE\Pingce
docker compose -f deploy/compose.yaml up -d --build
docker compose -f deploy/compose.yaml ps
```

The `init` job runs Alembic to head and creates the read-only/audit accounts.
Then create a tenant and a full-scope API key from the host:

```powershell
cd backend
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
$env:PINGCE_ENV = "dev"
$env:PINGCE_DATABASE_URL = "mysql+pymysql://root:change-me-root@127.0.0.1:3306/pingce?charset=utf8mb4"
python ..\scripts\bootstrap_platform.py `
  --dsn $env:PINGCE_DATABASE_URL `
  --tenant-name Demo --tenant-slug demo `
  --key-name local-admin `
  --pepper change-me-pepper
```

Copy the printed `api_key` (`pk_dev_...`). Start the frontend:

```powershell
cd ..\frontend
npm install
npm run gen:api
npm run dev
```

Open http://localhost:5173 and log in with that API key.

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| REST API | http://localhost:8000 |
| OpenAPI | http://localhost:8000/docs |
| MCP | http://localhost:8765/mcp |
| MySQL | 127.0.0.1:3306 |
| Redis | 127.0.0.1:6379 |

## B. Fully local backend

```powershell
# 1. Infrastructure only
docker compose -f deploy/compose.yaml up -d mysql redis

# 2. Backend dependencies
cd backend
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .

# 3. Environment
$env:PINGCE_ENV = "dev"
$env:PINGCE_DATABASE_URL = "mysql+pymysql://root:change-me-root@127.0.0.1:3306/pingce?charset=utf8mb4"
$env:PINGCE_MCP_DB_DSN = $env:PINGCE_DATABASE_URL
$env:PINGCE_MCP_AUDIT_DSN = $env:PINGCE_DATABASE_URL
$env:PINGCE_MCP_API_KEY_PEPPER = "change-me-pepper"
$env:PINGCE_MCP_CURSOR_SECRET = "change-me-cursor"
$env:PINGCE_MCP_SERVICES_FACTORY = "app.services.readonly:build_readonly_services"

# 4. Migrations + tenant key
python -m alembic upgrade head
python ..\scripts\bootstrap_platform.py --dsn $env:PINGCE_DATABASE_URL --tenant-name Demo --tenant-slug demo

# 5. REST API
uvicorn app.api.server:create_app_from_settings --factory --host 0.0.0.0 --port 8000

# 6. MCP server (second terminal)
pingce mcp serve --http --host 0.0.0.0 --port 8765

# 7. Frontend (third terminal)
cd ..\frontend
npm install
npm run gen:api
npm run dev
```

> `bootstrap_platform.py` uses `PINGCE_ENV` as the key environment. The printed
> key must start with `pk_dev_` for the dev API, otherwise the authenticator
> rejects it. Use `--key-env dev` explicitly if needed.

## Optional observability stack

```powershell
docker compose `
  -f deploy/compose.yaml `
  -f deploy/compose.observability.yaml `
  up -d
```

| Service | URL |
|---|---|
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| OTLP HTTP | http://localhost:4318 |
| Tempo | http://localhost:3200 |

Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` for services in
compose (the overlay already does this for `api` and `mcp-server`).

## Verification

```powershell
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/readyz

$key = "pk_dev_..."
curl -H "Authorization: Bearer $key" http://127.0.0.1:8000/v1/projects

curl http://127.0.0.1:8765/healthz
```

## Known scope of the REST API

The REST catalog (projects/datasets/datasources write paths), reports and the
MCP read surface are SQL-backed. The evaluation/gate/search/functional REST
ports still use deterministic in-memory adapters until their module adapters are
wired; the MCP tools are the fully SQL-backed read surface.

## Troubleshooting

- **API exits with `PINGCE_DATABASE_URL is required`**: set it and restart.
- **MCP returns empty lists**: `PINGCE_MCP_SERVICES_FACTORY` must be set to
  `app.services.readonly:build_readonly_services` and `PINGCE_MCP_DB_DSN` must
  point at MySQL.
- **401 after bootstrap**: key prefix and `PINGCE_ENV` disagree; re-issue with
  `--key-env dev` (or set `PINGCE_ENV` to match).
- **Frontend cannot reach the API**: the Vite dev server proxies `/v1` to
  `http://127.0.0.1:8000`; make sure the API is running there.
- **MySQL data location**: the compose files use bind mounts under `.local/`
  (E: on this machine), never the system drive.
