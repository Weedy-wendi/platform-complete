"""Object-storage readers for ingestion connectors (ING-11).

``boto3`` is optional and imported lazily. Callers that already own a client
(for example tests or a shared session pool) can inject it and avoid the
dependency entirely.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import InvalidArgumentError

_MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound", "NoSuchBucket"})


class S3StorageReader:
    """Minimal S3-compatible :class:`StorageReader` backed by ``boto3``."""

    def __init__(self, bucket: str, prefix: str = "", client: Any | None = None) -> None:
        normalized = bucket.strip()
        if not normalized:
            raise InvalidArgumentError("S3 bucket is required")
        self.bucket = normalized
        self.prefix = prefix.strip("/")
        if client is None:
            try:
                import boto3
            except ImportError as exc:
                raise InvalidArgumentError(
                    "boto3 is required for the S3 storage reader; install the storage extra"
                ) from exc
            client = boto3.client("s3")
        self._client = client

    def _object_key(self, key: str) -> str:
        normalized = key.lstrip("/")
        return f"{self.prefix}/{normalized}" if self.prefix else normalized

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=self._object_key(key))
        except Exception as exc:  # noqa: BLE001 - provider errors are normalised below
            response = getattr(exc, "response", None) or {}
            code = str((response.get("Error") or {}).get("Code", ""))
            if code in _MISSING_CODES or code.startswith("4"):
                return False
            raise
        return True

    def read_bytes(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=self._object_key(key))
        except Exception as exc:  # noqa: BLE001 - provider errors are normalised below
            response = getattr(exc, "response", None) or {}
            code = str((response.get("Error") or {}).get("Code", ""))
            if code in _MISSING_CODES:
                raise InvalidArgumentError("storage object does not exist", key=key) from exc
            raise
        body = response["Body"]
        payload = body.read() if hasattr(body, "read") else body
        if isinstance(payload, str):
            return payload.encode("utf-8")
        if not isinstance(payload, (bytes, bytearray)):
            raise InvalidArgumentError("storage body must be bytes", key=key)
        return bytes(payload)


__all__ = ["S3StorageReader"]
