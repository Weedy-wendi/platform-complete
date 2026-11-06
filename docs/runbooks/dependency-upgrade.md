# Dependency & Image Upgrade

This runbook keeps the runtime reproducible: Python runtime dependencies are
locked in `backend/requirements.lock`, test/CI tools in
`backend/requirements-dev.lock`, and container images are pinned by digest.

## 1. Update Python dependencies

```bash
cd backend
# edit pyproject.toml first
uv pip compile pyproject.toml -o requirements.lock --python-platform linux --python-version 3.12
uv pip compile pyproject.toml --extra dev -o requirements-dev.lock --python-platform linux --python-version 3.12
```

## 2. Verify against the lockfile

```powershell
cd backend
uv venv .venv-lock --python 3.13
uv pip install -r requirements-dev.lock --python .venv-lock\Scripts\python.exe
uv pip install --no-deps -e . --python .venv-lock\Scripts\python.exe
.\.venv-lock\Scripts\python.exe -m pytest -q
.\.venv-lock\Scripts\python.exe -m ruff check app tests
.\.venv-lock\Scripts\python.exe -m mypy app
```

## 3. Refresh image digests

```powershell
docker pull python:3.12-slim
docker pull mysql:8.0
docker pull redis:7-alpine

docker image inspect python:3.12-slim --format "{{index .RepoDigests 0}}"
docker image inspect mysql:8.0 --format "{{index .RepoDigests 0}}"
docker image inspect redis:7-alpine --format "{{index .RepoDigests 0}}"
```

Update:
- `backend/Dockerfile` `FROM ...@sha256:...`
- `deploy/compose.yaml` `mysql` and `redis` image digests

## 4. Build and smoke test

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke-container.ps1
```

The smoke test verifies:
- the image contains `/app/contracts/tools.yaml`
- `ToolRegistry` loads exactly 10 tools
- the container starts and `/healthz` responds

## 5. Run MySQL verification

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-mysql.ps1
```

## Rollback

Revert `requirements.lock`, `requirements-dev.lock`, and the digest changes
together. Do not keep a new lockfile with old image digests; they are one
deployment unit.
