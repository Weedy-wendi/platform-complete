"""Identifier helpers.

ULID-like identifiers are time-sortable, which keeps keyset pagination stable.
API key ids are hex so they can be split out of ``pk_<env>_<key_id>_<secret>``
without ambiguity.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    chars: list[str] = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        chars.append(_ALPHABET[rem])
    return "".join(reversed(chars))


def new_ulid(now: datetime | None = None) -> str:
    """Return a 26-character ULID-like identifier."""
    moment = now or datetime.now(UTC)
    timestamp_ms = int(moment.timestamp() * 1000)
    random_part = secrets.randbits(80)
    return _encode(timestamp_ms, 10) + _encode(random_part, 16)


def new_key_id() -> str:
    """Return a 24-character hex key id."""
    return secrets.token_hex(12)


def new_secret() -> str:
    """Return a 256-bit URL-safe API key secret."""
    return secrets.token_urlsafe(32)


def new_trace_id() -> str:
    """Return a 32-character hex trace id."""
    return secrets.token_hex(16)
