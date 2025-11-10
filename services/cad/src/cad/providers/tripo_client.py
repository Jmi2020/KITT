"""Client for Tripo cloud mesh generation."""

from __future__ import annotations

from typing import Any, Dict, Optional

from common.config import settings
from common.http import http_client
from common.logging import get_logger

LOGGER = get_logger(__name__)


class TripoClient:
    """Typed wrapper around the Tripo 3D generation API."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None) -> None:
        self._api_key = api_key or settings.tripo_api_key
        if not self._api_key:
            raise RuntimeError("TRIPO_API_KEY not configured")
        raw_base = base_url or settings.tripo_api_base or "https://api.tripo3d.ai/v2/openapi"
        self._base_url = self._normalize_base(raw_base)

    @staticmethod
    def _normalize_base(value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.endswith("/v2/openapi"):
            normalized = f"{normalized}/v2/openapi"
        return normalized

    @staticmethod
    def _unwrap(payload: Dict[str, Any]) -> Dict[str, Any]:
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload

    @staticmethod
    def _normalize_job(data: Dict[str, Any], fallback_task_id: Optional[str] = None) -> Dict[str, Any]:
        task_id = (
            data.get("task_id")
            or data.get("taskId")
            or data.get("id")
            or fallback_task_id
        )
        status = (data.get("status") or data.get("state") or "").lower() or "pending"
        return {
            "task_id": task_id,
            "status": status,
            "result": data,
        }

    async def upload_image(
        self,
        *,
        data: bytes,
        filename: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload a reference image and return the hosted URL."""

        if not data:
            raise ValueError("Image payload is empty")
        files = {
            "file": (
                filename or "reference.jpg",
                data,
                content_type or "application/octet-stream",
            )
        }
        async with http_client(
            base_url=self._base_url,
            bearer_token=self._api_key,
            timeout=60.0,
        ) as client:
            response = await client.post("/upload", files=files)
            response.raise_for_status()
            payload = self._unwrap(response.json())

        image_url = (
            payload.get("url")
            or payload.get("image_url")
            or payload.get("imageUrl")
            or payload.get("upload_url")
        )
        if not image_url:
            raise RuntimeError("Tripo upload response missing image URL")
        LOGGER.info("Tripo reference uploaded", image_url=image_url)
        return image_url

    async def start_image_job(
        self,
        *,
        image_url: str,
        model_version: Optional[str] = None,
        texture_quality: Optional[str] = None,
        texture_alignment: Optional[str] = None,
        orientation: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Kick off an image-to-3D generation task."""

        body: Dict[str, Any] = {"image_url": image_url}
        if model_version:
            body["model_version"] = model_version
        if texture_quality:
            body["texture_quality"] = texture_quality
        if texture_alignment:
            body["texture_alignment"] = texture_alignment
        if orientation:
            body["orientation"] = orientation

        async with http_client(
            base_url=self._base_url,
            bearer_token=self._api_key,
            timeout=30.0,
        ) as client:
            response = await client.post("/image-to-3d", json=body)
            response.raise_for_status()
            payload = self._unwrap(response.json())

        job = self._normalize_job(payload)
        LOGGER.info(
            "Tripo image job created",
            task_id=job.get("task_id"),
            status=job.get("status"),
        )
        return job

    async def get_task(self, task_id: str) -> Dict[str, Any]:
        """Fetch the latest status for a generation task."""

        async with http_client(
            base_url=self._base_url,
            bearer_token=self._api_key,
            timeout=30.0,
        ) as client:
            response = await client.get(f"/task/{task_id}")
            response.raise_for_status()
            payload = self._unwrap(response.json())

        return self._normalize_job(payload, fallback_task_id=task_id)

    async def start_convert_task(
        self,
        *,
        original_task_id: str,
        fmt: str = "STL",
        stl_format: Optional[str] = None,
        face_limit: Optional[int] = None,
        unit: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Request server-side conversion to a different mesh format."""

        body: Dict[str, Any] = {
            "original_task_id": original_task_id,
            "format": (fmt or "STL").upper(),
        }
        if stl_format:
            body["stl_format"] = stl_format
        if face_limit and face_limit > 0:
            body["face_limit"] = face_limit
        if unit:
            body["unit"] = unit

        async with http_client(
            base_url=self._base_url,
            bearer_token=self._api_key,
            timeout=30.0,
        ) as client:
            response = await client.post("/convert", json=body)
            response.raise_for_status()
            payload = self._unwrap(response.json())

        job = self._normalize_job(payload)
        LOGGER.info(
            "Tripo convert task created",
            original_task_id=original_task_id,
            convert_task_id=job.get("task_id"),
        )
        return job


__all__ = ["TripoClient"]
