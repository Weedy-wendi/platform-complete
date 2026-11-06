"""Application service composition for the MCP adapter.

The MCP layer depends on these services only. In a full deployment the platform
constructs SQL-backed repositories; this repository ships deterministic
in-memory repositories so the adapter is testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.badcases import BadcaseService
from app.services.datasets import DatasetService
from app.services.evaluation import EvaluationService
from app.services.gate import GateReader, UnavailableGateReader
from app.services.projects import ProjectService
from app.services.repositories import (
    InMemoryDatasetRepository,
    InMemoryEvaluatorRepository,
    InMemoryProjectRepository,
    InMemoryRunRepository,
)
from app.services.search import SemanticSearch, UnavailableSemanticSearch


@dataclass(frozen=True)
class ServiceRegistry:
    projects: ProjectService
    datasets: DatasetService
    evaluation: EvaluationService
    badcases: BadcaseService
    gate: GateReader


def build_services(
    *,
    projects: ProjectService | None = None,
    datasets: DatasetService | None = None,
    evaluation: EvaluationService | None = None,
    badcases: BadcaseService | None = None,
    gate: GateReader | None = None,
    semantic_search: SemanticSearch | None = None,
) -> ServiceRegistry:
    return ServiceRegistry(
        projects=projects or ProjectService(InMemoryProjectRepository()),
        datasets=datasets or DatasetService(InMemoryDatasetRepository()),
        evaluation=evaluation or EvaluationService(InMemoryEvaluatorRepository(), InMemoryRunRepository()),
        badcases=badcases or BadcaseService(semantic_search or UnavailableSemanticSearch()),
        gate=gate or UnavailableGateReader(),
    )


def build_empty_services() -> ServiceRegistry:
    return ServiceRegistry(
        projects=ProjectService(InMemoryProjectRepository()),
        datasets=DatasetService(InMemoryDatasetRepository()),
        evaluation=EvaluationService(InMemoryEvaluatorRepository(), InMemoryRunRepository()),
        badcases=BadcaseService(UnavailableSemanticSearch()),
        gate=UnavailableGateReader(),
    )


__all__ = [
    "ServiceRegistry",
    "build_services",
    "build_empty_services",
]
