"""Browser sandbox metadata and network allowlist helpers (FUN-03)."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.core.errors import InvalidArgumentError
from app.modules.functional.public import NetworkPolicyError


@dataclass(frozen=True)
class BrowserSandboxConfig:
    """Resource limits and pinned browser image for a run."""

    browser_version: str = "chromium-1200"
    image_digest: str = "sha256:pinned"
    cpu_limit: float = 1.0
    memory_mb: int = 1024
    disk_mb: int = 2048
    network_allowlist: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.cpu_limit <= 0 or self.memory_mb <= 0 or self.disk_mb <= 0:
            raise InvalidArgumentError("browser resource limits must be positive")
        if self.timeout_seconds <= 0:
            raise InvalidArgumentError("browser timeout must be positive")


def host_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        raise InvalidArgumentError("browser step requires an absolute URL")
    return host


def is_host_allowed(url: str, allow_hosts: tuple[str, ...]) -> bool:
    """Match exact hosts and ``*.example.com`` wildcards."""

    if not allow_hosts:
        return True
    host = host_of(url)
    for pattern in allow_hosts:
        candidate = pattern.strip().lower()
        if not candidate:
            continue
        if candidate.startswith("*."):
            suffix = candidate[1:]
            if host.endswith(suffix) and host != suffix.lstrip("."):
                return True
        elif host == candidate:
            return True
    return False


def ensure_host_allowed(url: str, allow_hosts: tuple[str, ...]) -> None:
    if not is_host_allowed(url, allow_hosts):
        raise NetworkPolicyError(f"host is not in the network allowlist: {host_of(url)}")


__all__ = [
    "BrowserSandboxConfig",
    "ensure_host_allowed",
    "host_of",
    "is_host_allowed",
]
