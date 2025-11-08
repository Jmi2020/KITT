"""Unit tests for web search cascade (SearXNG -> Brave -> DuckDuckGo)."""

from __future__ import annotations

import pytest

import sys
from pathlib import Path
from types import SimpleNamespace

class _DummyDDGS:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def text(self, **kwargs):
        return []

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/research/src"))

sys.modules.setdefault("duckduckgo_search", SimpleNamespace(DDGS=_DummyDDGS))
sys.modules.setdefault("simhash", SimpleNamespace(Simhash=object))
sys.modules.setdefault("markdownify", SimpleNamespace(markdownify=lambda value, **_: value))

from research.search_tool import SearchTool  # type: ignore


@pytest.mark.asyncio
async def test_search_prefers_searx(monkeypatch):
    async def fake_searx(self, query, max_results):
        return {
            "success": True,
            "query": query,
            "results": [{"title": "A", "url": "https://a.test", "description": "", "source": "a.test"}],
            "total_results": 1,
            "metadata": {"provider": "searxng"},
        }

    async def fake_brave(self, query, max_results):
        return None

    async def fake_duckduckgo(self, query, max_results):
        return {"success": True, "metadata": {"provider": "duckduckgo"}, "results": []}

    monkeypatch.setattr(SearchTool, "_search_searx", fake_searx, raising=False)
    monkeypatch.setattr(SearchTool, "_search_brave", fake_brave, raising=False)
    monkeypatch.setattr(SearchTool, "_search_duckduckgo", fake_duckduckgo, raising=False)

    tool = SearchTool()
    result = await tool.search("test query")
    assert result["metadata"]["provider"] == "searxng"


@pytest.mark.asyncio
async def test_search_uses_brave_when_searx_unavailable(monkeypatch):
    async def fake_searx(self, query, max_results):
        return None

    async def fake_brave(self, query, max_results):
        return {
            "success": True,
            "query": query,
            "results": [{"title": "B", "url": "https://b.test", "description": "", "source": "b.test"}],
            "total_results": 1,
            "metadata": {"provider": "brave"},
        }

    async def fake_duckduckgo(self, query, max_results):
        return {"success": True, "metadata": {"provider": "duckduckgo"}, "results": []}

    monkeypatch.setattr(SearchTool, "_search_searx", fake_searx, raising=False)
    monkeypatch.setattr(SearchTool, "_search_brave", fake_brave, raising=False)
    monkeypatch.setattr(SearchTool, "_search_duckduckgo", fake_duckduckgo, raising=False)

    tool = SearchTool()
    result = await tool.search("test query")
    assert result["metadata"]["provider"] == "brave"


@pytest.mark.asyncio
async def test_search_falls_back_to_duckduckgo(monkeypatch):
    async def fake_searx(self, query, max_results):
        return None

    async def fake_brave(self, query, max_results):
        return None

    async def fake_duckduckgo(self, query, max_results):
        return {
            "success": True,
            "query": query,
            "results": [{"title": "D", "url": "https://d.test", "description": "", "source": "d.test"}],
            "total_results": 1,
            "metadata": {"provider": "duckduckgo"},
        }

    monkeypatch.setattr(SearchTool, "_search_searx", fake_searx, raising=False)
    monkeypatch.setattr(SearchTool, "_search_brave", fake_brave, raising=False)
    monkeypatch.setattr(SearchTool, "_search_duckduckgo", fake_duckduckgo, raising=False)

    tool = SearchTool()
    result = await tool.search("test query")
    assert result["metadata"]["provider"] == "duckduckgo"


def test_normalize_local_url_remaps_inside_container():
    original = "http://localhost:8888/search"
    remapped = SearchTool._normalize_local_url(
        original,
        inside_container=True,
        gateway_host="host.docker.internal",
    )
    assert remapped == "http://host.docker.internal:8888/search"


def test_normalize_local_url_noop_outside_container():
    original = "http://localhost:8888/search"
    remapped = SearchTool._normalize_local_url(
        original,
        inside_container=False,
        gateway_host="host.docker.internal",
    )
    assert remapped == original
