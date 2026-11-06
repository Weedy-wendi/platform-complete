from pathlib import Path

SQL = Path(__file__).resolve().parents[2] / "deploy" / "sql" / "mcp_grants.sql"


def _grants() -> list[str]:
    lines = [line.strip() for line in SQL.read_text(encoding="utf-8").splitlines()]
    return [line.upper() for line in lines if line.startswith("GRANT ")]


def test_read_only_business_account() -> None:
    grants = _grants()
    assert any("GRANT SELECT ON PINGCE.* TO 'PINGCE_MCP_RO'" in grant for grant in grants)


def test_audit_account_only_inserts() -> None:
    grants = _grants()
    audit_grants = [grant for grant in grants if "PINGCE_MCP_AUDIT" in grant]
    assert len(audit_grants) == 1
    assert audit_grants[0].startswith("GRANT INSERT ON PINGCE.MCP_TOOL_CALL")


def test_no_write_or_ddl_grants() -> None:
    grants = " ".join(_grants())
    for forbidden in ("GRANT UPDATE", "GRANT DELETE", "GRANT CREATE", "GRANT ALTER", "GRANT DROP"):
        assert forbidden not in grants
