"""Integration tests for Brain ↔ CAD service flow.

Tests the integration between the Brain service and CAD service with mocked
provider responses to validate request handling, provider cycling, artifact
storage, and error handling.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from io import BytesIO

# CAD service imports
import sys

sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "services" / "cad" / "src")
)

from cad.cycler import CADCycler
from cad.models import ImageReference
from cad.providers.zoo_client import ZooClient
from cad.providers.tripo_client import TripoClient
from cad.providers.tripo_local import LocalMeshRunner
from cad.fallback.freecad_runner import FreeCADRunner
from cad.storage.artifact_store import ArtifactStore
from PIL import Image


@pytest.fixture
def mock_zoo_client():
    """Mock Zoo.dev API client."""
    client = AsyncMock(spec=ZooClient)
    client.create_model = AsyncMock(
        return_value={
            "id": "job-123",
            "polling_url": "https://api.zoo.dev/jobs/job-123",
            "status": "queued",
        }
    )
    client.poll_status = AsyncMock(
        return_value={
            "id": "job-123",
            "status": "completed",
            "geometry": {
                "url": "https://api.zoo.dev/artifacts/model.gltf",
                "format": "gltf",
            },
            "credits_used": 5,
        }
    )
    return client


@pytest.fixture
def mock_tripo_client():
    """Mock Tripo cloud API client."""
    client = AsyncMock(spec=TripoClient)
    client.upload_image = AsyncMock(return_value={
        "file_token": "token-123",
        "file_type": "image/png",
        "image_url": "https://tripo.ai/uploads/upload.png",
    })
    client.start_image_task = AsyncMock(
        return_value={"task_id": "task-123", "status": "processing", "result": {}}
    )
    async def fake_get_task(task_id):
        if str(task_id).startswith("convert"):
            return {
                "task_id": task_id,
                "status": "completed",
                "result": {
                    "model": {
                        "stl_model": "https://tripo.ai/artifacts/model.stl",
                    }
                },
            }
        return {
            "task_id": task_id,
            "status": "completed",
            "result": {
                "model_mesh": {
                    "url": "https://tripo.ai/artifacts/mesh.glb",
                    "format": "glb",
                },
                "thumbnail": "https://tripo.ai/artifacts/thumbnail.png",
            },
        }

    client.get_task = AsyncMock(side_effect=fake_get_task)

    convert_counter = {"value": 0}

    async def fake_convert_task(**_kwargs):
        convert_counter["value"] += 1
        return {
            "task_id": f"convert-{convert_counter['value']}",
            "status": "processing",
            "result": {},
        }

    client.start_convert_task = AsyncMock(side_effect=fake_convert_task)
    return client


@pytest.fixture
def mock_local_runner():
    """Mock local mesh runner."""
    runner = MagicMock(spec=LocalMeshRunner)
    runner.generate = MagicMock(return_value=True)
    return runner


@pytest.fixture
def mock_freecad_runner():
    """Mock FreeCAD runner."""
    runner = MagicMock(spec=FreeCADRunner)
    runner.run_script = MagicMock(return_value=True)
    return runner


@pytest.fixture
def mock_artifact_store(tmp_path):
    """Mock artifact storage."""
    store = AsyncMock(spec=ArtifactStore)

    # Mock save_from_url to return fake storage locations
    async def mock_save_from_url(url, suffix):
        return f"minio://artifacts/{url.split('/')[-1]}"

    store.save_from_url = mock_save_from_url

    # Mock save_file to return fake storage locations
    def mock_save_file(path, suffix):
        return str(tmp_path / f"artifact{suffix}")

    store.save_file = mock_save_file

    def mock_save_bytes(content, suffix):
        return f"minio://generated/{len(content)}{suffix}"

    store.save_bytes = mock_save_bytes

    return store


def _write_test_image(path: Path, fmt: str = "PNG") -> None:
    image = Image.new("RGB", (4, 4), color=(255, 0, 0))
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    path.write_bytes(buffer.getvalue())


@pytest.fixture
def cad_cycler(
    mock_zoo_client,
    mock_tripo_client,
    mock_artifact_store,
    mock_local_runner,
    mock_freecad_runner,
):
    """Create CADCycler with all mocked dependencies."""
    cycler = CADCycler(
        zoo_client=mock_zoo_client,
        tripo_client=mock_tripo_client,
        artifact_store=mock_artifact_store,
        local_runner=mock_local_runner,
        freecad_runner=mock_freecad_runner,
        mesh_converter=lambda _data, _fmt: b"converted-stl",
    )
    cycler._download_bytes = AsyncMock(return_value=b"converted")  # type: ignore[attr-defined]
    return cycler


@pytest.mark.asyncio
async def test_zoo_generation_success(cad_cycler, mock_zoo_client):
    """Test successful CAD generation via Zoo.dev provider."""
    prompt = "Design a bracket for mounting a sensor"
    artifacts = await cad_cycler.run(prompt)

    # Verify Zoo client was called
    mock_zoo_client.create_model.assert_called_once()
    mock_zoo_client.poll_status.assert_called_once_with(
        "https://api.zoo.dev/jobs/job-123"
    )

    # Verify artifact was created
    assert len(artifacts) >= 1
    zoo_artifact = artifacts[0]
    assert zoo_artifact.provider == "zoo"
    assert zoo_artifact.artifact_type == "gltf"
    assert "model.gltf" in zoo_artifact.location
    assert zoo_artifact.metadata["credits_used"] == "5"


@pytest.mark.asyncio
async def test_tripo_generation_with_image_url(cad_cycler, mock_tripo_client, tmp_path):
    """Test Tripo cloud generation when image_url is provided."""
    prompt = "Convert this image to a 3D mesh"
    image_path = tmp_path / "input.png"
    _write_test_image(image_path)
    image_refs = [ImageReference(storage_uri=str(image_path))]

    artifacts = await cad_cycler.run(prompt, {}, image_refs)

    # Verify Tripo client was called
    mock_tripo_client.upload_image.assert_called_once()
    mock_tripo_client.start_image_task.assert_called_once()
    mock_tripo_client.start_convert_task.assert_called_once()
    mock_tripo_client.get_task.assert_any_await("task-123")  # type: ignore[attr-defined]
    mock_tripo_client.get_task.assert_any_await("convert-1")  # type: ignore[attr-defined]

    # Find Tripo artifact
    tripo_artifacts = [a for a in artifacts if a.provider == "tripo"]
    assert len(tripo_artifacts) == 1
    assert tripo_artifacts[0].artifact_type == "stl"
    assert tripo_artifacts[0].location.endswith(".stl")


@pytest.mark.asyncio
async def test_local_fallback_with_image_path(cad_cycler, mock_local_runner, tmp_path):
    """Test local mesh generation fallback."""
    prompt = "Generate mesh from image"
    image_path = tmp_path / "input.png"
    image_path.touch()
    references = {"image_path": str(image_path)}

    artifacts = await cad_cycler.run(prompt, references)

    # Verify local runner was called
    mock_local_runner.generate.assert_called_once()

    # Find local artifact
    local_artifacts = [a for a in artifacts if a.provider == "tripo_local"]
    assert len(local_artifacts) == 1
    assert local_artifacts[0].artifact_type == "glb"


@pytest.mark.asyncio
async def test_freecad_fallback_with_script(cad_cycler, mock_freecad_runner, tmp_path):
    """Test FreeCAD script execution fallback."""
    prompt = "Execute CAD script"
    script_path = tmp_path / "bracket.py"
    script_path.touch()
    references = {"freecad_script": str(script_path)}

    artifacts = await cad_cycler.run(prompt, references)

    # Verify FreeCAD runner was called
    mock_freecad_runner.run_script.assert_called_once()

    # Find FreeCAD artifact
    freecad_artifacts = [a for a in artifacts if a.provider == "freecad"]
    assert len(freecad_artifacts) == 1
    assert freecad_artifacts[0].artifact_type == "step"


@pytest.mark.asyncio
async def test_zoo_failure_continues_to_next_provider(
    mock_tripo_client, mock_artifact_store, tmp_path
):
    """Test that Zoo failure doesn't stop other providers."""
    # Create Zoo client that fails
    failing_zoo_client = AsyncMock(spec=ZooClient)
    failing_zoo_client.create_model = AsyncMock(side_effect=Exception("Zoo API error"))

    cycler = CADCycler(
        zoo_client=failing_zoo_client,
        tripo_client=mock_tripo_client,
        artifact_store=mock_artifact_store,
        mesh_converter=lambda _data, _fmt: b"converted-stl",
    )
    cycler._download_bytes = AsyncMock(return_value=b"converted")  # type: ignore[attr-defined]

    prompt = "Design a part"
    image_path = tmp_path / "input.png"
    _write_test_image(image_path)
    image_refs = [ImageReference(storage_uri=str(image_path))]
    artifacts = await cycler.run(prompt, {}, image_refs)

    # Verify Zoo failed but Tripo still ran
    failing_zoo_client.create_model.assert_called_once()
    mock_tripo_client.upload_image.assert_called_once()
    mock_tripo_client.start_convert_task.assert_called_once()

    # Should have Tripo artifact but not Zoo
    assert len(artifacts) >= 1
    assert all(a.provider != "zoo" for a in artifacts)
    assert any(a.provider == "tripo" for a in artifacts)


@pytest.mark.asyncio
async def test_all_providers_fail_returns_empty_list(mock_artifact_store, tmp_path):
    """Test graceful handling when all providers fail."""
    failing_zoo = AsyncMock(spec=ZooClient)
    failing_zoo.create_model = AsyncMock(side_effect=Exception("Zoo error"))

    failing_tripo = AsyncMock(spec=TripoClient)
    failing_tripo.upload_image = AsyncMock(side_effect=Exception("Tripo error"))
    failing_tripo.start_convert_task = AsyncMock()

    cycler = CADCycler(
        zoo_client=failing_zoo,
        tripo_client=failing_tripo,
        artifact_store=mock_artifact_store,
        tripo_convert_enabled=False,
    )

    prompt = "Design a part"
    image_path = tmp_path / "input.png"
    _write_test_image(image_path)
    image_refs = [ImageReference(storage_uri=str(image_path))]
    artifacts = await cycler.run(prompt, {}, image_refs)

    # Should return empty list, not raise exception
    assert artifacts == []


@pytest.mark.asyncio
async def test_multiple_providers_return_multiple_artifacts(cad_cycler, tmp_path):
    """Test that multiple providers can generate artifacts simultaneously."""
    prompt = "Design a bracket"
    image_path = tmp_path / "input.png"
    _write_test_image(image_path)
    image_refs = [ImageReference(storage_uri=str(image_path))]

    artifacts = await cad_cycler.run(prompt, {}, image_refs)

    # Should have artifacts from both Zoo and Tripo
    providers = {a.provider for a in artifacts}
    assert "zoo" in providers
    assert "tripo" in providers
    assert len(artifacts) >= 2


@pytest.mark.asyncio
async def test_artifact_storage_integration(mock_zoo_client, mock_artifact_store):
    """Test that artifacts are properly stored via ArtifactStore."""
    cycler = CADCycler(
        zoo_client=mock_zoo_client,
        tripo_client=None,
        artifact_store=mock_artifact_store,
    )

    prompt = "Design a part"
    artifacts = await cycler.run(prompt)

    # Verify artifact storage was called
    assert artifacts[0].location.startswith("minio://artifacts/")


@pytest.mark.asyncio
async def test_empty_references_dict(cad_cycler):
    """Test that empty references dict doesn't cause errors."""
    prompt = "Design a part"
    artifacts = await cad_cycler.run(prompt, references={})

    # Should still run Zoo provider
    assert len(artifacts) >= 1
    assert any(a.provider == "zoo" for a in artifacts)


@pytest.mark.asyncio
async def test_none_references_param(cad_cycler):
    """Test that None references param doesn't cause errors."""
    prompt = "Design a part"
    artifacts = await cad_cycler.run(prompt, references=None)

    # Should still run Zoo provider
    assert len(artifacts) >= 1
    assert any(a.provider == "zoo" for a in artifacts)


@pytest.mark.asyncio
async def test_zoo_missing_geometry_url(mock_artifact_store):
    """Test handling of Zoo response missing geometry URL."""
    zoo_client = AsyncMock(spec=ZooClient)
    zoo_client.create_model = AsyncMock(
        return_value={
            "id": "job-123",
            "polling_url": "https://api.zoo.dev/jobs/job-123",
        }
    )
    zoo_client.poll_status = AsyncMock(
        return_value={
            "id": "job-123",
            "status": "completed",
            "geometry": {},  # Missing URL
        }
    )

    cycler = CADCycler(
        zoo_client=zoo_client, tripo_client=None, artifact_store=mock_artifact_store
    )

    artifacts = await cycler.run("Design a part")

    # Should return empty list when geometry URL is missing
    assert artifacts == []


@pytest.mark.asyncio
async def test_tripo_missing_model_url(mock_artifact_store, tmp_path):
    """Test handling of Tripo response missing model URL."""
    tripo_client = AsyncMock(spec=TripoClient)
    tripo_client.upload_image = AsyncMock(return_value={
        "file_token": "token-missing",
        "file_type": "image/png",
    })
    tripo_client.start_image_task = AsyncMock(
        return_value={"task_id": "task-missing", "status": "processing", "result": {}}
    )
    tripo_client.get_task = AsyncMock(
        return_value={"task_id": "task-missing", "status": "completed", "result": {}}
    )

    cycler = CADCycler(
        zoo_client=AsyncMock(spec=ZooClient),
        tripo_client=tripo_client,
        artifact_store=mock_artifact_store,
        tripo_convert_enabled=False,
    )

    # Configure Zoo to fail so we only test Tripo
    cycler._zoo.create_model = AsyncMock(side_effect=Exception("Skip Zoo"))

    image_path = tmp_path / "input.png"
    _write_test_image(image_path)
    image_refs = [ImageReference(storage_uri=str(image_path))]
    artifacts = await cycler.run("Convert image", {}, image_refs)

    # Should have no Tripo artifacts
    assert all(a.provider != "tripo" for a in artifacts)


@pytest.mark.asyncio
async def test_local_runner_failure_is_silent(mock_artifact_store, tmp_path):
    """Test that local runner failure doesn't crash the cycler."""
    failing_local = MagicMock(spec=LocalMeshRunner)
    failing_local.generate = MagicMock(return_value=False)  # Failure

    cycler = CADCycler(
        zoo_client=AsyncMock(spec=ZooClient),
        tripo_client=None,
        artifact_store=mock_artifact_store,
        local_runner=failing_local,
    )

    # Configure Zoo to fail
    cycler._zoo.create_model = AsyncMock(side_effect=Exception("Skip Zoo"))

    image_path = tmp_path / "input.png"
    image_path.touch()
    artifacts = await cycler.run("Convert image", {"image_path": str(image_path)})

    # Should return empty list, not raise exception
    assert artifacts == []
    failing_local.generate.assert_called_once()


@pytest.mark.asyncio
async def test_freecad_runner_failure_is_silent(mock_artifact_store, tmp_path):
    """Test that FreeCAD runner failure doesn't crash the cycler."""
    failing_freecad = MagicMock(spec=FreeCADRunner)
    failing_freecad.run_script = MagicMock(return_value=False)  # Failure

    cycler = CADCycler(
        zoo_client=AsyncMock(spec=ZooClient),
        tripo_client=None,
        artifact_store=mock_artifact_store,
        freecad_runner=failing_freecad,
    )

    # Configure Zoo to fail
    cycler._zoo.create_model = AsyncMock(side_effect=Exception("Skip Zoo"))

    script_path = tmp_path / "script.py"
    script_path.touch()
    artifacts = await cycler.run("Run script", {"freecad_script": str(script_path)})

    # Should return empty list, not raise exception
    assert artifacts == []
    failing_freecad.run_script.assert_called_once()
