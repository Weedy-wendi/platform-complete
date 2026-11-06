"""Artifact use cases: object storage plus tenant-scoped metadata."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.clock import utcnow_naive
from app.core.context import TenantContext
from app.core.errors import InvalidArgumentError, NotFoundError, UpstreamUnavailableError
from app.core.ids import new_ulid
from app.core.repository import TenantScopedRepository
from app.modules.assets.models import Artifact
from app.modules.assets.storage import (
    MAX_PRESIGN_TTL_SECONDS,
    Storage,
    sha256_hex,
    validate_key,
    validate_ttl,
)


@dataclass(frozen=True)
class ArtifactRef:
    tenant_id: str
    artifact_id: str
    s3_key: str
    size_bytes: int
    sha256: str
    mime_type: str


class ArtifactService:
    def __init__(
        self,
        storage: Storage,
        session_factory: sessionmaker[Session],
        *,
        presign_ttl_seconds: int = MAX_PRESIGN_TTL_SECONDS,
    ) -> None:
        self._storage = storage
        self._session_factory = session_factory
        self._presign_ttl = validate_ttl(presign_ttl_seconds)

    def create(
        self,
        ctx: TenantContext,
        *,
        key: str,
        data: bytes,
        mime_type: str,
    ) -> ArtifactRef:
        self._validate_tenant_key(ctx, key)
        if not mime_type:
            raise InvalidArgumentError("mime_type is required")
        with self._session_factory() as session:
            existing = session.scalar(
                TenantScopedRepository(session, ctx.tenant_id).scoped(Artifact).where(Artifact.s3_key == key)
            )
            if existing is not None:
                raise InvalidArgumentError("artifact already exists", key=key)
        digest = sha256_hex(data)
        stored_digest = self._storage.put(key, data, content_type=mime_type)
        if stored_digest != digest:
            raise UpstreamUnavailableError("object store checksum mismatch")

        artifact = Artifact(
            id=new_ulid(),
            tenant_id=ctx.tenant_id,
            asset_type=_segment(key, 2),
            asset_id=_segment(key, 3),
            version=_segment(key, 4),
            filename=_segment(key, 5),
            s3_key=key,
            size_bytes=len(data),
            sha256=digest,
            mime_type=mime_type,
            created_at=utcnow_naive(),
            created_by=ctx.subject_id,
        )
        try:
            with self._session_factory() as session:
                session.add(artifact)
                session.commit()
        except IntegrityError as exc:
            # Never delete the object here: a concurrent writer may own it and
            # the pre-check already covers the normal duplicate path.
            raise InvalidArgumentError("artifact already exists", key=key) from exc
        except Exception:
            self._storage.delete(key)
            raise
        return _ref(artifact)

    def get(self, ctx: TenantContext, artifact_id: str) -> ArtifactRef:
        with self._session_factory() as session:
            artifact = TenantScopedRepository(session, ctx.tenant_id).get(Artifact, artifact_id)
            if artifact is None:
                raise NotFoundError("Artifact not found")
            return _ref(artifact)

    def get_bytes(self, ctx: TenantContext, artifact_id: str) -> bytes:
        ref = self.get(ctx, artifact_id)
        data = self._storage.get(ref.s3_key)
        if sha256_hex(data) != ref.sha256:
            raise InvalidArgumentError("artifact checksum mismatch", artifact_id=artifact_id)
        return data

    def presign_get(
        self,
        ctx: TenantContext,
        artifact_id: str,
        *,
        ttl_seconds: int | None = None,
    ) -> str:
        ref = self.get(ctx, artifact_id)
        return self._storage.presign_get(
            ref.s3_key,
            ttl_seconds=self._presign_ttl if ttl_seconds is None else validate_ttl(ttl_seconds),
        )

    def delete(self, ctx: TenantContext, artifact_id: str) -> None:
        with self._session_factory() as session:
            repository = TenantScopedRepository(session, ctx.tenant_id)
            artifact = repository.get(Artifact, artifact_id)
            if artifact is None:
                raise NotFoundError("Artifact not found")
            self._storage.delete(artifact.s3_key)
            session.delete(artifact)
            session.commit()

    def _validate_tenant_key(self, ctx: TenantContext, key: str) -> None:
        validate_key(key)
        prefix = f"tenant/{ctx.tenant_id}/"
        if not key.startswith(prefix):
            raise InvalidArgumentError("artifact key is outside the tenant prefix", key=key)


def _segment(key: str, index: int) -> str:
    parts = key.split("/")
    if len(parts) <= index:
        raise InvalidArgumentError("artifact key does not match the required layout", key=key)
    return parts[index]


def _ref(artifact: Artifact) -> ArtifactRef:
    return ArtifactRef(
        tenant_id=artifact.tenant_id,
        artifact_id=artifact.id,
        s3_key=artifact.s3_key,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
        mime_type=artifact.mime_type,
    )
