"""Register a model provider with a secret reference.

The plaintext key is never passed on the command line. Put it in an environment
variable and use ``secret://env/NAME`` (or ``secret://file/PATH``)::

    $env:OPENAI_API_KEY = "..."
    python scripts/configure_provider.py `
        --tenant-id tenant-a `
        --name judge `
        --provider openai `
        --model gpt-4o-mini `
        --secret-ref secret://env/OPENAI_API_KEY `
        --check-secret
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.context import TenantContext
from app.core.db import create_engine_from_dsn, make_session_factory
from app.core.secrets import DEFAULT_SECRET_RESOLVER, should_resolve
from app.modules.model_gateway.service import ModelGatewayService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or update a provider config row."
    )
    parser.add_argument("--dsn", default=os.environ.get("PINGCE_DATABASE_URL", ""))
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--subject-id", default="system")
    parser.add_argument("--name", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--secret-ref", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--connect-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--read-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--input-cost-per-million", type=float, default=0.0)
    parser.add_argument("--output-cost-per-million", type=float, default=0.0)
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("--check-secret", action="store_true")
    args = parser.parse_args()

    if not args.dsn:
        parser.error("--dsn or PINGCE_DATABASE_URL is required")
    if not args.secret_ref.startswith("secret://"):
        parser.error("--secret-ref must use the secret:// scheme")
    if not args.secret_ref.startswith(("secret://env/", "secret://file/")):
        parser.error("this script resolves secret://env/ or secret://file/ refs only")
    if args.check_secret:
        DEFAULT_SECRET_RESOLVER.resolve(args.secret_ref)
        print("secret_ok")

    engine = create_engine_from_dsn(args.dsn)
    factory = make_session_factory(engine)
    service = ModelGatewayService(factory, completion=lambda *_: None)
    ctx = TenantContext(
        tenant_id=args.tenant_id,
        subject_id=args.subject_id,
        scopes=frozenset({"platform:admin"}),
        trace_id="configure-provider",
    )
    view = service.create_provider(
        ctx,
        name=args.name,
        provider=args.provider,
        model=args.model,
        secret_ref=args.secret_ref,
        timeout_seconds=args.timeout_seconds,
        connect_timeout_seconds=args.connect_timeout_seconds,
        read_timeout_seconds=args.read_timeout_seconds,
        max_retries=args.max_retries,
        input_cost_per_million=args.input_cost_per_million,
        output_cost_per_million=args.output_cost_per_million,
        enabled=not args.disabled,
    )
    print(
        f"provider_id={view.id} name={view.name} enabled={view.enabled} secret_ref={view.secret_ref}"
    )
    if should_resolve(args.secret_ref):
        print("secret_resolution=enabled")
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
