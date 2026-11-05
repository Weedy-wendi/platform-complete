"""S3-compatible adapters used by OSS and MinIO deployments."""

from __future__ import annotations

from typing import Any, Protocol

from app.core.errors import InvalidArgumentError, NotFoundError, UpstreamUnavailableError
from app.modules.assets.storage import (
    MAX_PRESIGN_TTL_SECONDS,
    sha256_hex,
    validate_key,
    validate_ttl,
)


class S3Client(Protocol):
    def put_object(self, **kwargs: Any) -> Any: ...
    def get_object(self, **kwargs: Any) -> Any: ...
    def delete_object(self, **kwargs: Any) -> Any: ...
    def head_bucket(self, **kwargs: Any) -> Any: ...
    def generate_presigned_url(self, operation: str, *, Params: dict[str, Any], ExpiresIn: int) -> str: ...


def _map_client_error(exc: Exception) -> Exception:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return exc
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
    if isinstance(status, int) and 400 <= status < 500:
        if status == 404:
            return NotFoundError("Object not found")
        return InvalidArgumentError("object store rejected the request", status=status)
    return UpstreamUnavailableError("object store is unavailable")


class S3Storage:
    def __init__(self, client: S3Client, *, bucket: str, path_style: bool = False) -> None:
        self._client = client
        self._bucket = bucket
        self._path_style = path_style

    @property
    def bucket(self) -> str:
        return self._bucket

    def put(self, key: str, data: bytes, *, content_type: str) -> str:
        validate_key(key)
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except Exception as exc:
            mapped = _map_client_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc
        return sha256_hex(data)

    def get(self, key: str) -> bytes:
        validate_key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            mapped = _map_client_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc
        body = response.get("Body")
        if body is None:
            return b""
        return body.read() if hasattr(body, "read") else bytes(body)

    def delete(self, key: str) -> None:
        validate_key(key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            mapped = _map_client_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc

    def presign_get(self, key: str, *, ttl_seconds: int = MAX_PRESIGN_TTL_SECONDS) -> str:
        validate_key(key)
        validate_ttl(ttl_seconds)
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )

    def presign_put(self, key: str, *, ttl_seconds: int = MAX_PRESIGN_TTL_SECONDS) -> str:
        validate_key(key)
        validate_ttl(ttl_seconds)
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )

    def healthcheck(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            return False
        return True


class OssStorage(S3Storage):
    """Aliyun OSS via its S3-compatible endpoint (virtual-host style)."""


class MinioStorage(S3Storage):
    """MinIO via the S3 API (path-style addressing)."""

    def __init__(self, client: S3Client, *, bucket: str) -> None:
        super().__init__(client, bucket=bucket, path_style=True)
