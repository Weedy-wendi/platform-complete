"""Storage factory.

boto3 is imported lazily so local development and the default test suite do not
need the vendor SDK installed.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.modules.assets.local import LocalStorage
from app.modules.assets.s3 import MinioStorage, OssStorage
from app.modules.assets.storage import Storage


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "local":
        return LocalStorage(settings.local_storage_root)

    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise ServiceUnavailableError("boto3 is required for S3 storage; install the 'storage' extra") from exc

    client = boto3.client(
        "s3",
        endpoint_url=settings.oss_endpoint,
        aws_access_key_id=settings.oss_access_key.get_secret_value(),
        aws_secret_access_key=settings.oss_secret_key.get_secret_value(),
        region_name=settings.oss_region,
        use_ssl=settings.oss_secure,
        config=Config(s3={"addressing_style": "path" if settings.oss_path_style else "virtual"}),
    )
    if settings.oss_path_style:
        return MinioStorage(client, bucket=settings.oss_bucket)
    return OssStorage(client, bucket=settings.oss_bucket)
