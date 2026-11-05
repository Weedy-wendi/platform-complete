"""Initialize MySQL for the MCP server.

Runs Alembic migrations with the root DSN, then creates the two restricted
accounts. This is the Compose init job, not a runtime path.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time

import pymysql
from sqlalchemy.engine import make_url

_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def _wait_for_mysql(url, attempts: int = 60) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            connection = pymysql.connect(
                host=url.host or "mysql",
                port=url.port or 3306,
                user=url.username or "root",
                password=url.password or "",
                database=url.database or "pingce",
                charset="utf8mb4",
                autocommit=True,
                connect_timeout=3,
            )
            connection.close()
            return
        except Exception as exc:  # pragma: no cover - integration path
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"MySQL did not become ready: {last_error}")


def _run_migrations() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=os.getcwd(),
    )


def _create_accounts(url, ro_password: str, audit_password: str) -> None:
    database = url.database or "pingce"
    if not _IDENTIFIER.match(database):
        raise ValueError("Database name contains unsupported characters")
    ro = pymysql.converters.escape_string(ro_password)
    audit = pymysql.converters.escape_string(audit_password)
    connection = pymysql.connect(
        host=url.host or "mysql",
        port=url.port or 3306,
        user=url.username or "root",
        password=url.password or "",
        database=database,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("DROP USER IF EXISTS 'pingce_mcp_ro'@'%'")
            cursor.execute("DROP USER IF EXISTS 'pingce_mcp_audit'@'%'")
            cursor.execute(f"CREATE USER 'pingce_mcp_ro'@'%' IDENTIFIED BY '{ro}'")
            cursor.execute(f"GRANT SELECT ON `{database}`.* TO 'pingce_mcp_ro'@'%'")
            cursor.execute(f"CREATE USER 'pingce_mcp_audit'@'%' IDENTIFIED BY '{audit}'")
            cursor.execute(f"GRANT INSERT ON `{database}`.`mcp_tool_call` TO 'pingce_mcp_audit'@'%'")
            cursor.execute("FLUSH PRIVILEGES")
    finally:
        connection.close()


def main() -> int:
    dsn = os.environ.get("PINGCE_MCP_DB_DSN", "")
    ro_password = os.environ.get("MCP_RO_PASSWORD", "")
    audit_password = os.environ.get("MCP_AUDIT_PASSWORD", "")
    if not dsn:
        raise SystemExit("PINGCE_MCP_DB_DSN is required")
    if not ro_password or not audit_password:
        raise SystemExit("MCP_RO_PASSWORD and MCP_AUDIT_PASSWORD are required")

    url = make_url(dsn)
    _wait_for_mysql(url)
    _run_migrations()
    _create_accounts(url, ro_password, audit_password)
    print("MySQL initialized: migrations applied; restricted accounts created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
