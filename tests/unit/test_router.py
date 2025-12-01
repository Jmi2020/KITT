# ruff: noqa: E402
import asyncio
import hashlib
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/common/src"))
sys.path.append(str(ROOT / "services/brain/src"))

pytest.importorskip("pydantic_settings")
pytest.importorskip("pydantic")
pytest.importorskip("httpx")

from common.cache import CacheRecord  # type: ignore[import]
from common.db.models import RoutingTier  # type: ignore[import]
from brain.routing.router import BrainRouter, RoutingRequest, RoutingResult  # type: ignore[import]


class FakeCache:
    def __init__(self) -> None:
        self.store_dict = {}

    def store(self, record: CacheRecord) -> str:  # type: ignore[override]
        self.store_dict[record.key] = record
        return record.key

    def fetch(self, key: str):  # type: ignore[override]
        record = self.store_dict.get(key)
        return record

    def hit_ratio(self) -> float:
        return float(len(self.store_dict))


class StubLocal:
    def __init__(self, text: str, confidence: float = 0.9) -> None:
        self._text = text
        self._confidence = confidence

    async def generate(self, prompt: str, model: str, tools: Any = None) -> Dict[str, Any]:
        await asyncio.sleep(0)
        return {"response": f"{self._text}: {prompt}"}


class StubAudit:
    def __init__(self) -> None:
        self.records = []

    def record(self, **kwargs):  # type: ignore[override]
        self.records.append(kwargs)


@pytest.mark.asyncio
async def test_router_returns_local_result(monkeypatch):
    cache = FakeCache()
    audit = StubAudit()
    router = BrainRouter(
        llama_client=StubLocal("local"), audit_store=audit, cache=cache
    )

    request = RoutingRequest(conversation_id="c1", request_id="r1", prompt="hello")
    result = await router.route(request)

    assert isinstance(result, RoutingResult)
    assert result.tier == RoutingTier.local
    assert "local" in result.output
    assert audit.records


@pytest.mark.asyncio
async def test_router_uses_cache(monkeypatch):
    cache = FakeCache()
    audit = StubAudit()
    # Use the correct hash for "hello" to match the router's cache key generation
    cache_key = hashlib.sha256("hello".encode("utf-8")).hexdigest()
    cache.store(
        CacheRecord(
            key=cache_key,
            prompt="hello",
            response="cached response",
            confidence=0.9,
        )
    )
    router = BrainRouter(
        llama_client=StubLocal("local"), audit_store=audit, cache=cache
    )

    request = RoutingRequest(conversation_id="c2", request_id="r2", prompt="hello")
    result = await router.route(request)

    assert result.cached is True
    assert result.output == "cached response"
