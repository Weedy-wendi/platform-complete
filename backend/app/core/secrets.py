"""Secret reference resolution.

Provider and datasource records only store a ``secret://`` reference; the
plaintext value is resolved at call time and never persisted or logged.

Supported schemes:

- ``secret://env/NAME``  -> environment variable ``NAME``
- ``secret://file/PATH`` -> file contents (trimmed)

Other schemes are intentionally rejected by the resolver; a deployment may
inject its own resolver (Vault, AWS Secrets Manager, ...) through the model
gateway constructor.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from app.core.errors import InvalidArgumentError

_PREFIX = "secret://"


class SecretResolver(Protocol):
    def resolve(self, ref: str) -> str: ...


class EnvSecretResolver:
    """Resolve environment/file references without persisting the secret."""

    def resolve(self, ref: str) -> str:
        if not ref.startswith(_PREFIX):
            raise InvalidArgumentError("secret reference must use the secret:// scheme")
        scheme, _, path = ref[len(_PREFIX) :].partition("/")
        if not scheme or not path:
            raise InvalidArgumentError("secret reference is malformed", secret_ref=ref)
        if scheme == "env":
            value = os.environ.get(path)
            if value is None or value == "":
                raise InvalidArgumentError("secret environment variable is not set", secret_ref=ref)
            return value
        if scheme == "file":
            file_path = Path(path)
            if not file_path.is_file():
                raise InvalidArgumentError("secret file does not exist", secret_ref=ref)
            value = file_path.read_text(encoding="utf-8").strip()
            if not value:
                raise InvalidArgumentError("secret file is empty", secret_ref=ref)
            return value
        raise InvalidArgumentError("unsupported secret scheme", scheme=scheme)


DEFAULT_SECRET_RESOLVER = EnvSecretResolver()


def should_resolve(ref: str) -> bool:
    """Only resolve schemes this deployment knows how to read."""

    return ref.startswith("secret://env/") or ref.startswith("secret://file/")


__all__ = ["DEFAULT_SECRET_RESOLVER", "EnvSecretResolver", "SecretResolver", "should_resolve"]
