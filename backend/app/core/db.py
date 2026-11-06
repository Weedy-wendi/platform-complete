"""Database primitives.

The control plane uses synchronous SQLAlchemy. The MCP adapter is read-only for
business tables and only writes to the audit table through a separate DSN.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.context import try_get_tenant_context
from app.core.logging import get_logger

_sql_logger = get_logger("app.core.sql")

READONLY_SESSION_STATEMENTS: tuple[str, ...] = (
    "SET SESSION MAX_EXECUTION_TIME=5000",
    "SET SESSION TRANSACTION READ ONLY",
    "SET SESSION time_zone='+00:00'",
)


class Base(DeclarativeBase):
    pass


def create_engine_from_dsn(dsn: str, *, echo: bool = False) -> Engine:
    if not dsn:
        raise ValueError("Database DSN is empty")
    engine = create_engine(
        dsn,
        echo=echo,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )
    install_sql_logging(engine)
    return engine


def install_sql_logging(engine: Engine) -> None:
    """Log SQL templates with tenant/trace context, never bound parameters."""

    def _log_sql(
        connection: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        tenant = try_get_tenant_context()
        _sql_logger.info(
            "sql",
            extra={
                "sql": statement,
                "trace_id": tenant.trace_id if tenant else None,
                "tenant_id": tenant.tenant_id if tenant else None,
            },
        )

    event.listen(engine, "before_cursor_execute", _log_sql)


def apply_readonly_session(dbapi_connection: Any) -> None:
    """Apply read-only session guards on a raw DBAPI connection (MySQL)."""
    cursor = dbapi_connection.cursor()
    try:
        for statement in READONLY_SESSION_STATEMENTS:
            cursor.execute(statement)
    finally:
        cursor.close()


def create_readonly_engine_from_dsn(dsn: str, *, echo: bool = False) -> Engine:
    """Engine for the business read replica/read-only account.

    A server-side statement timeout and read-only transaction mode are defense
    in depth on top of the restricted grants.
    """
    engine = create_engine_from_dsn(dsn, echo=echo)
    event.listen(engine, "connect", lambda connection, _record: apply_readonly_session(connection))
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def write_session(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Explicit write transaction boundary."""
    with session_scope(factory) as session:
        yield session


@contextmanager
def read_session(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Read transaction boundary; callers should pass a read-only factory."""
    with session_scope(factory) as session:
        yield session


class UnitOfWork:
    """Small transaction boundary used by application services."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()
        self.close()


@dataclass(frozen=True)
class SessionRegistry:
    """Platform read/write session routing.

    Writes always use the writable engine. Reads use the replica when configured
    (with the read-only session guards); otherwise they fall back to the
    writable engine.
    """

    write_engine: Engine
    read_engine: Engine
    write_factory: sessionmaker[Session]
    read_factory: sessionmaker[Session]

    @classmethod
    def from_settings(cls, settings: Settings) -> SessionRegistry:
        if not settings.database_url:
            raise ValueError("DATABASE_URL is required for platform sessions")
        write_engine = create_engine_from_dsn(settings.database_url)
        if settings.read_replica_url:
            read_engine = create_readonly_engine_from_dsn(settings.read_replica_url)
        else:
            read_engine = write_engine
        return cls(
            write_engine=write_engine,
            read_engine=read_engine,
            write_factory=make_session_factory(write_engine),
            read_factory=make_session_factory(read_engine),
        )

    @contextmanager
    def write_session(self) -> Iterator[Session]:
        with session_scope(self.write_factory) as session:
            yield session

    @contextmanager
    def read_session(self) -> Iterator[Session]:
        with session_scope(self.read_factory) as session:
            yield session

    def dispose(self) -> None:
        self.write_engine.dispose()
        if self.read_engine is not self.write_engine:
            self.read_engine.dispose()


_registry: SessionRegistry | None = None


def get_session_registry() -> SessionRegistry:
    """Return the process-wide session registry, creating it on first use."""
    global _registry
    if _registry is None:
        _registry = SessionRegistry.from_settings(get_settings())
    return _registry


def set_session_registry(registry: SessionRegistry | None) -> None:
    """Replace the process-wide registry (tests and application startup)."""
    global _registry
    _registry = registry


def reset_session_registry() -> None:
    """Drop the process-wide registry without disposing it."""
    set_session_registry(None)
