from pathlib import Path

import yaml

from app.mcp.registry import ToolRegistry

CONTRACT = Path(__file__).resolve().parents[4] / "specs" / "001-mcp-server" / "contracts" / "tools.yaml"


def test_tools_match_contract_snapshot() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    registry = ToolRegistry.from_contract(CONTRACT)
    expected = {item["name"] for item in contract["tools"]}
    actual = set(registry.tool_names)
    assert actual == expected
    assert len(actual) == 10

    listed = {tool.name: tool for tool in registry.list_tools()}
    for item in contract["tools"]:
        tool = listed[item["name"]]
        assert tool.annotations.read_only_hint == item["annotations"]["readOnlyHint"]
        assert tool.annotations.destructive_hint == item["annotations"]["destructiveHint"]
        assert tool.annotations.idempotent_hint == item["annotations"]["idempotentHint"]
        assert tool.annotations.open_world_hint == item["annotations"]["openWorldHint"]


def test_no_write_tool_names() -> None:
    registry = ToolRegistry.from_contract(CONTRACT)
    write_prefixes = ("create_", "update_", "delete_", "start_", "cancel_", "write_", "patch_", "remove_", "drop_")
    assert not any(name.startswith(write_prefixes) for name in registry.tool_names)


def test_resource_templates_match_contract() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    registry = ToolRegistry.from_contract(CONTRACT)
    assert len(registry.list_resource_templates()) == len(contract["resources"]) == 3
