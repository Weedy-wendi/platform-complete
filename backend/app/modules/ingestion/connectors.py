"""Built-in connectors and the connector registry (ING-01..03)."""

from __future__ import annotations

import bz2
import codecs
import csv
import gzip
import io
import json
import lzma
import time
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO

from app.core.clock import utcnow_naive
from app.core.errors import InvalidArgumentError, UpstreamUnavailableError
from app.modules.ingestion.public import Connector, ConnectorCursor, ConnectorField, StorageReader
from app.modules.ingestion.schema import infer_schema
from app.modules.ingestion.storage import S3StorageReader

ConnectorFactory = Callable[[dict[str, Any]], Connector]

_DETECT_BYTES = 64 * 1024
_ZIP_MEMBER_SUFFIXES = {".csv", ".jsonl"}


@contextmanager
def _open_binary(path: Path) -> Iterator[Any]:
    """Open a plain, compressed or single-member zip source as binary."""

    if not path.exists():
        raise InvalidArgumentError("source file does not exist", path=str(path))
    suffix = path.suffix.lower()
    if suffix == ".gz":
        with gzip.open(path, "rb") as handle:
            yield handle
    elif suffix == ".bz2":
        with bz2.open(path, "rb") as handle:
            yield handle
    elif suffix == ".xz":
        with lzma.open(path, "rb") as handle:
            yield handle
    elif suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            if len(members) != 1:
                raise InvalidArgumentError(
                    "zip archive must contain exactly one csv or jsonl file",
                    path=str(path),
                    members=len(members),
                )
            member = members[0]
            if Path(member.filename).suffix.lower() not in _ZIP_MEMBER_SUFFIXES:
                raise InvalidArgumentError(
                    "zip member must be a csv or jsonl file",
                    path=str(path),
                    member=member.filename,
                )
            with archive.open(member) as handle:
                yield handle
    else:
        with path.open("rb") as handle:
            yield handle


def _detect_encoding(handle: Any, path: Path) -> str:
    prefix = handle.read(_DETECT_BYTES)
    try:
        handle.seek(0)
    except (OSError, io.UnsupportedOperation) as exc:
        raise InvalidArgumentError("source is not seekable; specify encoding explicitly", path=str(path)) from exc
    if prefix.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    try:
        codecs.getincrementaldecoder("utf-8")().decode(prefix, final=False)
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        codecs.getincrementaldecoder("gbk")().decode(prefix, final=False)
        return "gbk"
    except UnicodeDecodeError as exc:
        raise InvalidArgumentError(
            "unable to detect source encoding; specify encoding explicitly",
            path=str(path),
        ) from exc


@contextmanager
def _open_text(path: Path, encoding: str | None) -> Iterator[TextIO]:
    with _open_binary(path) as binary:
        chosen = encoding or _detect_encoding(binary, path)
        try:
            wrapper = io.TextIOWrapper(binary, encoding=chosen, newline="")
        except LookupError as exc:
            raise InvalidArgumentError("unknown encoding", encoding=chosen) from exc
        try:
            yield wrapper
        finally:
            # The binary context manager owns the descriptor lifetime.
            try:
                wrapper.detach()
            except (OSError, ValueError):
                pass


@contextmanager
def _open_storage_binary(reader: StorageReader, key: str) -> Iterator[Any]:
    """Open a plain, compressed or single-member zip storage object."""

    if not reader.exists(key):
        raise InvalidArgumentError("source object does not exist", key=key)
    buffer = io.BytesIO(reader.read_bytes(key))
    suffix = Path(key).suffix.lower()
    if suffix == ".gz":
        with gzip.GzipFile(fileobj=buffer, mode="rb") as handle:
            yield handle
    elif suffix == ".bz2":
        with bz2.BZ2File(buffer, mode="rb") as handle:
            yield handle
    elif suffix == ".xz":
        with lzma.LZMAFile(buffer, mode="rb") as handle:
            yield handle
    elif suffix == ".zip":
        with zipfile.ZipFile(buffer) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            if len(members) != 1:
                raise InvalidArgumentError(
                    "zip archive must contain exactly one csv or jsonl file",
                    key=key,
                    members=len(members),
                )
            member = members[0]
            if Path(member.filename).suffix.lower() not in _ZIP_MEMBER_SUFFIXES:
                raise InvalidArgumentError(
                    "zip member must be a csv or jsonl file",
                    key=key,
                    member=member.filename,
                )
            with archive.open(member) as handle:
                yield handle
    else:
        yield buffer


@contextmanager
def _open_storage_text(reader: StorageReader, key: str, encoding: str | None) -> Iterator[TextIO]:
    with _open_storage_binary(reader, key) as binary:
        path = Path(key)
        chosen = encoding or _detect_encoding(binary, path)
        try:
            wrapper = io.TextIOWrapper(binary, encoding=chosen, newline="")
        except LookupError as exc:
            raise InvalidArgumentError("unknown encoding", encoding=chosen) from exc
        try:
            yield wrapper
        finally:
            try:
                wrapper.detach()
            except (OSError, ValueError):
                pass


def _iter_jsonl_rows(handle: TextIO) -> Iterator[dict[str, Any]]:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InvalidArgumentError("invalid jsonl line", line=line[:120]) from exc
        if not isinstance(value, dict):
            raise InvalidArgumentError("jsonl rows must be objects")
        yield value


class CsvConnector:
    """Streaming CSV connector with encoding/archive auto-detection."""

    def __init__(
        self,
        path: str | Path,
        *,
        encoding: str | None = None,
        delimiter: str = ",",
    ) -> None:
        self.path = Path(path)
        self.encoding = encoding
        self.delimiter = delimiter

    def _open(self) -> Any:
        return _open_text(self.path, self.encoding)

    def _reader(self, handle: Any) -> csv.DictReader:
        return csv.DictReader(handle, delimiter=self.delimiter)

    def discover(self) -> list[ConnectorField]:
        with self._open() as handle:
            row = next(self._reader(handle), None)
        return infer_schema([dict(row)]) if row is not None else []

    def read(self, cursor: ConnectorCursor, limit: int) -> tuple[list[dict[str, Any]], ConnectorCursor]:
        if limit < 1:
            raise InvalidArgumentError("limit must be >= 1")
        offset = int(cursor.value or "0")
        rows: list[dict[str, Any]] = []
        try:
            with self._open() as handle:
                for index, row in enumerate(self._reader(handle)):
                    if index < offset:
                        continue
                    if len(rows) >= limit:
                        break
                    rows.append(dict(row))
        except UnicodeDecodeError as exc:
            raise InvalidArgumentError(
                "csv encoding error; specify the correct encoding",
                encoding=self.encoding,
                position=exc.start,
            ) from exc
        if not rows:
            return [], ConnectorCursor(value=None, updated_at=cursor.updated_at)
        return rows, ConnectorCursor(value=str(offset + len(rows)), updated_at=utcnow_naive())


class JsonlConnector:
    """Line-delimited JSON connector with encoding/archive auto-detection."""

    def __init__(self, path: str | Path, *, encoding: str | None = None) -> None:
        self.path = Path(path)
        self.encoding = encoding

    def _iter_rows(self) -> Iterator[dict[str, Any]]:
        with _open_text(self.path, self.encoding) as handle:
            yield from _iter_jsonl_rows(handle)

    def discover(self) -> list[ConnectorField]:
        first = next(self._iter_rows(), None)
        return infer_schema([first]) if first is not None else []

    def read(self, cursor: ConnectorCursor, limit: int) -> tuple[list[dict[str, Any]], ConnectorCursor]:
        if limit < 1:
            raise InvalidArgumentError("limit must be >= 1")
        offset = int(cursor.value or "0")
        rows: list[dict[str, Any]] = []
        for index, row in enumerate(self._iter_rows()):
            if index < offset:
                continue
            if len(rows) >= limit:
                break
            rows.append(row)
        if not rows:
            return [], ConnectorCursor(value=None, updated_at=cursor.updated_at)
        return rows, ConnectorCursor(value=str(offset + len(rows)), updated_at=utcnow_naive())


class ObjectStorageConnector:
    """CSV/JSONL connector reading through a :class:`StorageReader`.

    Keys are inspected for the same ``.gz``/``.bz2``/``.xz``/``.zip`` suffixes
    as local files, so object storage inherits identical archive and encoding
    behaviour.
    """

    def __init__(
        self,
        reader: StorageReader,
        key: str,
        *,
        encoding: str | None = None,
        delimiter: str = ",",
        format: str | None = None,
    ) -> None:
        if not key.strip():
            raise InvalidArgumentError("storage key is required")
        self.reader = reader
        self.key = key
        self.encoding = encoding
        self.delimiter = delimiter
        self.format = format.lower() if format else None

    def _resolved_format(self) -> str:
        if self.format:
            if self.format not in {"csv", "jsonl"}:
                raise InvalidArgumentError("storage format must be csv or jsonl", format=self.format)
            return self.format
        suffix = Path(self.key).suffix.lower()
        if suffix in {".gz", ".bz2", ".xz"}:
            suffix = Path(self.key).with_suffix("").suffix.lower()
        if suffix == ".zip":
            if not self.reader.exists(self.key):
                raise InvalidArgumentError("source object does not exist", key=self.key)
            with zipfile.ZipFile(io.BytesIO(self.reader.read_bytes(self.key))) as archive:
                members = [info for info in archive.infolist() if not info.is_dir()]
                if len(members) != 1:
                    raise InvalidArgumentError(
                        "zip archive must contain exactly one csv or jsonl file",
                        key=self.key,
                        members=len(members),
                    )
                suffix = Path(members[0].filename).suffix.lower()
        if suffix == ".csv":
            return "csv"
        if suffix == ".jsonl":
            return "jsonl"
        raise InvalidArgumentError("cannot infer storage object format; specify format", key=self.key)

    def _open(self) -> Any:
        return _open_storage_text(self.reader, self.key, self.encoding)

    def _iter_rows(self, handle: TextIO) -> Iterator[dict[str, Any]]:
        if self._resolved_format() == "csv":
            for row in csv.DictReader(handle, delimiter=self.delimiter):
                yield dict(row)
        else:
            yield from _iter_jsonl_rows(handle)

    def discover(self) -> list[ConnectorField]:
        with self._open() as handle:
            row = next(self._iter_rows(handle), None)
        return infer_schema([row]) if row is not None else []

    def read(self, cursor: ConnectorCursor, limit: int) -> tuple[list[dict[str, Any]], ConnectorCursor]:
        if limit < 1:
            raise InvalidArgumentError("limit must be >= 1")
        offset = int(cursor.value or "0")
        rows: list[dict[str, Any]] = []
        try:
            with self._open() as handle:
                for index, row in enumerate(self._iter_rows(handle)):
                    if index < offset:
                        continue
                    if len(rows) >= limit:
                        break
                    rows.append(row)
        except UnicodeDecodeError as exc:
            raise InvalidArgumentError(
                "csv encoding error; specify the correct encoding",
                encoding=self.encoding,
                position=exc.start,
            ) from exc
        if not rows:
            return [], ConnectorCursor(value=None, updated_at=cursor.updated_at)
        return rows, ConnectorCursor(value=str(offset + len(rows)), updated_at=utcnow_naive())


def _extract(payload: Any, path: str | None) -> Any:
    if not path:
        return payload
    value = payload
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit():
            value = value[int(part)]
        else:
            return None
    return value


class RestConnector:
    """Paginated REST/HTTP connector with retry and a hard timeout.

    ``httpx`` is imported lazily so the module can be used without the optional
    HTTP client (tests inject a fake ``client``).
    """

    def __init__(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data_path: str | None = None,
        page_param: str = "page",
        size_param: str = "limit",
        start_page: int = 1,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.05,
        client: Any | None = None,
    ) -> None:
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.data_path = data_path
        self.page_param = page_param
        self.size_param = size_param
        self.start_page = start_page
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._client = client

    def _http_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - dependency is installed in dev
            raise UpstreamUnavailableError("httpx is required for REST ingestion") from exc
        self._client = httpx.Client(timeout=self.timeout_seconds)
        return self._client

    def _request(self, params: dict[str, Any]) -> Any:
        client = self._http_client()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.request(
                    self.method,
                    self.url,
                    params=params,
                    headers=self.headers,
                )
                if hasattr(response, "raise_for_status"):
                    response.raise_for_status()
                return response.json()
            except Exception as exc:  # noqa: BLE001 - retried and wrapped below
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
        raise UpstreamUnavailableError("REST connector request failed") from last_error

    def _fetch(self, page: int, limit: int) -> list[dict[str, Any]]:
        params = {self.page_param: page, self.size_param: limit}
        payload = self._request(params)
        rows = _extract(payload, self.data_path)
        if rows is None:
            return []
        if not isinstance(rows, list):
            raise InvalidArgumentError("REST data_path must point to a list")
        return [dict(row) for row in rows if isinstance(row, dict)]

    def discover(self) -> list[ConnectorField]:
        return infer_schema(self._fetch(self.start_page, 1))

    def read(self, cursor: ConnectorCursor, limit: int) -> tuple[list[dict[str, Any]], ConnectorCursor]:
        if limit < 1:
            raise InvalidArgumentError("limit must be >= 1")
        page = int(cursor.value or str(self.start_page))
        rows = self._fetch(page, limit)
        if not rows:
            return [], ConnectorCursor(value=None, updated_at=cursor.updated_at)
        return rows, ConnectorCursor(value=str(page + 1), updated_at=utcnow_naive())


class ConnectorRegistry:
    """Pluggable connector registry (kind -> factory)."""

    def __init__(self) -> None:
        self._factories: dict[str, ConnectorFactory] = {}

    def register(self, kind: str, factory: ConnectorFactory) -> None:
        if not kind.strip():
            raise InvalidArgumentError("connector kind is required")
        self._factories[kind] = factory

    def create(self, kind: str, config: dict[str, Any]) -> Connector:
        factory = self._factories.get(kind)
        if factory is None:
            raise InvalidArgumentError("unsupported connector kind", kind=kind)
        return factory(config)

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


def _create_s3_connector(config: dict[str, Any]) -> Connector:
    options = dict(config)
    reader = options.pop("reader", None)
    if reader is None:
        bucket = options.pop("bucket", None)
        if not bucket:
            raise InvalidArgumentError("S3 bucket is required")
        reader = S3StorageReader(
            bucket=bucket,
            prefix=options.pop("prefix", ""),
            client=options.pop("client", None),
        )
    return ObjectStorageConnector(reader, **options)


def default_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    registry.register("csv", lambda config: CsvConnector(**config))
    registry.register("jsonl", lambda config: JsonlConnector(**config))
    registry.register("rest", lambda config: RestConnector(**config))
    registry.register("http", lambda config: RestConnector(**config))
    registry.register("oss", lambda config: ObjectStorageConnector(**config))
    registry.register("s3", _create_s3_connector)
    return registry


__all__ = [
    "ConnectorRegistry",
    "CsvConnector",
    "JsonlConnector",
    "ObjectStorageConnector",
    "RestConnector",
    "default_registry",
]
