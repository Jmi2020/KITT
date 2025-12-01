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
        self._base_url = raw_base.rstrip("/")
        if self._base_url.endswith("/v2/openapi"):
            self._api_prefix = self._base_url
            self._public_prefix = self._base_url
        else:
            self._api_prefix = f"{self._base_url}/v2/openapi"
            self._public_prefix = self._base_url

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
    ) -> Dict[str, str]:
        """Upload a reference image and return identifiers for generation."""

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
            base_url=self._public_prefix,
            bearer_token=self._api_key,
            timeout=60.0,
        ) as client:
            response = await client.post("/upload", files=files)
            response.raise_for_status()
            payload = response.json()

        body = payload.get("data") or payload
        token = body.get("file_token") or body.get("image_token") or body.get("token")
        if not token:
            raise RuntimeError(f"Tripo upload response missing token: {payload}")
        file_type = body.get("file_type") or (filename.split(".")[-1].lower() if "." in filename else "png")
        image_url = body.get("image_url") or body.get("url")
        LOGGER.info("Tripo reference uploaded", image_token=token)
        return {"file_token": token, "file_type": file_type, "image_url": image_url}

    async def start_image_task(
        self,
        *,
        file_token: str,
        file_type: Optional[str] = None,
        version: Optional[str] = None,
        texture_quality: Optional[str] = None,
        texture_alignment: Optional[str] = None,
        orientation: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an image-to-model task via the unified task endpoint."""

        if not file_token:
            raise ValueError("file_token is required for Tripo task")

        body: Dict[str, Any] = {
            "type": "image_to_model",
            "file": {
                "file_token": file_token,
                "type": (file_type or "png").lower(),
            },
        }
        if version:
            body["version"] = version
        if texture_quality:
            body["texture_quality"] = texture_quality
        if texture_alignment:
            body["texture_alignment"] = texture_alignment
        if orientation:
            body["orientation"] = orientation

        async with http_client(
            base_url=self._api_prefix,
            bearer_token=self._api_key,
            timeout=30.0,
        ) as client:
            response = await client.post("/task", json=body)
            response.raise_for_status()
            payload = self._unwrap(response.json())

        job = self._normalize_job(payload)
        LOGGER.info(
            "Tripo image task created",
            task_id=job.get("task_id"),
            status=job.get("status"),
        )
        return job

    async def start_text_task(
        self,
        *,
        prompt: str,
        version: Optional[str] = None,
        texture_quality: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a text-to-model task via the unified task endpoint."""

        if not prompt:
            raise ValueError("prompt is required for Tripo text-to-model task")

        body: Dict[str, Any] = {
            "type": "text_to_model",
            "prompt": prompt,
        }
        if version:
            body["model_version"] = version
        if texture_quality:
            body["texture_quality"] = texture_quality

        async with http_client(
            base_url=self._api_prefix,
            bearer_token=self._api_key,
            timeout=30.0,
        ) as client:
            response = await client.post("/task", json=body)
            response.raise_for_status()
            payload = self._unwrap(response.json())

        job = self._normalize_job(payload)
        LOGGER.info(
            "Tripo text task created",
            task_id=job.get("task_id"),
            status=job.get("status"),
        )
        return job

    async def get_task(self, task_id: str) -> Dict[str, Any]:
        """Fetch the latest status for a generation task."""

        async with http_client(
            base_url=self._api_prefix,
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
        fmt: str = "3MF",
        face_limit: Optional[int] = None,
        unit: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Request server-side conversion to a different mesh format."""

        body: Dict[str, Any] = {
            "original_task_id": original_task_id,
            "format": (fmt or "3MF").upper(),
        }
        if face_limit and face_limit > 0:
            body["face_limit"] = face_limit
        if unit:
            body["unit"] = unit

        async with http_client(
            base_url=self._api_prefix,
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
