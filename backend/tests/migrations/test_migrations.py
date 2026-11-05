from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"


def test_migrations_exist_and_have_downgrade() -> None:
    files = sorted(VERSIONS.glob("*.py"))
    assert [path.name for path in files] == [
        "0001_api_key.py",
        "0002_mcp_tool_call.py",
        "0003_identity.py",
        "0004_audit_log.py",
        "0005_audit_partitions.py",
        "0006_artifact.py",
        "0007_catalog.py",
        "0008_jobs.py",
        "0009_model_gateway.py",
        "0010_ingestion.py",
        "0011_functional.py",
        "0012_evaluation.py",
        "0013_gate.py",
        "0014_reporting.py",
        "0015_ingestion_dead_letter.py",
        "0016_convergence_gaps.py",
    ]
    for path in files:
        content = path.read_text(encoding="utf-8")
        assert "def upgrade()" in content
        assert "def downgrade()" in content


def test_audit_migration_is_partitioned() -> None:
    content = (VERSIONS / "0002_mcp_tool_call.py").read_text(encoding="utf-8")
    assert "PARTITION BY RANGE COLUMNS(created_at)" in content
    assert "p202611" in content
    audit_partitions = (VERSIONS / "0005_audit_partitions.py").read_text(encoding="utf-8")
    assert "PARTITION BY RANGE COLUMNS(created_at)" in audit_partitions
    assert "p202611" in audit_partitions
    assert "REMOVE PARTITIONING" in audit_partitions
