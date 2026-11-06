"""CLI entry points."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from app.mcp import server as mcp_server


def _serve(args: argparse.Namespace) -> int:
    # Reuse the server entrypoint so graceful shutdown (30s) is applied.
    mcp_server.run(host=args.host, port=args.port)
    return 0


def _maintain_partitions(args: argparse.Namespace) -> int:
    from app.cli.maintain_partitions import run

    return run(
        dsn=args.dsn,
        months_ahead=args.months_ahead,
        retention_days=args.retention_days,
        dry_run=args.dry_run,
    )


def _maintain_audit_partitions(args: argparse.Namespace) -> int:
    from app.cli.maintain_partitions import run

    return run(
        dsn=args.dsn,
        months_ahead=args.months_ahead,
        retention_days=args.retention_days,
        dry_run=args.dry_run,
        table="audit_log",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pingce")
    sub = parser.add_subparsers(dest="command")

    mcp = sub.add_parser("mcp", help="MCP server commands")
    mcp_sub = mcp.add_subparsers(dest="mcp_command")
    serve = mcp_sub.add_parser("serve", help="Serve the MCP Streamable HTTP endpoint")
    serve.add_argument("--http", action="store_true", help="Use Streamable HTTP (default)")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=_serve)

    maintain = mcp_sub.add_parser(
        "maintain-partitions",
        help="Pre-create and expire mcp_tool_call monthly partitions",
    )
    maintain.add_argument("--dsn", default=os.environ.get("PINGCE_MCP_DB_DSN", ""))
    maintain.add_argument("--months-ahead", type=int, default=3)
    maintain.add_argument("--retention-days", type=int, default=90)
    maintain.add_argument("--dry-run", action="store_true")
    maintain.set_defaults(func=_maintain_partitions)

    audit = sub.add_parser("audit", help="Audit log maintenance")
    audit_sub = audit.add_subparsers(dest="audit_command")
    audit_maint = audit_sub.add_parser(
        "maintain-partitions",
        help="Pre-create and expire audit_log monthly partitions",
    )
    audit_maint.add_argument(
        "--dsn",
        default=os.environ.get("PINGCE_DATABASE_URL", os.environ.get("PINGCE_MCP_DB_DSN", "")),
    )
    audit_maint.add_argument("--months-ahead", type=int, default=3)
    audit_maint.add_argument("--retention-days", type=int, default=180)
    audit_maint.add_argument("--dry-run", action="store_true")
    audit_maint.set_defaults(func=_maintain_audit_partitions)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    result = args.func(args)
    return 0 if result is None else int(result)


if __name__ == "__main__":
    raise SystemExit(main())
