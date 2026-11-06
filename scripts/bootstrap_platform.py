"""Create a local tenant and a full-scope API key.

Run after migrations::

    python scripts/bootstrap_platform.py `
        --dsn "mysql+pymysql://root:...@127.0.0.1:3306/pingce?charset=utf8mb4" `
        --tenant-name "Demo" --tenant-slug demo

The raw API key is printed once; store it in the frontend login screen or a
secret manager. It is never written to the database in plaintext.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.context import TenantContext  # noqa: E402
from app.core.db import create_engine_from_dsn, make_session_factory  # noqa: E402
from app.modules.identity.api_key import ISSUABLE_SCOPES, ApiKeyService, SqlApiKeyStore  # noqa: E402
from app.modules.identity.auth import SqlTenantStatusChecker  # noqa: E402
from app.modules.identity.service import IdentityService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a tenant and API key.")
    parser.add_argument("--dsn", default=os.environ.get("PINGCE_DATABASE_URL", ""))
    parser.add_argument("--tenant-name", default="Demo")
    parser.add_argument("--tenant-slug", default="demo")
    parser.add_argument("--tenant-id", default="", help="Use an existing tenant instead of creating one")
    parser.add_argument("--key-name", default="local-admin")
    parser.add_argument(
        "--pepper",
        default=os.environ.get("PINGCE_MCP_API_KEY_PEPPER")
        or os.environ.get("PINGCE_API_KEY_PEPPER")
        or "dev-pepper-change-me",
    )
    parser.add_argument("--subject-id", default="bootstrap")
    parser.add_argument("--key-env", default=os.environ.get("PINGCE_ENV", "dev"))
    args = parser.parse_args()
    if not args.dsn:
        parser.error("--dsn or PINGCE_DATABASE_URL is required")

    engine = create_engine_from_dsn(args.dsn)
    factory = make_session_factory(engine)
    key_service = ApiKeyService(
        SqlApiKeyStore(factory),
        pepper=args.pepper,
        key_env=args.key_env,
        tenant_status_checker=SqlTenantStatusChecker(factory),
    )
    identity = IdentityService(factory, key_service)

    bootstrap_ctx = TenantContext(
        tenant_id=args.tenant_id or "bootstrap",
        subject_id=args.subject_id,
        scopes=frozenset({"identity:tenant:create", "identity:api_key:issue"}),
        trace_id="bootstrap",
    )
    tenant_id = args.tenant_id
    if not tenant_id:
        tenant = identity.create_tenant(bootstrap_ctx, args.tenant_name, args.tenant_slug)
        tenant_id = tenant.id
        print(f"tenant_id={tenant_id} slug={tenant.slug}")
    else:
        print(f"tenant_id={tenant_id} (existing)")

    issue_ctx = TenantContext(
        tenant_id=tenant_id,
        subject_id=args.subject_id,
        scopes=frozenset({"identity:api_key:issue"}),
        trace_id="bootstrap",
    )
    issued = identity.issue_api_key(issue_ctx, name=args.key_name, scopes=set(ISSUABLE_SCOPES))
    print(f"key_id={issued.key_id}")
    print(f"api_key={issued.raw_key}")
    print("Store the api_key now; it is not recoverable from the database.")
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
