import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MCP_SRC = ROOT / "services" / "mcp" / "src"
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from mcp.servers.vision_server import ReferenceStore, VisionMCPServer  # noqa: E402


@pytest.mark.asyncio
async def test_reference_store_local(tmp_path: Path):
    store = ReferenceStore(local_root=tmp_path)
    meta = await store.save("session", b"hello", "image/png")
    saved = Path(meta["storage_uri"])
    assert saved.exists()
    assert saved.read_bytes() == b"hello"


@pytest.mark.asyncio
async def test_image_filter_scores_by_keyword():
    server = VisionMCPServer()
    args = {
        "query": "gandalf rubber duck",
        "images": [
            {"id": "1", "title": "Gandalf Rubber Duck", "description": "Wizard duck"},
            {"id": "2", "title": "Random cat", "description": "orange cat"},
        ],
        "min_score": 0.1,
    }
    result = await server._tool_image_filter(args)
    scores = [item["score"] for item in result.data["results"]]
    assert scores[0] >= scores[-1]
    assert result.data["results"][0]["id"] == "1"
