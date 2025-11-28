"""Client for Zoo CAD API.

Uses the text-to-cad async API:
POST /ai/text-to-cad/{output_format}
GET /async/operations/{id} for polling

Zoo returns model data as base64-encoded strings in the outputs dict:
  "outputs": {
    "source.gltf": "<base64_data>",
    "source.step": "<base64_data>"
  }
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any, Dict, Optional

from common.config import settings
from common.http import http_client
from common.logging import get_logger

LOGGER = get_logger(__name__)


class ZooClient:
    """Client for Zoo text-to-cad API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        output_format: str = "step",
        poll_interval: float = 3.0,
        poll_timeout: float = 180.0,
    ) -> None:
        self._api_key = api_key or settings.zoo_api_key
        if not self._api_key:
            raise RuntimeError("ZOO_API_KEY not configured")
        self._base_url = (base_url or settings.zoo_api_base).rstrip("/")
        self._output_format = output_format
        self._poll_interval = max(1.0, poll_interval)
        self._poll_timeout = max(poll_interval, poll_timeout)

    async def create_model(
        self, name: str, prompt: str, parameters: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Create a CAD model from text prompt using Zoo text-to-cad API.

        Args:
            name: Model name (used for metadata)
            prompt: Natural language description of the model
            parameters: Optional additional parameters

        Returns:
            Dict with 'id' for polling and initial status
        """
        # Build the request payload
        payload = {"prompt": prompt}

        async with http_client(
            base_url=self._base_url, bearer_token=self._api_key
        ) as client:
            # Use the new text-to-cad endpoint
            response = await client.post(
                f"/ai/text-to-cad/{self._output_format}",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

            # The API returns an async operation with an 'id' field
            op_id = result.get("id")
            status = result.get("status", "").lower()

            LOGGER.info(
                "Zoo text-to-cad job created",
                operation_id=op_id,
                status=status,
            )

            # Return with polling URL for compatibility with cycler
            return {
                "id": op_id,
                "status": status,
                "polling_url": f"/async/operations/{op_id}" if op_id else None,
                "raw_response": result,
            }

    def _process_outputs(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Process Zoo outputs dict to extract geometry data.

        Args:
            outputs: Zoo outputs dict with format keys like "source.gltf"

        Returns:
            Dict with geometry data/url and format
        """
        geometry_data = None
        geometry_url = None
        geometry_format = None

        # Priority order: GLTF (for preview), then STEP (for CAD)
        format_priority = ["gltf", "glb", "step", "obj"]

        for target_fmt in format_priority:
            for key, data in outputs.items():
                # Extract format from key like "source.gltf" -> "gltf"
                key_lower = key.lower()
                if not key_lower.endswith(f".{target_fmt}"):
                    continue

                # Check if it's a URL (legacy behavior)
                if isinstance(data, str) and data.startswith("http"):
                    geometry_url = data
                    geometry_format = target_fmt
                    break
                # Check if it's a dict with URL
                elif isinstance(data, dict) and data.get("url"):
                    geometry_url = data["url"]
                    geometry_format = target_fmt
                    break
                # Assume base64-encoded data (current Zoo API)
                elif isinstance(data, str) and len(data) > 100:
                    try:
                        geometry_data = base64.b64decode(data)
                        geometry_format = target_fmt
                        LOGGER.info(
                            "Decoded Zoo output",
                            format=target_fmt,
                            size_bytes=len(geometry_data),
                        )
                        break
                    except Exception as e:
                        LOGGER.warning(
                            "Failed to decode Zoo output",
                            key=key,
                            error=str(e),
                        )
            if geometry_data or geometry_url:
                break

        return {
            "url": geometry_url,
            "data": geometry_data,
            "format": geometry_format or self._output_format,
        }

    async def poll_status(self, status_url: str) -> Dict[str, Any]:
        """Poll for async operation status.

        Args:
            status_url: URL path to poll (e.g., /async/operations/{id})

        Returns:
            Dict with status and results when complete.
            For completed jobs, returns geometry with either:
            - 'url': HTTP URL to download (legacy)
            - 'data': Raw bytes of the model (current Zoo API)
        """
        async with http_client(
            base_url=self._base_url, bearer_token=self._api_key
        ) as client:
            response = await client.get(status_url)
            response.raise_for_status()
            result = response.json()

            status = result.get("status", "").lower()

            # Transform to format expected by cycler
            if status == "completed":
                outputs = result.get("outputs", {})
                geometry = self._process_outputs(outputs)

                return {
                    "status": status,
                    "geometry": geometry,
                    "credits_used": result.get("credits_used", 0),
                    "raw_response": result,
                }

            return {
                "status": status,
                "raw_response": result,
            }

    async def create_and_poll(
        self, name: str, prompt: str, parameters: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Create a model and poll until completion.

        Convenience method that combines create_model and poll_status.
        Handles both cached responses (outputs in initial response) and
        async jobs (requires polling).
        """
        job = await self.create_model(name, prompt, parameters)
        status = job.get("status", "").lower()
        raw_response = job.get("raw_response", {})

        # Check if outputs are already in the initial response (cached result)
        outputs = raw_response.get("outputs", {})
        if status == "completed" and outputs:
            LOGGER.info("Zoo returned cached result with outputs")
            geometry = self._process_outputs(outputs)
            return {
                "status": status,
                "geometry": geometry,
                "credits_used": raw_response.get("credits_used", 0),
                "raw_response": raw_response,
            }

        # Need to poll for async operation
        polling_url = job.get("polling_url")
        if not polling_url:
            raise RuntimeError("Zoo response missing operation ID for polling")

        start = time.perf_counter()
        while True:
            if time.perf_counter() - start >= self._poll_timeout:
                raise TimeoutError(f"Zoo job timed out after {self._poll_timeout}s")

            await asyncio.sleep(self._poll_interval)
            result = await self.poll_status(polling_url)
            status = result.get("status", "").lower()

            if status == "completed":
                return result
            if status in {"failed", "error"}:
                raise RuntimeError(
                    f"Zoo job failed: {result.get('raw_response', {}).get('error', 'Unknown error')}"
                )
