"""CAD cycling orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from common.logging import get_logger

from .fallback.freecad_runner import FreeCADRunner
from .providers.tripo_client import TripoClient
from .providers.tripo_local import LocalMeshRunner
from .providers.zoo_client import ZooClient
from .storage.artifact_store import ArtifactStore

LOGGER = get_logger(__name__)


@dataclass
class CADArtifact:
    provider: str
    artifact_type: str
    location: str
    metadata: Dict[str, str]


class CADCycler:
    def __init__(
        self,
        zoo_client: ZooClient,
        tripo_client: Optional[TripoClient],
        artifact_store: ArtifactStore,
        local_runner: Optional[LocalMeshRunner] = None,
        freecad_runner: Optional[FreeCADRunner] = None,
    ) -> None:
        self._zoo = zoo_client
        self._tripo = tripo_client
        self._store = artifact_store
        self._local_runner = local_runner
        self._freecad = freecad_runner

    async def run(
        self, prompt: str, references: Optional[Dict[str, str]] = None
    ) -> List[CADArtifact]:
        artifacts: List[CADArtifact] = []
        references = references or {}

        # Zoo parametric generation
        try:
            zoo_job = await self._zoo.create_model(
                name="kitty-job", prompt=prompt, parameters=references
            )
            status_url = zoo_job.get("polling_url") or zoo_job.get("status_url")
            if status_url:
                status = await self._zoo.poll_status(status_url)
                geometry = status.get("geometry", {})
                if geometry.get("url"):
                    stored = await self._store.save_from_url(geometry["url"], ".gltf")
                    artifacts.append(
                        CADArtifact(
                            provider="zoo",
                            artifact_type=geometry.get("format", "gltf"),
                            location=stored,
                            metadata={
                                "credits_used": str(status.get("credits_used", 0))
                            },
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Zoo generation failed", error=str(exc))

        # Tripo cloud mesh
        if self._tripo:
            try:
                image_url = references.get("image_url")
                if image_url:
                    mesh = await self._tripo.image_to_mesh(image_url)
                    data = mesh.get("data", {})
                    mesh_url = data.get("model_url")
                    if mesh_url:
                        stored = await self._store.save_from_url(mesh_url, ".glb")
                        artifacts.append(
                            CADArtifact(
                                provider="tripo",
                                artifact_type="glb",
                                location=stored,
                                metadata={"thumbnail": data.get("thumbnail", "")},
                            )
                        )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Tripo cloud generation failed", error=str(exc))

        # Local fallback
        if self._local_runner and "image_path" in references:
            image_path = Path(references["image_path"])
            tmp_output = Path("/tmp") / f"{uuid4().hex}.glb"
            success = self._local_runner.generate(image_path, tmp_output)
            if success:
                location = self._store.save_file(tmp_output, ".glb")
                artifacts.append(
                    CADArtifact(
                        provider="tripo_local",
                        artifact_type="glb",
                        location=location,
                        metadata={},
                    )
                )
                tmp_output.unlink(missing_ok=True)

        if self._freecad and "freecad_script" in references:
            script_path = Path(references["freecad_script"])
            tmp_output = Path("/tmp") / f"{uuid4().hex}.step"
            success = self._freecad.run_script(script_path, tmp_output)
            if success:
                location = self._store.save_file(tmp_output, ".step")
                artifacts.append(
                    CADArtifact(
                        provider="freecad",
                        artifact_type="step",
                        location=location,
                        metadata={},
                    )
                )
                tmp_output.unlink(missing_ok=True)

        return artifacts
