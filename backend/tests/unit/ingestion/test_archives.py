"""Archive and encoding auto-detection for CSV/JSONL connectors (ING-10)."""

from __future__ import annotations

import bz2
import gzip
import lzma
import zipfile

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.ingestion.connectors import CsvConnector, JsonlConnector
from app.modules.ingestion.public import ConnectorCursor


def test_gzip_csv_is_decompressed(tmp_path) -> None:
    path = tmp_path / "samples.csv.gz"
    with gzip.open(path, "wb") as handle:
        handle.write(b"id,name\n1,Alice\n2,Bob\n")

    rows, cursor = CsvConnector(path).read(ConnectorCursor(), 10)

    assert rows == [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
    assert cursor.value == "2"


def test_bz2_and_xz_are_decompressed(tmp_path) -> None:
    payload = b'{"id": "1"}\n'
    for suffix, opener in ((".bz2", bz2.open), (".xz", lzma.open)):
        path = tmp_path / f"rows.jsonl{suffix}"
        with opener(path, "wb") as handle:
            handle.write(payload)
        rows, _ = JsonlConnector(path).read(ConnectorCursor(), 10)
        assert rows == [{"id": "1"}]


def test_zip_with_single_csv_member_is_supported(tmp_path) -> None:
    path = tmp_path / "samples.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("samples.csv", "id,name\n1,Alice\n")

    rows, _ = CsvConnector(path).read(ConnectorCursor(), 10)

    assert rows == [{"id": "1", "name": "Alice"}]


def test_zip_with_multiple_members_is_rejected(tmp_path) -> None:
    path = tmp_path / "many.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("a.csv", "id\n1\n")
        archive.writestr("b.csv", "id\n2\n")

    with pytest.raises(InvalidArgumentError):
        CsvConnector(path).discover()


def test_gbk_is_detected_when_encoding_is_not_configured(tmp_path) -> None:
    path = tmp_path / "gbk.csv"
    path.write_bytes("姓名,城市\n张三,北京\n".encode("gbk"))

    rows, _ = CsvConnector(path).read(ConnectorCursor(), 10)

    assert rows == [{"姓名": "张三", "城市": "北京"}]


def test_explicit_encoding_wins_over_detection(tmp_path) -> None:
    path = tmp_path / "gbk.csv"
    path.write_bytes("姓名\n张三\n".encode("gbk"))

    rows, _ = CsvConnector(path, encoding="gbk").read(ConnectorCursor(), 10)

    assert rows == [{"姓名": "张三"}]
