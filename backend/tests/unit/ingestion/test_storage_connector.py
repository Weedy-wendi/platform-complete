"""Object-storage connector and S3 reader tests (ING-11)."""

from __future__ import annotations

import gzip
import sys
import zipfile
from io import BytesIO

import pytest

from app.core.errors import InvalidArgumentError
from app.modules.ingestion.connectors import ObjectStorageConnector, default_registry
from app.modules.ingestion.public import ConnectorCursor
from app.modules.ingestion.storage import S3StorageReader


class FakeStorageReader:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.reads: list[str] = []

    def exists(self, key: str) -> bool:
        return key in self.objects

    def read_bytes(self, key: str) -> bytes:
        self.reads.append(key)
        return self.objects[key]


class FakeS3Client:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.calls: list[tuple[str, str]] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, BytesIO]:
        self.calls.append((Bucket, Key))
        return {"Body": BytesIO(self.objects[Key])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        self.calls.append((Bucket, Key))
        if Key not in self.objects:
            raise RuntimeError("missing")
        return {}


def test_fake_storage_reader_syncs_csv_rows() -> None:
    reader = FakeStorageReader({"exports/samples.csv": b"id,name\n1,Alice\n2,Bob\n3,Carol\n"})
    connector = ObjectStorageConnector(reader, "exports/samples.csv")

    assert [field.name for field in connector.discover()] == ["id", "name"]

    first, cursor = connector.read(ConnectorCursor(), 2)
    assert first == [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
    assert cursor.value == "2"

    second, cursor = connector.read(cursor, 2)
    assert second == [{"id": "3", "name": "Carol"}]
    assert cursor.value == "3"

    exhausted, cursor = connector.read(cursor, 2)
    assert exhausted == []
    assert cursor.value is None


def test_storage_connector_reads_gzip_and_zip_archives() -> None:
    gzip_reader = FakeStorageReader({"samples.csv.gz": gzip.compress(b"id,name\n1,Alice\n")})
    gzip_rows, _ = ObjectStorageConnector(gzip_reader, "samples.csv.gz").read(ConnectorCursor(), 10)
    assert gzip_rows == [{"id": "1", "name": "Alice"}]

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("samples.csv", "id,name\n2,Bob\n")
    zip_reader = FakeStorageReader({"samples.zip": buffer.getvalue()})
    zip_rows, _ = ObjectStorageConnector(zip_reader, "samples.zip").read(ConnectorCursor(), 10)
    assert zip_rows == [{"id": "2", "name": "Bob"}]


def test_storage_connector_reads_jsonl_and_gbk() -> None:
    jsonl = FakeStorageReader({"rows.jsonl": b'{"id": 1}\n{"id": 2}\n'})
    rows, _ = ObjectStorageConnector(jsonl, "rows.jsonl").read(ConnectorCursor(), 10)
    assert rows == [{"id": 1}, {"id": 2}]

    gbk = FakeStorageReader({"rows.csv": "id,姓名\n1,张三\n".encode("gbk")})
    rows, _ = ObjectStorageConnector(gbk, "rows.csv").read(ConnectorCursor(), 10)
    assert rows == [{"id": "1", "姓名": "张三"}]


def test_missing_storage_key_raises_clear_error() -> None:
    connector = ObjectStorageConnector(FakeStorageReader({}), "missing.csv")
    with pytest.raises(InvalidArgumentError):
        connector.read(ConnectorCursor(), 10)
    with pytest.raises(InvalidArgumentError):
        connector.discover()


def test_registry_exposes_oss_and_s3_kinds() -> None:
    registry = default_registry()
    assert {"oss", "s3"}.issubset(set(registry.kinds()))

    reader = FakeStorageReader({"samples.csv": b"id\n1\n"})
    connector = registry.create("oss", {"reader": reader, "key": "samples.csv"})
    rows, _ = connector.read(ConnectorCursor(), 10)
    assert rows == [{"id": "1"}]

    client = FakeS3Client({"exports/samples.csv": b"id\n2\n"})
    s3_connector = registry.create(
        "s3",
        {"bucket": "tests", "prefix": "exports", "key": "samples.csv", "client": client},
    )
    rows, _ = s3_connector.read(ConnectorCursor(), 10)
    assert rows == [{"id": "2"}]
    assert client.calls[0] == ("tests", "exports/samples.csv")


def test_s3_reader_without_boto3_fails_clearly(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "boto3", None)
    with pytest.raises(InvalidArgumentError, match="boto3"):
        S3StorageReader("tests")


def test_s3_reader_uses_bucket_prefix_and_client() -> None:
    client = FakeS3Client({"exports/samples.csv": b"id\n1\n"})
    reader = S3StorageReader("tests", prefix="/exports/", client=client)

    assert reader.exists("samples.csv") is True
    assert reader.read_bytes("samples.csv") == b"id\n1\n"
    assert client.calls[0] == ("tests", "exports/samples.csv")
