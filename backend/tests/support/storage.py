"""In-memory storage doubles shared by contract and service tests."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from app.core.errors import NotFoundError
from app.modules.assets.storage import validate_ttl


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.put_error: Exception | None = None
        self.tamper_reads = False

    def put(self, key: str, data: bytes, *, content_type: str) -> str:
        if self.put_error is not None:
            raise self.put_error
        import hashlib

        self.objects[key] = (bytes(data), content_type)
        return hashlib.sha256(data).hexdigest()

    def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise NotFoundError("Object not found", key=key)
        data = self.objects[key][0]
        return data[:-1] + b"X" if self.tamper_reads and data else data

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def presign_get(self, key: str, *, ttl_seconds: int = 900) -> str:
        validate_ttl(ttl_seconds)
        return f"fake://{key}?ttl={ttl_seconds}"

    def presign_put(self, key: str, *, ttl_seconds: int = 900) -> str:
        validate_ttl(ttl_seconds)
        return f"fake-put://{key}?ttl={ttl_seconds}"

    def healthcheck(self) -> bool:
        return self.put_error is None


class FakeClientError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"client error {status}")
        self.response = {"ResponseMetadata": {"HTTPStatusCode": status}}


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.fail_status: int | None = None

    def _maybe_fail(self) -> None:
        if self.fail_status is not None:
            raise FakeClientError(self.fail_status)

    def put_object(self, **kwargs: Any) -> None:
        self._maybe_fail()
        self.objects[kwargs["Key"]] = (bytes(kwargs["Body"]), kwargs["ContentType"])

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self._maybe_fail()
        key = kwargs["Key"]
        if key not in self.objects:
            raise FakeClientError(404)
        return {"Body": BytesIO(self.objects[key][0])}

    def delete_object(self, **kwargs: Any) -> None:
        self._maybe_fail()
        self.objects.pop(kwargs["Key"], None)

    def head_bucket(self, **kwargs: Any) -> None:
        self._maybe_fail()

    def generate_presigned_url(self, operation: str, *, Params: dict[str, Any], ExpiresIn: int) -> str:
        self._maybe_fail()
        return f"https://s3.test/{Params['Bucket']}/{Params['Key']}?op={operation}&expires={ExpiresIn}"
