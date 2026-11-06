"""Dotted-path service factory used by factory tests."""

from __future__ import annotations

from app.core.config import Settings
from app.services import ServiceRegistry
from tests.support.seeds import build_seeded_services


def build_test_services(settings: Settings) -> ServiceRegistry:
    return build_seeded_services()
