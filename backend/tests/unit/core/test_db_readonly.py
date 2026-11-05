"""Read-only session guards (T077)."""

from __future__ import annotations

from typing import Any

from app.core.db import READONLY_SESSION_STATEMENTS, apply_readonly_session


class FakeCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.closed = False

    def execute(self, statement: str) -> None:
        self.statements.append(statement)

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self) -> None:
        self._cursor = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self._cursor


def test_readonly_statements_cover_timeout_readonly_and_utc() -> None:
    joined = " ".join(READONLY_SESSION_STATEMENTS)
    assert "MAX_EXECUTION_TIME=5000" in joined
    assert "TRANSACTION READ ONLY" in joined
    assert "time_zone='+00:00'" in joined


def test_apply_readonly_session_executes_and_closes() -> None:
    connection: Any = FakeConnection()
    apply_readonly_session(connection)
    assert connection._cursor.statements == list(READONLY_SESSION_STATEMENTS)
    assert connection._cursor.closed is True
