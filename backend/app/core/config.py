"""Runtime configuration.

Secrets are wrapped in SecretStr so accidental logging shows ``**********``.
Production environments must provide real secrets; the development defaults are
only accepted when env is ``dev`` or ``test``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONTRACT = _REPO_ROOT / "specs" / "001-mcp-server" / "contracts" / "tools.yaml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PINGCE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "dev"

    # MCP server
    mcp_auth_mode: Literal["api_key", "oauth"] = "api_key"
    mcp_api_key_pepper: SecretStr = SecretStr("dev-pepper-change-me")
    mcp_cursor_secret: SecretStr = SecretStr("dev-cursor-change-me")
    mcp_contracts_path: Path = _DEFAULT_CONTRACT
    mcp_max_result_bytes: int = 65536
    mcp_max_page_size: int = 100
    mcp_max_request_bytes: int = 262144
    mcp_tool_timeout_seconds: int = 25
    mcp_cursor_ttl_seconds: int = 900

    # Platform core datastores
    database_url: str = ""
    read_replica_url: str = ""
    redis_url: str = "redis://localhost:6379/0"

    # Object storage
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_root: Path = Path("var/assets")
    oss_endpoint: str = ""
    oss_bucket: str = ""
    oss_access_key: SecretStr = SecretStr("")
    oss_secret_key: SecretStr = SecretStr("")
    oss_region: str = "us-east-1"
    oss_secure: bool = True
    oss_path_style: bool = False
    oss_presign_ttl_seconds: int = 900
    oss_public_bucket: bool = False

    # MCP datastores
    mcp_db_dsn: str = ""
    mcp_audit_dsn: str = ""
    mcp_redis_url: str = "redis://localhost:6379/0"

    # Dotted path to a callable(Settings) -> ServiceRegistry. Required in prod.
    mcp_services_factory: str = ""

    @property
    def read_database_url(self) -> str:
        """Read replica DSN, falling back to the writable database."""
        return self.read_replica_url or self.database_url

    # Rate limits
    mcp_rate_limit_key_per_min: int = 120
    mcp_rate_limit_tenant_per_min: int = 600
    mcp_rate_limit_heavy_per_min: int = 30
    mcp_rate_limit_heavy_tools: tuple[str, ...] = ("preview_samples", "get_run_items")

    # Transport
    mcp_dns_rebinding_protection: bool = True
    mcp_allowed_hosts: tuple[str, ...] = ("127.0.0.1:*", "localhost:*", "[::1]:*")

    # OAuth 2.1 (reserved; not enabled in P0)
    mcp_oauth_issuer: str | None = None
    mcp_oauth_audience: str | None = None
    mcp_oauth_jwks_url: str | None = None
    mcp_oauth_resource_metadata_url: str | None = None

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        if self.env.lower() in {"prod", "production"}:
            if self.mcp_api_key_pepper.get_secret_value() == "dev-pepper-change-me":
                raise ValueError("MCP_API_KEY_PEPPER must be set in production")
            if self.mcp_cursor_secret.get_secret_value() == "dev-cursor-change-me":
                raise ValueError("MCP_CURSOR_SECRET must be set in production")
            if not self.mcp_db_dsn:
                raise ValueError("MCP_DB_DSN is required in production")
            if not self.mcp_audit_dsn:
                raise ValueError("MCP_AUDIT_DSN is required in production")
            if not self.mcp_redis_url:
                raise ValueError("MCP_REDIS_URL is required in production")
        if self.mcp_auth_mode == "oauth":
            missing = [
                name
                for name, value in (
                    ("MCP_OAUTH_ISSUER", self.mcp_oauth_issuer),
                    ("MCP_OAUTH_AUDIENCE", self.mcp_oauth_audience),
                    ("MCP_OAUTH_JWKS_URL", self.mcp_oauth_jwks_url),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"OAuth mode requires: {', '.join(missing)}")
        if self.mcp_max_result_bytes <= 0:
            raise ValueError("MCP_MAX_RESULT_BYTES must be positive")
        if self.read_replica_url and not self.database_url:
            raise ValueError("READ_REPLICA_URL requires DATABASE_URL")
        if not 0 < self.oss_presign_ttl_seconds <= 900:
            raise ValueError("OSS_PRESIGN_TTL_SECONDS must be between 1 and 900")
        if self.oss_public_bucket:
            raise ValueError("OSS_PUBLIC_BUCKET must be false; buckets are private")
        if self.storage_backend == "s3":
            missing = [
                name
                for name, value in (
                    ("OSS_ENDPOINT", self.oss_endpoint),
                    ("OSS_BUCKET", self.oss_bucket),
                    ("OSS_ACCESS_KEY", self.oss_access_key.get_secret_value()),
                    ("OSS_SECRET_KEY", self.oss_secret_key.get_secret_value()),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"S3 storage requires: {', '.join(missing)}")
        return self


def get_settings() -> Settings:
    return Settings()
