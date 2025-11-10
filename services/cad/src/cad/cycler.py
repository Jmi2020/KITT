"""CAD cycling orchestrator."""

from __future__ import annotations

import asyncio
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from common.logging import get_logger

from .fallback.freecad_runner import FreeCADRunner
from .models import ImageReference, ReferencePayload
from .providers.tripo_client import TripoClient
from .providers.tripo_local import LocalMeshRunner
from .providers.zoo_client import ZooClient
from .storage.artifact_store import ArtifactStore
from .utils.mesh_conversion import MeshConversionError, convert_mesh_to_stl
from .utils.image_normalization import (
    ImageNormalizationError,
    normalize_image_payload,
)

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
        max_tripo_images: int = 2,
        tripo_model_version: Optional[str] = None,
        tripo_texture_quality: Optional[str] = None,
        tripo_texture_alignment: Optional[str] = None,
        tripo_orientation: Optional[str] = None,
        tripo_poll_interval: float = 3.0,
        tripo_poll_timeout: float = 180.0,
        storage_root: Optional[Path] = None,
        gateway_internal_url: Optional[str] = None,
        mesh_converter: Optional[Callable[[bytes, Optional[str]], bytes]] = None,
        tripo_convert_enabled: bool = True,
        tripo_stl_format: str = "binary",
        tripo_face_limit: Optional[int] = None,
        tripo_unit: Optional[str] = "millimeters",
    ) -> None:
        self._zoo = zoo_client
        self._tripo = tripo_client
        self._store = artifact_store
        self._local_runner = local_runner
        self._freecad = freecad_runner
        self._max_tripo_images = max(1, max_tripo_images)
        self._tripo_model_version = tripo_model_version or "v2.5"
        self._tripo_texture_quality = tripo_texture_quality or "HD"
        self._tripo_texture_alignment = tripo_texture_alignment or "align_image"
        self._tripo_orientation = tripo_orientation
        self._tripo_poll_interval = max(1.0, tripo_poll_interval)
        self._tripo_poll_timeout = max(self._tripo_poll_interval, tripo_poll_timeout)

        root = storage_root or Path(os.getenv("KITTY_STORAGE_ROOT", "storage"))
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        self._reference_root = root
        self._gateway_internal_url = (
            gateway_internal_url
            or os.getenv("GATEWAY_INTERNAL_URL")
            or "http://gateway:8080"
        ).rstrip("/")
        self._mesh_converter = mesh_converter or convert_mesh_to_stl
        self._tripo_convert_enabled = tripo_convert_enabled and self._tripo is not None
        self._tripo_stl_format = (tripo_stl_format or "binary").lower()
        self._tripo_face_limit = tripo_face_limit
        self._tripo_unit = tripo_unit

    async def run(
        self,
        prompt: str,
        references: Optional[Dict[str, str]] = None,
        image_refs: Optional[Sequence[Any]] = None,
    ) -> List[CADArtifact]:
        artifacts: List[CADArtifact] = []
        references = references or {}
        normalized_refs = self._normalize_image_refs(references, image_refs or [])

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

        # Tripo cloud mesh generation
        artifacts.extend(await self._generate_tripo_meshes(normalized_refs))

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

    def _normalize_image_refs(
        self,
        references: Dict[str, str],
        raw_refs: Sequence[Any],
    ) -> List[ImageReference]:
        refs: List[ImageReference] = []
        seen: set[str] = set()

        for item in raw_refs:
            parsed = self._coerce_image_ref(item)
            if not parsed:
                continue
            key = parsed.dedupe_key()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            refs.append(parsed)

        extra_url = references.get("image_url") or references.get("imageUrl")
        if extra_url:
            extra_ref = ImageReference(source_url=extra_url)
            key = extra_ref.dedupe_key()
            if not key or key not in seen:
                if key:
                    seen.add(key)
                refs.append(extra_ref)

        return refs[: self._max_tripo_images]

    def _coerce_image_ref(self, item: Any) -> Optional[ImageReference]:
        if isinstance(item, ImageReference):
            return item
        if isinstance(item, str):
            return ImageReference(download_url=item)
        if hasattr(item, "model_dump"):
            return self._coerce_image_ref(item.model_dump())
        if isinstance(item, dict):
            return ImageReference(
                reference_id=item.get("id") or item.get("reference_id"),
                download_url=item.get("downloadUrl") or item.get("download_url"),
                storage_uri=item.get("storageUri") or item.get("storage_uri"),
                source_url=item.get("sourceUrl")
                or item.get("source_url")
                or item.get("image_url"),
                title=item.get("title"),
                source=item.get("source"),
                caption=item.get("caption"),
            )
        return None

    async def _generate_tripo_meshes(
        self,
        refs: Sequence[ImageReference],
    ) -> List[CADArtifact]:
        if not self._tripo or not refs:
            return []

        artifacts: List[CADArtifact] = []
        for reference in refs:
            payload = await self._load_reference_payload(reference)
            if not payload:
                LOGGER.warning(
                    "Skipping reference - unable to load image data",
                    reference=reference.dedupe_key(),
                )
                continue
            try:
                normalized = normalize_image_payload(
                    payload.data, payload.filename, payload.content_type
                )
            except ImageNormalizationError as exc:
                LOGGER.warning(
                    "Skipping reference - unsupported image format",
                    error=str(exc),
                    reference=reference.dedupe_key(),
                )
                continue
            try:
                upload_url = await self._tripo.upload_image(
                    data=normalized.data,
                    filename=normalized.filename,
                    content_type=normalized.content_type,
                )
                job = await self._tripo.start_image_job(
                    image_url=upload_url,
                    model_version=self._tripo_model_version,
                    texture_quality=self._tripo_texture_quality,
                    texture_alignment=self._tripo_texture_alignment,
                    orientation=self._tripo_orientation,
                )
                result = await self._await_tripo_completion(job)
                artifact = await self._store_tripo_result(
                    result,
                    reference,
                    job.get("task_id"),
                )
                if artifact:
                    artifacts.append(artifact)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    "Tripo cloud generation failed",
                    error=str(exc),
                    reference=reference.dedupe_key(),
                )
        return artifacts

    async def _load_reference_payload(
        self,
        reference: ImageReference,
    ) -> Optional[ReferencePayload]:
        if reference.storage_uri:
            path = self._resolve_storage_path(reference.storage_uri)
            try:
                data = await asyncio.to_thread(path.read_bytes)
                mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                return ReferencePayload(
                    data=data,
                    filename=path.name,
                    content_type=mime,
                )
            except FileNotFoundError:
                LOGGER.warning("Reference file not found", path=str(path))
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    "Failed to read reference file", path=str(path), error=str(exc)
                )

        url = reference.download_url or reference.source_url
        if not url:
            return None
        resolved = self._rewrite_gateway_url(url)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(resolved)
                response.raise_for_status()
                filename = Path(urlparse(resolved).path).name or "reference.jpg"
                content_type = response.headers.get(
                    "content-type", "application/octet-stream"
                )
                return ReferencePayload(
                    data=response.content,
                    filename=filename,
                    content_type=content_type,
                )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Failed to fetch reference URL", url=resolved, error=str(exc))
        return None

    def _resolve_storage_path(self, storage_uri: str) -> Path:
        path = Path(storage_uri)
        if path.is_absolute():
            return path
        try:
            relative = path.relative_to(self._reference_root.name)
            return self._reference_root / relative
        except ValueError:
            return (Path.cwd() / path).resolve()

    def _rewrite_gateway_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.hostname in {"localhost", "127.0.0.1"}:
            base = self._gateway_internal_url
            query = f"?{parsed.query}" if parsed.query else ""
            return f"{base}{parsed.path or '/'}{query}"
        return url

    async def _await_tripo_completion(self, job: Dict[str, Any]) -> Dict[str, Any]:
        status = (job.get("status") or "").lower()
        task_id = job.get("task_id")
        result = job.get("result") or {}
        if status == "completed":
            return result
        if not task_id:
            raise RuntimeError("Tripo response missing task_id")

        start = time.perf_counter()
        while True:
            if time.perf_counter() - start >= self._tripo_poll_timeout:
                raise TimeoutError(f"Tripo job {task_id} timed out")
            await asyncio.sleep(self._tripo_poll_interval)
            latest = await self._tripo.get_task(task_id)
            status = (latest.get("status") or "").lower()
            result = latest.get("result") or {}
            if status == "completed":
                return result
            if status in {"failed", "error"}:
                raise RuntimeError(f"Tripo job {task_id} failed: {result}")

    async def _download_bytes(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    async def _store_tripo_result(
        self,
        result: Dict[str, Any],
        reference: ImageReference,
        task_id: Optional[str],
    ) -> Optional[CADArtifact]:
        convert_payload = await self._convert_tripo_task_to_stl(task_id)
        if convert_payload:
            content, convert_task_id = convert_payload
            location = self._store.save_bytes(content, ".stl")
            metadata = {
                "task_id": task_id or "",
                "convert_task_id": convert_task_id or "",
                "thumbnail": self._extract_thumbnail(result) or "",
                "source_image": reference.source_url or reference.download_url or "",
                "original_format": "stl",
            }
            return CADArtifact(
                provider="tripo",
                artifact_type="stl",
                location=location,
                metadata={k: v for k, v in metadata.items() if v},
            )

        mesh_url, mesh_format = self._extract_mesh_url(result)
        if not mesh_url:
            LOGGER.warning("Tripo job completed without mesh URL", task_id=task_id)
            return None

        mesh_bytes = await self._download_bytes(mesh_url)
        artifact_type = (mesh_format or "glb").lower()
        suffix = f".{artifact_type}"
        content = mesh_bytes

        if self._mesh_converter:
            try:
                converted = await asyncio.to_thread(
                    self._mesh_converter, mesh_bytes, mesh_format
                )
                content = converted
                artifact_type = "stl"
                suffix = ".stl"
            except MeshConversionError as exc:
                LOGGER.warning(
                    "STL conversion skipped, falling back to original mesh",
                    task_id=task_id,
                    error=str(exc),
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    "Unexpected STL conversion failure",
                    task_id=task_id,
                    error=str(exc),
                )

        location = self._store.save_bytes(content, suffix)
        metadata = {
            "task_id": task_id or "",
            "thumbnail": self._extract_thumbnail(result) or "",
            "source_image": reference.source_url or reference.download_url or "",
            "original_format": mesh_format or "",
            "mesh_url": mesh_url,
        }
        return CADArtifact(
            provider="tripo",
            artifact_type=artifact_type or "glb",
            location=location,
            metadata={k: v for k, v in metadata.items() if v},
        )

    async def _convert_tripo_task_to_stl(
        self, task_id: Optional[str]
    ) -> Optional[tuple[bytes, Optional[str]]]:
        if not self._tripo_convert_enabled or not self._tripo or not task_id:
            return None
        try:
            convert_job = await self._tripo.start_convert_task(
                original_task_id=task_id,
                fmt="STL",
                stl_format=self._tripo_stl_format.upper() if self._tripo_stl_format else None,
                face_limit=self._tripo_face_limit,
                unit=self._tripo_unit,
            )
            convert_result = await self._await_tripo_completion(convert_job)
            stl_url = self._extract_stl_url(convert_result)
            if not stl_url:
                LOGGER.warning(
                    "Tripo convert completed without STL URL",
                    task_id=convert_job.get("task_id"),
                )
                return None
            data = await self._download_bytes(stl_url)
            return data, convert_job.get("task_id")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Tripo STL convert failed",
                task_id=task_id,
                error=str(exc),
            )
            return None

    def _extract_mesh_url(self, payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        candidates = [
            payload.get("model_mesh"),
            payload.get("base_model"),
            payload.get("pbr_model"),
            payload.get("model"),
        ]
        for candidate in candidates:
            url, fmt = self._parse_url_candidate(candidate)
            if url:
                return url, fmt or self._guess_format(url)

        direct = payload.get("model_url") or payload.get("mesh_url")
        if isinstance(direct, str) and direct.startswith("http"):
            return direct, self._guess_format(direct)

        return None, None

    @staticmethod
    def _extract_stl_url(payload: Dict[str, Any]) -> Optional[str]:
        if not payload:
            return None
        candidates: List[Optional[str]] = []
        direct = payload.get("stl_model")
        if isinstance(direct, str):
            candidates.append(direct)
        model_section = payload.get("model") or {}
        candidates.extend(
            [
                model_section.get("stl_model"),
                model_section.get("url"),
                model_section.get("download_url"),
            ]
        )
        for value in candidates:
            if isinstance(value, str) and value.startswith("http"):
                return value
        return None

    @staticmethod
    def _parse_url_candidate(candidate: Any) -> tuple[Optional[str], Optional[str]]:
        if isinstance(candidate, str):
            return candidate, None
        if isinstance(candidate, dict):
            url = candidate.get("url") or candidate.get("download_url")
            fmt = candidate.get("format") or candidate.get("type")
            if isinstance(url, str):
                return url, fmt
        return None, None

    @staticmethod
    def _guess_format(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        lower = value.lower()
        if lower.endswith(".glb"):
            return "glb"
        if lower.endswith(".gltf"):
            return "gltf"
        if lower.endswith(".obj"):
            return "obj"
        if lower.endswith(".fbx"):
            return "fbx"
        return None

    @staticmethod
    def _extract_thumbnail(payload: Dict[str, Any]) -> Optional[str]:
        for key in ("rendered_image", "thumbnail", "preview", "cover"):
            value = payload.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
            if isinstance(value, dict):
                url = value.get("url")
                if isinstance(url, str) and url.startswith("http"):
                    return url
        return None
