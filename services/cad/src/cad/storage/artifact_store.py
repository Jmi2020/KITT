"""Artifact storage backed by MinIO or local filesystem."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx
from minio import Minio

from common.config import settings
from common.logging import get_logger

LOGGER = get_logger(__name__)


class ArtifactStore:
    def __init__(self, bucket: Optional[str] = None) -> None:
        self._bucket = bucket or settings.minio_bucket
        self._minio: Optional[Minio] = None
        self._local_root: Optional[Path] = None
        if settings.minio_access_key and settings.minio_secret_key:
            endpoint = settings.minio_endpoint.replace("http://", "").replace(
                "https://", ""
            )
            secure = settings.minio_endpoint.startswith("https")
            self._minio = Minio(
                endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=secure,
            )
            if not self._minio.bucket_exists(self._bucket):
                self._minio.make_bucket(self._bucket)
        else:
            self._local_root = Path("artifacts")
            self._local_root.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, content: bytes, suffix: str) -> str:
        object_name = f"{uuid4().hex}{suffix}"
        if self._minio:
            from io import BytesIO

            data_stream = BytesIO(content)
            self._minio.put_object(
                self._bucket,
                object_name,
                data=data_stream,
                length=len(content),
                content_type="application/octet-stream",
            )
            LOGGER.info(
                "Stored artifact in MinIO", bucket=self._bucket, object_name=object_name
            )
            return f"minio://{self._bucket}/{object_name}"
        assert self._local_root is not None
        path = self._local_root / object_name
        path.write_bytes(content)
        LOGGER.info("Stored artifact locally", path=str(path))
        return str(path)

    async def save_from_url(self, url: str, suffix: str) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url)
            response.raise_for_status()
            return self.save_bytes(response.content, suffix)

    def save_file(self, path: Path, suffix: str) -> str:
        return self.save_bytes(path.read_bytes(), suffix)
