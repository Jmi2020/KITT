import sys
from pathlib import Path
from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CAD_SRC = ROOT / "services" / "cad" / "src"
if str(CAD_SRC) not in sys.path:
    sys.path.insert(0, str(CAD_SRC))

from cad.cycler import CADCycler  # type: ignore  # noqa: E402
from cad.models import ImageReference  # type: ignore  # noqa: E402


class DummyZoo:
    def __init__(self):
        self.called = False

    async def create_model(self, name: str, prompt: str, parameters):  # noqa: D401
        self.called = True
        return {}

    async def poll_status(self, url: str):  # noqa: D401
        return {}


class DummyTripo:
    def __init__(self):
        self.uploads = []
        self.started = []
        self.converts = []
        self.upload_payloads = []

    async def upload_image(self, *, data: bytes, filename: str, content_type: str):  # noqa: D401
        self.uploads.append(filename)
        self.upload_payloads.append((data, filename, content_type))
        return {
            "file_token": f"token-{len(self.uploads)}",
            "file_type": "png",
            "image_url": f"http://uploads/{len(self.uploads)}.png",
        }

    async def start_image_task(self, **_: str):  # noqa: D401
        task_id = f"task-{len(self.started) + 1}"
        self.started.append(task_id)
        return {"task_id": task_id, "status": "processing", "result": {}}

    async def get_task(self, task_id: str):  # noqa: D401
        if str(task_id).startswith("convert"):
            return {
                "task_id": task_id,
                "status": "completed",
                "result": {
                    "model": {
                        "url": f"http://example.com/{task_id}.3mf",
                    }
                },
            }
        return {
            "task_id": task_id,
            "status": "completed",
            "result": {
                "model_mesh": {
                    "url": f"http://example.com/{task_id}.glb",
                    "format": "glb",
                },
                "thumbnail": f"http://example.com/{task_id}.jpg",
            },
        }

    async def start_convert_task(self, *, original_task_id: str, **_):  # noqa: D401
        convert_id = f"convert-{len(self.converts) + 1}"
        self.converts.append((original_task_id, convert_id))
        return {"task_id": convert_id, "status": "processing", "result": {}}


class DummyStore:
    async def save_from_url(self, url: str, suffix: str):  # noqa: D401
        return f"stored:{url}{suffix}"

    def save_bytes(self, content: bytes, suffix: str, subdir: str = None):  # noqa: D401
        return f"stored-bytes:{len(content)}{suffix}"


def _make_image_bytes(fmt: str = "PNG") -> bytes:
    if fmt.upper() == "GIF":
        image = Image.new("P", (4, 4), color=1)
    else:
        mode = "RGBA" if fmt.upper() in {"PNG", "WEBP"} else "RGB"
        color = (255, 0, 0, 255) if mode == "RGBA" else (255, 0, 0)
        image = Image.new(mode, (4, 4), color=color)
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_cad_cycler_uses_image_refs_limit(tmp_path: Path):
    tripo = DummyTripo()
    cycler = CADCycler(
        zoo_client=DummyZoo(),
        tripo_client=tripo,
        artifact_store=DummyStore(),
        local_runner=None,
        freecad_runner=None,
        max_tripo_images=2,
        storage_root=tmp_path,
        mesh_converter=lambda _data, _fmt: b"3mf-bytes",
        tripo_convert_enabled=False,
    )
    cycler._download_bytes = AsyncMock(return_value=b"mesh")  # type: ignore[attr-defined]

    refs = []
    for idx in range(3):
        path = tmp_path / f"img{idx}.png"
        path.write_bytes(_make_image_bytes("PNG"))
        refs.append(ImageReference(storage_uri=str(path)))

    artifacts = await cycler.run("duck", references={}, image_refs=refs)

    assert len(artifacts) == 2
    assert tripo.started == ["task-1", "task-2"]
    assert all(artifact.provider == "tripo" for artifact in artifacts)
    assert all(artifact.artifact_type == "3mf" for artifact in artifacts)


@pytest.mark.asyncio
async def test_cad_cycler_prefers_tripo_convert(tmp_path: Path):
    tripo = DummyTripo()
    cycler = CADCycler(
        zoo_client=DummyZoo(),
        tripo_client=tripo,
        artifact_store=DummyStore(),
        local_runner=None,
        freecad_runner=None,
        max_tripo_images=1,
        storage_root=tmp_path,
        mesh_converter=None,
        tripo_convert_enabled=True,
    )
    cycler._download_bytes = AsyncMock(return_value=b"3mf-data")  # type: ignore[attr-defined]

    path = tmp_path / "img.png"
    path.write_bytes(_make_image_bytes("PNG"))
    refs = [ImageReference(storage_uri=str(path))]

    artifacts = await cycler.run("duck", references={}, image_refs=refs)

    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "3mf"
    assert tripo.converts == [("task-1", "convert-1")]


@pytest.mark.asyncio
async def test_cad_cycler_mode_parametric_skips_tripo(tmp_path: Path):
    tripo = DummyTripo()
    cycler = CADCycler(
        zoo_client=DummyZoo(),
        tripo_client=tripo,
        artifact_store=DummyStore(),
        storage_root=tmp_path,
    )
    cycler._download_bytes = AsyncMock(return_value=b"mesh")  # type: ignore[attr-defined]

    path = tmp_path / "img.png"
    path.write_bytes(_make_image_bytes("PNG"))
    refs = [ImageReference(storage_uri=str(path))]

    await cycler.run("duck", references={}, image_refs=refs, mode="parametric")

    assert tripo.uploads == []


@pytest.mark.asyncio
async def test_cad_cycler_mode_organic_skips_zoo(tmp_path: Path):
    zoo = DummyZoo()
    tripo = DummyTripo()
    cycler = CADCycler(
        zoo_client=zoo,
        tripo_client=tripo,
        artifact_store=DummyStore(),
        storage_root=tmp_path,
    )
    cycler._download_bytes = AsyncMock(return_value=b"3mf-data")  # type: ignore[attr-defined]

    path = tmp_path / "img.png"
    path.write_bytes(_make_image_bytes("PNG"))
    refs = [ImageReference(storage_uri=str(path))]

    await cycler.run("duck", references={}, image_refs=refs, mode="organic")

    assert zoo.called is False


@pytest.mark.asyncio
async def test_cad_cycler_converts_unsupported_image(tmp_path: Path):
    tripo = DummyTripo()
    cycler = CADCycler(
        zoo_client=DummyZoo(),
        tripo_client=tripo,
        artifact_store=DummyStore(),
        max_tripo_images=1,
        storage_root=tmp_path,
        mesh_converter=None,
        tripo_convert_enabled=False,
    )
    cycler._download_bytes = AsyncMock(return_value=b"mesh")  # type: ignore[attr-defined]

    path = tmp_path / "img.gif"
    path.write_bytes(_make_image_bytes("GIF"))
    refs = [ImageReference(storage_uri=str(path))]

    artifacts = await cycler.run("duck", references={}, image_refs=refs)

    assert len(artifacts) == 1
    assert tripo.upload_payloads[0][2] == "image/png"
