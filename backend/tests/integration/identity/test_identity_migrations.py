"""Alembic round-trip for the identity/audit migrations (opt-in testcontainers)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.db import create_engine_from_dsn

_BACKEND = Path(__file__).resolve().parents[3]


def test_identity_and_audit_migrations_round_trip(mysql_dsn: str, monkeypatch) -> None:
    monkeypatch.setenv("PINGCE_MCP_DB_DSN", mysql_dsn)
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "migrations"))

    command.upgrade(config, "head")
    engine = create_engine_from_dsn(mysql_dsn)
    try:
        tables = set(inspect(engine).get_table_names())
        assert {
            "tenant",
            "user",
            "role",
            "permission",
            "user_role",
            "role_permission",
            "audit_log",
            "artifact",
            "project",
            "datasource",
            "dataset",
            "dataset_version",
            "sample",
            "lineage_edge",
            "job",
            "job_event",
            "dead_letter_task",
            "idempotency_key",
            "provider_config",
            "model_call",
            "connector",
            "ingestion_job",
            "sync_cursor",
            "quality_rule",
            "quality_result",
            "test_case",
            "test_suite",
            "test_run",
            "test_step",
            "assertion",
            "visual_diff",
            "evaluator",
            "evaluator_version",
            "metric",
            "eval_suite",
            "suite_version",
            "target",
            "run",
            "run_item",
            "score",
            "judge_call",
            "baseline",
            "gate",
            "gate_rule",
            "gate_result",
            "report_snapshot",
            "read_model_run",
            "ingestion_dead_letter",
            "functional_dead_letter",
        } <= tables

        with engine.connect() as connection:
            partitions = {
                row[0]
                for row in connection.execute(
                    text(
                        """
                        SELECT PARTITION_NAME
                        FROM information_schema.PARTITIONS
                        WHERE TABLE_SCHEMA = DATABASE()
                          AND TABLE_NAME = 'audit_log'
                          AND PARTITION_NAME IS NOT NULL
                        """
                    )
                )
            }
        assert "p202611" in partitions
        assert "pmax" in partitions

        with engine.connect() as connection:
            triggers = {
                row[0]
                for row in connection.execute(
                    text(
                        """
                        SELECT TRIGGER_NAME
                        FROM information_schema.TRIGGERS
                        WHERE TRIGGER_SCHEMA = DATABASE()
                          AND EVENT_OBJECT_TABLE = 'dataset_version'
                        """
                    )
                )
            }
        assert "trg_dataset_version_immutable" in triggers

        with engine.connect() as connection:
            event_triggers = {
                row[0]
                for row in connection.execute(
                    text(
                        """
                        SELECT TRIGGER_NAME
                        FROM information_schema.TRIGGERS
                        WHERE TRIGGER_SCHEMA = DATABASE()
                          AND EVENT_OBJECT_TABLE = 'job_event'
                        """
                    )
                )
            }
        assert {"trg_job_event_no_update", "trg_job_event_no_delete"} <= event_triggers

        command.downgrade(config, "base")
        tables = set(inspect(engine).get_table_names())
        assert "tenant" not in tables
        assert "audit_log" not in tables

        command.upgrade(config, "head")
        tables = set(inspect(engine).get_table_names())
        assert "tenant" in tables
        assert "audit_log" in tables
    finally:
        engine.dispose()
