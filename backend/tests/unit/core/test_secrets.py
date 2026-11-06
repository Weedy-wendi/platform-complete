"""Secret reference resolution (provider secret_ref)."""

from __future__ import annotations

import pytest

from app.core.errors import InvalidArgumentError
from app.core.secrets import EnvSecretResolver, should_resolve


def test_env_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PINGCE_TEST_PROVIDER_KEY", "sk-test")
    assert EnvSecretResolver().resolve("secret://env/PINGCE_TEST_PROVIDER_KEY") == "sk-test"


def test_file_secret(tmp_path) -> None:
    path = tmp_path / "provider.key"
    path.write_text("sk-file\n", encoding="utf-8")
    assert EnvSecretResolver().resolve(f"secret://file/{path.as_posix()}") == "sk-file"


def test_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PINGCE_TEST_MISSING_KEY", raising=False)
    with pytest.raises(InvalidArgumentError):
        EnvSecretResolver().resolve("secret://env/PINGCE_TEST_MISSING_KEY")


def test_unsupported_scheme_raises() -> None:
    with pytest.raises(InvalidArgumentError):
        EnvSecretResolver().resolve("secret://vault/secret/data/key")


def test_should_resolve_only_known_schemes() -> None:
    assert should_resolve("secret://env/KEY")
    assert should_resolve("secret://file/key")
    assert not should_resolve("secret://tenant-a/openai")
