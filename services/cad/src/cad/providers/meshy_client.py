"""Client for Meshy.ai cloud mesh generation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from common.config import settings
from common.http import http_client
from common.logging import get_logger

LOGGER = get_logger(__name__)


class MeshyClient:
    """Typed wrapper around the Meshy.ai 3D generation API.

    Meshy is the primary provider for organic 3D generation.
    Tripo serves as fallback if Meshy is unavailable or fails.

    API Reference: https://docs.meshy.ai
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None) -> None:
        self._api_key = api_key or settings.meshy_api_key
        if not self._api_key:
            raise RuntimeError("MESHY_API_KEY not configured")
        raw_base = base_url or settings.meshy_api_base or "https://api.meshy.ai"
        self._base_url = raw_base.rstrip("/")

    @staticmethod
    def _normalize_job(data: Dict[str, Any], fallback_task_id: Optional[str] = None) -> Dict[str, Any]:
        """Normalize Meshy response to match internal job format.

        Meshy uses uppercase status values: PENDING, IN_PROGRESS, SUCCEEDED, FAILED
        """
        # Task ID can be in 'result' field from creation or 'id' from status check
        task_id = data.get("result") or data.get("id") or fallback_task_id
        # Meshy uses uppercase status values
        raw_status = (data.get("status") or "PENDING").upper()
        status_map = {
            "PENDING": "pending",
            "IN_PROGRESS": "pending",
            "SUCCEEDED": "succeeded",
            "FAILED": "failed",
            "EXPIRED": "failed",
        }
        status = status_map.get(raw_status, "pending")
        return {
            "task_id": task_id,
            "status": status,
            "progress": data.get("progress", 0),
            "result": data,
        }

    async def start_text_task(
        self,
        *,
        prompt: str,
        mode: str = "preview",
        preview_task_id: Optional[str] = None,
        enable_pbr: Optional[bool] = None,
        art_style: Optional[str] = None,
        negative_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a text-to-3D task.

        Args:
            prompt: Text description of the 3D model to generate
            mode: "preview" for initial generation, "refine" for HD refinement
            preview_task_id: Required for refine mode - ID of the preview task
            enable_pbr: Enable PBR textures (default from settings)
            art_style: Art style preset (e.g., "realistic", "cartoon")
            negative_prompt: Things to avoid in the generation

        Returns:
            Normalized job dict with task_id, status, result
        """
        if mode == "refine" and not preview_task_id:
            raise ValueError("preview_task_id required for refine mode")

        body: Dict[str, Any] = {
            "mode": mode,
            "enable_pbr": enable_pbr if enable_pbr is not None else settings.meshy_enable_pbr,
        }

        if mode == "preview":
            body["prompt"] = prompt
            if art_style:
                body["art_style"] = art_style
            if negative_prompt:
                body["negative_prompt"] = negative_prompt
        else:
            # Refine mode
            body["preview_task_id"] = preview_task_id

        async with http_client(
            base_url=self._base_url,
            bearer_token=self._api_key,
            timeout=30.0,
        ) as client:
            response = await client.post("/openapi/v2/text-to-3d", json=body)
            response.raise_for_status()
            payload = response.json()

        job = self._normalize_job(payload)
        LOGGER.info(
            "Meshy text task created",
            task_id=job.get("task_id"),
            mode=mode,
            status=job.get("status"),
        )
        return job

    async def start_image_task(
        self,
        *,
        image_url: str,
        enable_pbr: Optional[bool] = None,
        should_remesh: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Create an image-to-3D task.

        Args:
            image_url: Public URL or base64 data URI of the reference image
            enable_pbr: Enable PBR textures
            should_remesh: Apply remeshing for cleaner topology

        Returns:
            Normalized job dict with task_id, status, result
        """
        body: Dict[str, Any] = {
            "image_url": image_url,
            "enable_pbr": enable_pbr if enable_pbr is not None else settings.meshy_enable_pbr,
            "should_remesh": should_remesh if should_remesh is not None else settings.meshy_should_remesh,
        }

        async with http_client(
            base_url=self._base_url,
            bearer_token=self._api_key,
            timeout=30.0,
        ) as client:
            response = await client.post("/openapi/v1/image-to-3d", json=body)
            response.raise_for_status()
            payload = response.json()

        job = self._normalize_job(payload)
        LOGGER.info(
            "Meshy image task created",
            task_id=job.get("task_id"),
            status=job.get("status"),
        )
        return job

    async def start_multi_image_task(
        self,
        *,
        image_urls: List[str],
    ) -> Dict[str, Any]:
        """Create a multi-image-to-3D task (Meshy-5 model, 1-4 images).

        Args:
            image_urls: List of 1-4 image URLs from different angles

        Returns:
            Normalized job dict with task_id, status, result
        """
        if not image_urls or len(image_urls) > 4:
            raise ValueError("Provide 1-4 images for multi-image task")

        body: Dict[str, Any] = {
            "image_urls": image_urls,
        }

        async with http_client(
            base_url=self._base_url,
            bearer_token=self._api_key,
            timeout=30.0,
        ) as client:
            response = await client.post("/openapi/v1/multi-image-to-3d", json=body)
            response.raise_for_status()
            payload = response.json()

        job = self._normalize_job(payload)
        LOGGER.info(
            "Meshy multi-image task created",
            task_id=job.get("task_id"),
            image_count=len(image_urls),
            status=job.get("status"),
        )
        return job

    async def get_text_task(self, task_id: str) -> Dict[str, Any]:
        """Fetch status for a text-to-3D task.

        Args:
            task_id: The task ID returned from start_text_task

        Returns:
            Normalized job dict with current status and model_urls on success
        """
        async with http_client(
            base_url=self._base_url,
            bearer_token=self._api_key,
            timeout=30.0,
        ) as client:
            response = await client.get(f"/openapi/v2/text-to-3d/{task_id}")
            response.raise_for_status()
            payload = response.json()

        return self._normalize_job(payload, fallback_task_id=task_id)

    async def get_image_task(self, task_id: str) -> Dict[str, Any]:
        """Fetch status for an image-to-3D task.

        Args:
            task_id: The task ID returned from start_image_task

        Returns:
            Normalized job dict with current status and model_urls on success
        """
        async with http_client(
            base_url=self._base_url,
            bearer_token=self._api_key,
            timeout=30.0,
        ) as client:
            response = await client.get(f"/openapi/v1/image-to-3d/{task_id}")
            response.raise_for_status()
            payload = response.json()

        return self._normalize_job(payload, fallback_task_id=task_id)

    async def get_multi_image_task(self, task_id: str) -> Dict[str, Any]:
        """Fetch status for a multi-image-to-3D task.

        Args:
            task_id: The task ID returned from start_multi_image_task

        Returns:
            Normalized job dict with current status and model_urls on success
        """
        async with http_client(
            base_url=self._base_url,
            bearer_token=self._api_key,
            timeout=30.0,
        ) as client:
            response = await client.get(f"/openapi/v1/multi-image-to-3d/{task_id}")
            response.raise_for_status()
            payload = response.json()

        return self._normalize_job(payload, fallback_task_id=task_id)


__all__ = ["MeshyClient"]
