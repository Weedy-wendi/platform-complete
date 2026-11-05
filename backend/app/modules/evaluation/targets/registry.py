"""Target adapter registry with optional entry-point discovery."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable
from typing import Any

from app.core.errors import InvalidArgumentError
from app.modules.evaluation.targets.config import TargetConfig, validate_target_config
from app.modules.evaluation.types import TargetAdapter

AdapterFactory = Callable[..., TargetAdapter]


class TargetRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, AdapterFactory] = {}

    def register(self, name: str, factory: AdapterFactory, *, replace: bool = False) -> None:
        if not name.strip():
            raise InvalidArgumentError("adapter name is required")
        if name in self._factories and not replace:
            raise InvalidArgumentError("adapter is already registered", adapter=name)
        self._factories[name] = factory

    def unregister(self, name: str) -> None:
        self._factories.pop(name, None)

    def get(self, name: str) -> AdapterFactory:
        factory = self._factories.get(name)
        if factory is None:
            raise InvalidArgumentError("unknown target adapter", adapter=name, registered=sorted(self._factories))
        return factory

    def names(self) -> list[str]:
        return sorted(self._factories)

    def create(self, name: str, config: TargetConfig | dict[str, Any], **kwargs: Any) -> TargetAdapter:
        resolved = validate_target_config(config) if isinstance(config, dict) else config
        return self.get(name)(resolved, **kwargs)

    def load_entry_points(self, group: str = "pingce.target_adapters") -> list[str]:
        loaded: list[str] = []
        for entry_point in importlib.metadata.entry_points(group=group):
            factory = entry_point.load()
            self.register(entry_point.name, factory, replace=True)
            loaded.append(entry_point.name)
        return sorted(loaded)


def build_registry() -> TargetRegistry:
    from app.modules.evaluation.targets.http_json import HttpJsonAdapter
    from app.modules.evaluation.targets.openai_compat import OpenAICompatibleAdapter

    registry = TargetRegistry()
    registry.register("http_json", HttpJsonAdapter)
    registry.register("openai_compat", OpenAICompatibleAdapter)
    return registry


DEFAULT_REGISTRY = build_registry()


def build_adapter(
    config: TargetConfig | dict[str, Any],
    *,
    registry: TargetRegistry | None = None,
    **kwargs: Any,
) -> TargetAdapter:
    resolved = validate_target_config(config) if isinstance(config, dict) else config
    return (registry or DEFAULT_REGISTRY).create(resolved.adapter, resolved, **kwargs)
