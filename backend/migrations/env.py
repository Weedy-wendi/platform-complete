"""Alembic environment."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import Settings
from app.core.db import Base
from app.modules.audit.models import AuditLog, McpToolCall  # noqa: F401
from app.modules.assets.models import Artifact  # noqa: F401
from app.modules.catalog.models import (  # noqa: F401
    Dataset,
    DatasetVersion,
    Datasource,
    LineageEdge,
    Project,
    Sample,
)
from app.modules.identity.models import ApiKey  # noqa: F401
from app.modules.ingestion.models import (  # noqa: F401
    ConnectorRecord,
    IngestionDeadLetter,
    IngestionJob,
    QualityResult,
    QualityRule,
    SyncCursor,
)
from app.modules.functional.models import (  # noqa: F401
    AssertionRecord,
    FunctionalDeadLetter,
    FunctionalTestCase,
    FunctionalTestSuite,
    TestRun,
    TestStep,
    VisualDiff,
)
from app.modules.evaluation.models import (  # noqa: F401
    Baseline,
    EvalSuite,
    Evaluator,
    EvaluatorVersion,
    JudgeCall,
    Metric,
    Run,
    RunItem,
    Score,
    SuiteVersion,
    Target,
)
from app.modules.gate.models import Gate, GateResultRecord, GateRuleRecord  # noqa: F401
from app.modules.reporting.models import ReadModelRun, ReportSnapshot  # noqa: F401
from app.modules.jobs.models import (  # noqa: F401
    DeadLetterTask,
    IdempotencyKey,
    Job,
    JobEvent,
)
from app.modules.model_gateway.models import ModelCall, ProviderConfig  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _dsn() -> str:
    settings = Settings()
    if not settings.mcp_db_dsn:
        raise RuntimeError("PINGCE_MCP_DB_DSN is required to run migrations")
    return settings.mcp_db_dsn


def run_migrations_offline() -> None:
    context.configure(
        url=_dsn(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _dsn()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
