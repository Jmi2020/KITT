"""Semantic cache backed by Redis Streams."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import redis

from .config import settings


@dataclass(slots=True)
class CacheRecord:
    key: str
    prompt: str
    response: str
    confidence: float


class SemanticCache:
    """Persist prompts/responses in Redis Streams for reuse and observability."""

    STREAM_KEY = "kitty:semantic-cache"

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._client = redis.from_url(redis_url or settings.redis_url, decode_responses=True)

    def store(self, record: CacheRecord) -> str:
        payload = {
            "prompt": record.prompt,
            "response": record.response,
            "confidence": record.confidence,
        }
        return self._client.xadd(self.STREAM_KEY, {record.key: json.dumps(payload)})

    def fetch(self, key: str) -> Optional[CacheRecord]:
        entries = self._client.xrevrange(self.STREAM_KEY, count=50)
        for _, fields in entries:
            if key in fields:
                data = json.loads(fields[key])
                return CacheRecord(
                    key=key,
                    prompt=data["prompt"],
                    response=data["response"],
                    confidence=data["confidence"],
                )
        return None

    def hit_ratio(self) -> float:
        info = self._client.xinfo_stream(self.STREAM_KEY)
        length = info.get("length", 0)
        return float(length)


__all__ = ["SemanticCache", "CacheRecord"]
