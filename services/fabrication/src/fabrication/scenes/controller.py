"""Trigger lighting and power scenes via Home Assistant."""

from __future__ import annotations

from typing import Any, Dict

from common.credentials import HomeAssistantCredentials
from common.http import http_client


class SceneController:
    def __init__(self, credentials: HomeAssistantCredentials) -> None:
        self._credentials = credentials

    async def activate_scene(
        self, scene_entity: str, extra: Dict[str, Any] | None = None
    ) -> None:
        payload = {"entity_id": scene_entity}
        if extra:
            payload.update(extra)
        async with http_client(
            base_url=self._credentials.base_url,
            bearer_token=self._credentials.token.get_secret_value(),
        ) as client:
            response = await client.post("/api/services/scene/turn_on", json=payload)
            response.raise_for_status()
