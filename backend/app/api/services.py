"""Service container injected into the REST application."""

from __future__ import annotations

from dataclasses import dataclass

from app.api.memory import (
    InMemoryAdmin,
    InMemoryDatasets,
    InMemoryDatasources,
    InMemoryEvaluation,
    InMemoryFunctional,
    InMemoryGates,
    InMemoryProjects,
    InMemoryReports,
    InMemorySearch,
    InMemorySuites,
    InMemoryTargets,
)
from app.api.pagination import CursorCodec
from app.api.ports import (
    AdminPort,
    DatasetsPort,
    DatasourcesPort,
    EvaluationPort,
    FunctionalPort,
    GatePort,
    ProjectsPort,
    ReportsPort,
    SearchPort,
    SuitesPort,
    TargetsPort,
)
from app.modules.audit.public import AuditLogWriter


@dataclass(frozen=True)
class ApiServices:
    projects: ProjectsPort
    datasets: DatasetsPort
    datasources: DatasourcesPort
    evaluation: EvaluationPort
    suites: SuitesPort
    targets: TargetsPort
    gates: GatePort
    reports: ReportsPort
    search: SearchPort
    admin: AdminPort
    functional: FunctionalPort
    audit_writer: AuditLogWriter | None = None


def build_api_services(
    *,
    projects: ProjectsPort | None = None,
    datasets: DatasetsPort | None = None,
    datasources: DatasourcesPort | None = None,
    evaluation: EvaluationPort | None = None,
    suites: SuitesPort | None = None,
    targets: TargetsPort | None = None,
    gates: GatePort | None = None,
    reports: ReportsPort | None = None,
    search: SearchPort | None = None,
    admin: AdminPort | None = None,
    functional: FunctionalPort | None = None,
    audit_writer: AuditLogWriter | None = None,
    cursor_secret: str | None = None,
    cursor_ttl_seconds: int = 900,
    key_env: str = "dev",
) -> ApiServices:
    codec = CursorCodec(cursor_secret, ttl_seconds=cursor_ttl_seconds)
    projects = projects or InMemoryProjects(codec=codec)
    datasets = datasets or InMemoryDatasets(projects, codec=codec)
    datasources = datasources or InMemoryDatasources(codec=codec)
    evaluation = evaluation or InMemoryEvaluation(codec=codec)
    suites = suites or InMemorySuites(codec=codec)
    targets = targets or InMemoryTargets(codec=codec)
    gates = gates or InMemoryGates()
    reports = reports or InMemoryReports(evaluation)
    search = search or InMemorySearch()
    admin = admin or InMemoryAdmin(key_env=key_env)
    functional = functional or InMemoryFunctional(codec=codec)
    return ApiServices(
        projects=projects,
        datasets=datasets,
        datasources=datasources,
        evaluation=evaluation,
        suites=suites,
        targets=targets,
        gates=gates,
        reports=reports,
        search=search,
        admin=admin,
        functional=functional,
        audit_writer=audit_writer,
    )


__all__ = ["ApiServices", "build_api_services"]
