import pytest

from app.core.config import Settings


def _prod_kwargs(**overrides):
    values = {
        "env": "prod",
        "mcp_api_key_pepper": "real-pepper",
        "mcp_cursor_secret": "real-cursor",
        "mcp_db_dsn": "mysql+pymysql://user:pass@db:3306/pingce",
        "mcp_audit_dsn": "mysql+pymysql://user:pass@db:3306/pingce",
        "mcp_redis_url": "redis://redis:6379/0",
    }
    values.update(overrides)
    return values


def test_production_requires_all_dsns() -> None:
    with pytest.raises(ValueError):
        Settings(**_prod_kwargs(mcp_db_dsn=""))
    with pytest.raises(ValueError):
        Settings(**_prod_kwargs(mcp_audit_dsn=""))
    with pytest.raises(ValueError):
        Settings(**_prod_kwargs(mcp_redis_url=""))


def test_production_accepts_complete_configuration() -> None:
    settings = Settings(**_prod_kwargs())
    assert settings.mcp_db_dsn
    assert settings.mcp_audit_dsn
    assert settings.mcp_redis_url


def test_development_can_run_without_dsns() -> None:
    settings = Settings(env="test", mcp_db_dsn="", mcp_audit_dsn="", mcp_redis_url="")
    assert settings.env == "test"


def test_storage_rejects_public_bucket_and_long_presign_ttl() -> None:
    with pytest.raises(ValueError):
        Settings(env="test", oss_public_bucket=True)
    with pytest.raises(ValueError):
        Settings(env="test", oss_presign_ttl_seconds=901)


def test_s3_backend_requires_connection_fields() -> None:
    with pytest.raises(ValueError):
        Settings(env="test", storage_backend="s3")
