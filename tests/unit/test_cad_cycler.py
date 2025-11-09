import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CAD_SRC = ROOT / "services" / "cad" / "src"
if str(CAD_SRC) not in sys.path:
    sys.path.insert(0, str(CAD_SRC))

from cad.cycler import CADCycler  # type: ignore  # noqa: E402


class DummyZoo:
    async def create_model(self, name: str, prompt: str, parameters):  # noqa: D401
        return {}

    async def poll_status(self, url: str):  # noqa: D401
        return {}


class DummyTripo:
    def __init__(self):
        self.calls = []

    async def image_to_mesh(self, image_url: str):  # noqa: D401
        self.calls.append(image_url)
        return {
            "data": {
                "model_url": f"http://example.com/{len(self.calls)}.glb",
                "thumbnail": "thumb",
            }
        }


class DummyStore:
    async def save_from_url(self, url: str, suffix: str):  # noqa: D401
        return f"stored:{url}"


@pytest.mark.asyncio
async def test_cad_cycler_uses_image_refs_limit():
    tripo = DummyTripo()
    cycler = CADCycler(
        zoo_client=DummyZoo(),
        tripo_client=tripo,
        artifact_store=DummyStore(),
        local_runner=None,
        freecad_runner=None,
        max_tripo_images=2,
    )

    artifacts = await cycler.run("duck", references={}, image_refs=["url1", "url2", "url3"])

    assert len(artifacts) == 2
    assert tripo.calls == ["url1", "url2"]
