"""Settings-driven REST API entrypoint smoke tests."""

from __future__ import annotations

import pytest

from app.api.server import create_app_from_settings
from app.core.config import Settings


def test_api_server_requires_database_url() -> None:
    with pytest.raises(RuntimeError, match="PINGCE_DATABASE_URL"):
        create_app_from_settings(Settings(env="dev", database_url=""))


def test_api_server_builds_from_settings() -> None:
    app = create_app_from_settings(Settings(env="dev", database_url="sqlite://"))
    assert app.title == "Pingce Platform API"
    assert app.state.authenticator is not None
    assert "database" in app.state.ready_checks
