"""CSV/JSONL/REST connector tests (ING-02/03)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.ingestion.connectors import CsvConnector, JsonlConnector, RestConnector
from app.modules.ingestion.public import ConnectorCursor


def test_csv_parse_utf8_and_cursor(tmp_path) -> None:
    path = tmp_path / "samples.csv"
    path.write_text("id,name\n1,Alice\n2,Bob\n3,Carol\n", encoding="utf-8")
    connector = CsvConnector(path)

    assert [field.name for field in connector.discover()] == ["id", "name"]

    first, cursor = connector.read(ConnectorCursor(), 2)
    assert first == [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
    assert cursor.value == "2"

    second, cursor = connector.read(cursor, 2)
    assert second == [{"id": "3", "name": "Carol"}]
    assert cursor.value == "3"

    empty, cursor = connector.read(cursor, 2)
    assert empty == []
    assert cursor.value is None


def test_csv_gbk_encoding(tmp_path) -> None:
    path = tmp_path / "gbk.csv"
    path.write_bytes("id,问题\n1,登录失败\n".encode("gbk"))
    connector = CsvConnector(path, encoding="gbk")
    rows, _ = connector.read(ConnectorCursor(), 10)
    assert rows == [{"id": "1", "问题": "登录失败"}]


def test_csv_bad_encoding_raises_clear_error(tmp_path) -> None:
    path = tmp_path / "bad.csv"
    path.write_bytes("id,name\n1,登录\n".encode("gbk"))
    connector = CsvConnector(path, encoding="utf-8")
    with pytest.raises(InvalidArgumentError):
        connector.read(ConnectorCursor(), 10)


def test_csv_custom_delimiter(tmp_path) -> None:
    path = tmp_path / "tabs.csv"
    path.write_text("id\tname\n1\tAlice\n", encoding="utf-8")
    connector = CsvConnector(path, delimiter="\t")
    rows, _ = connector.read(ConnectorCursor(), 10)
    assert rows == [{"id": "1", "name": "Alice"}]


def test_jsonl_connector(tmp_path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text('{"id": 1}\n{"id": 2, "tag": "x"}\n', encoding="utf-8")
    connector = JsonlConnector(path)
    rows, cursor = connector.read(ConnectorCursor(), 1)
    assert rows == [{"id": 1}]
    rest, _ = connector.read(cursor, 10)
    assert rest == [{"id": 2, "tag": "x"}]


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self, pages: dict[int, Any]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, str, dict[str, Any], dict[str, str]]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> _FakeResponse:
        self.calls.append((method, url, params, headers))
        return _FakeResponse(self.pages[int(params["page"])])


def test_rest_connector_pagination_auth_and_shapes() -> None:
    client = _FakeClient(
        {
            1: {"data": {"items": [{"id": 1}, {"id": 2}]}},
            2: {"data": {"items": [{"id": 3}]}},
            3: {"data": {"items": []}},
        }
    )
    connector = RestConnector(
        "https://api.example.test/rows",
        data_path="data.items",
        headers={"Authorization": "Bearer token"},
        client=client,
        max_retries=0,
    )
    rows, cursor = connector.read(ConnectorCursor(), 2)
    assert rows == [{"id": 1}, {"id": 2}]
    assert cursor.value == "2"
    assert client.calls[0][0] == "GET"
    assert client.calls[0][2] == {"page": 1, "limit": 2}
    assert client.calls[0][3] == {"Authorization": "Bearer token"}

    rows, cursor = connector.read(cursor, 2)
    assert rows == [{"id": 3}]
    assert cursor.value == "3"

    rows, cursor = connector.read(cursor, 2)
    assert rows == []
    assert cursor.value is None


def test_rest_connector_requires_list_payload() -> None:
    client = _FakeClient({1: {"data": "not-a-list"}})
    connector = RestConnector("https://api.example.test/rows", data_path="data", client=client, max_retries=0)
    with pytest.raises(InvalidArgumentError):
        connector.read(ConnectorCursor(), 10)


def test_rest_connector_payload_json_roundtrip() -> None:
    client = _FakeClient({1: json.loads('{"items": [{"id": 1}]}')})
    connector = RestConnector("https://api.example.test/rows", data_path="items", client=client, max_retries=0)
    rows, _ = connector.read(ConnectorCursor(), 10)
    assert rows == [{"id": 1}]
