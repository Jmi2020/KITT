import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/research/src"))

class _DummyDDGS:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def text(self, **kwargs):
        return []

sys.modules.setdefault("duckduckgo_search", SimpleNamespace(DDGS=_DummyDDGS))
sys.modules.setdefault("simhash", SimpleNamespace(Simhash=object))
sys.modules.setdefault("markdownify", SimpleNamespace(markdownify=lambda value, **_: value))

from research.web_tool import WebTool  # type: ignore


class DummyResponse:
    def __init__(self, text: str = "<html><head><title>Example</title></head><body><p>Hello</p></body></html>"):
        self.text = text
        self.content = text.encode()
        self.status_code = 200
        self.headers = {"content-type": "text/html"}
        self.url = "http://example.com"

    def raise_for_status(self) -> None:  # noqa: D401
        return None


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):  # noqa: D401
        self._response = kwargs.pop("response", DummyResponse())

    async def __aenter__(self):  # noqa: D401
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: D401
        return False

    async def get(self, *args, **kwargs):  # noqa: D401
        return self._response


@pytest.mark.asyncio
async def test_web_tool_falls_back_to_beautifulsoup(monkeypatch):
    tool = WebTool(enable_jina=False)

    dummy_client = DummyAsyncClient()
    monkeypatch.setattr("research.web_tool.httpx.AsyncClient", lambda *a, **kw: dummy_client)

    result = await tool.fetch("http://example.com")

    assert result["success"] is True
    assert "Hello" in result["content"]
    assert result["metadata"]["provider"] == "beautifulsoup"


@pytest.mark.asyncio
async def test_web_tool_prefers_jina(monkeypatch):
    async def fake_jina(self, url):  # noqa: D401
        return {
            "success": True,
            "url": url,
            "final_url": url,
            "title": "Jina",
            "description": "",
            "author": "",
            "content": "Jina content",
            "metadata": {"provider": "jina_reader"},
        }

    tool = WebTool(enable_jina=True)
    tool._jina_enabled = True
    tool._fetch_via_jina = fake_jina.__get__(tool, WebTool)

    result = await tool.fetch("http://example.com")

    assert result["success"] is True
    assert result["content"] == "Jina content"
    assert result["metadata"]["provider"] == "jina_reader"
