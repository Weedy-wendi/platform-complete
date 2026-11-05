"""Public assets surface."""

from app.modules.assets.factory import build_storage
from app.modules.assets.local import LocalStorage
from app.modules.assets.s3 import MinioStorage, OssStorage, S3Storage
from app.modules.assets.service import ArtifactRef, ArtifactService
from app.modules.assets.storage import (
    MAX_PRESIGN_TTL_SECONDS,
    Storage,
    build_key,
    validate_key,
    validate_ttl,
)

__all__ = [
    "MAX_PRESIGN_TTL_SECONDS",
    "ArtifactRef",
    "ArtifactService",
    "LocalStorage",
    "MinioStorage",
    "OssStorage",
    "S3Storage",
    "Storage",
    "build_key",
    "build_storage",
    "validate_key",
    "validate_ttl",
]
