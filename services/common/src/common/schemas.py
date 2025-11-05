"""Pydantic schema helpers shared by services."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class KittyModel(BaseModel):
    """Base model enabling ORM mode and common helper methods."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    def dict_for_mqtt(self, **kwargs: Any) -> dict[str, Any]:
        payload = self.model_dump(mode="json", **kwargs)
        payload["generated_at"] = datetime.utcnow().isoformat()
        return payload


class Pagination(BaseModel):
    total: int
    limit: int = 50
    offset: int = 0


__all__ = ["KittyModel", "Pagination"]
