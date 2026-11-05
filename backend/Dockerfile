FROM python:3.12-slim@sha256:e695ab189fa2d082b1c61c69a6b888a5adeca61ceeccad107b1ed2a125721a9e

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PINGCE_MCP_CONTRACTS_PATH=/app/contracts/tools.yaml

WORKDIR /app

COPY backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir --no-deps .

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/deploy ./deploy
COPY specs/001-mcp-server/contracts/tools.yaml ./contracts/tools.yaml

EXPOSE 8765
CMD ["pingce", "mcp", "serve", "--http", "--host", "0.0.0.0", "--port", "8765"]
