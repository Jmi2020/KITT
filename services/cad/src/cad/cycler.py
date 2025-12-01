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
from .utils.mesh_conversion import MeshConversionError, convert_mesh_to_3mf
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
        tripo_face_limit: Optional[int] = None,
        tripo_unit: Optional[str] = "millimeters",
    ) -> None:
        self._zoo = zoo_client
        self._tripo = tripo_client
        self._store = artifact_store
        self._local_runner = local_runner
        self._freecad = freecad_runner
        self._max_tripo_images = max(1, max_tripo_images)
        self._tripo_model_version = tripo_model_version
        self._tripo_texture_quality = tripo_texture_quality
        self._tripo_texture_alignment = tripo_texture_alignment
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
        self._mesh_converter = mesh_converter or convert_mesh_to_3mf
        self._tripo_convert_enabled = tripo_convert_enabled and self._tripo is not None
        self._tripo_face_limit = tripo_face_limit
        self._tripo_unit = tripo_unit

    async def run(
        self,
        prompt: str,
        references: Optional[Dict[str, str]] = None,
        image_refs: Optional[Sequence[Any]] = None,
        mode: Optional[str] = None,
    ) -> List[CADArtifact]:
        artifacts: List[CADArtifact] = []
        references = references or {}
        normalized_refs = self._normalize_image_refs(references, image_refs or [])
        mode_normalized = (mode or "auto").lower()
        run_zoo = mode_normalized in {"auto", "parametric"}
        run_tripo = mode_normalized in {"auto", "organic"}

        # Zoo parametric generation
        if run_zoo:
            try:
                # Use create_and_poll for proper polling loop
                status = await self._zoo.create_and_poll(
                    name="kitty-job", prompt=prompt, parameters=references
                )
                geometry = status.get("geometry", {})
                stored = None
                geo_format = geometry.get("format", "gltf")

                # Handle raw bytes from Zoo API (base64 decoded)
                if geometry.get("data"):
                    ext = f".{geo_format}" if geo_format else ".gltf"
                    stored = await asyncio.to_thread(
                        self._store.save_bytes,
                        geometry["data"],
                        ext,
                        geo_format,
                    )
                    LOGGER.info(
                        "Zoo model saved from bytes",
                        location=stored,
                        format=geo_format,
                    )
                # Fallback: download from URL (legacy behavior)
                elif geometry.get("url"):
                    stored = await self._store.save_from_url(
                        geometry["url"], f".{geo_format}"
                    )

                if stored:
                    artifacts.append(
                        CADArtifact(
                            provider="zoo",
                            artifact_type=geo_format,
                            location=stored,
                            metadata={
                                "credits_used": str(status.get("credits_used", 0))
                            },
                        )
                    )
                    # Emit rename event for Zoo artifacts (STEP uses prompt-only)
                    step_loc = stored if geo_format == "step" else None
                    glb_loc = stored if geo_format in ("gltf", "glb") else None
                    asyncio.create_task(
                        self._emit_rename_event(
                            glb_location=glb_loc,
                            threemf_location=None,
                            thumbnail=None,  # Zoo doesn't provide thumbnails
                            prompt=prompt,
                            step_location=step_loc,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Zoo generation failed", error=str(exc))

        # Tripo cloud mesh generation
        if run_tripo:
            if normalized_refs:
                # Image-to-3D when images are provided
                artifacts.extend(await self._generate_tripo_meshes(normalized_refs))
            else:
                # Text-to-3D when no images
                tripo_text_artifact = await self._generate_tripo_text_mesh(prompt)
                if tripo_text_artifact:
                    artifacts.append(tripo_text_artifact)

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
                upload_meta = await self._tripo.upload_image(
                    data=normalized.data,
                    filename=normalized.filename,
                    content_type=normalized.content_type,
                )
                job = await self._tripo.start_image_task(
                    file_token=upload_meta.get("file_token"),
                    file_type=upload_meta.get("file_type"),
                    version=self._tripo_model_version,
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

    async def _generate_tripo_text_mesh(self, prompt: str) -> Optional[CADArtifact]:
        """Generate a 3D mesh from text prompt using Tripo text-to-model."""
        if not self._tripo or not prompt:
            return None

        try:
            job = await self._tripo.start_text_task(
                prompt=prompt,
                version=self._tripo_model_version,
                texture_quality=self._tripo_texture_quality,
            )
            result = await self._await_tripo_completion(job)
            if not result:
                return None

            result_data = result.get("result", {})
            # Text-to-model uses pbr_model, image-to-model uses model_mesh
            model_info = result_data.get("pbr_model") or result_data.get("model_mesh", {})
            model_url = model_info.get("url") if isinstance(model_info, dict) else None
            if not model_url:
                LOGGER.warning("Tripo text-to-3D result missing model URL", result=result_data)
                return None

            # Download GLB
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(model_url)
                response.raise_for_status()
                glb_data = response.content

            # Always save GLB for preview purposes
            glb_location = await asyncio.to_thread(
                self._store.save_bytes, glb_data, ".glb", "glb"
            )
            LOGGER.info("Saved GLB for preview", location=glb_location)

            # Convert GLB to 3MF for slicer compatibility
            threemf_location = None
            artifact_type = "glb"
            primary_location = glb_location
            try:
                threemf_data = convert_mesh_to_3mf(glb_data, source_format="glb")
                threemf_location = await asyncio.to_thread(
                    self._store.save_bytes, threemf_data, ".3mf", "3mf"
                )
                artifact_type = "3mf"
                primary_location = threemf_location
                LOGGER.info("Saved 3MF for slicer", location=threemf_location)
            except MeshConversionError as conv_err:
                LOGGER.warning("GLB to 3MF conversion failed", error=str(conv_err))

            thumbnail = result.get("thumbnail", "")
            metadata = {
                "task_id": job.get("task_id", ""),
                "thumbnail": thumbnail,
                "source": "text_to_model",
                "prompt": prompt,
                "glb_location": glb_location,
            }
            if threemf_location:
                metadata["threemf_location"] = threemf_location

            # Emit event for background rename
            asyncio.create_task(
                self._emit_rename_event(
                    glb_location=glb_location,
                    threemf_location=threemf_location,
                    thumbnail=thumbnail,
                    prompt=prompt,
                )
            )

            return CADArtifact(
                provider="tripo",
                artifact_type=artifact_type,
                location=primary_location,
                metadata={k: v for k, v in metadata.items() if v},
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Tripo text-to-3D generation failed", error=str(exc))
            return None

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
        result = job.get("result") or job
        if status in {"completed", "success", "succeeded", "done"}:
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
            result = latest.get("result") or latest
            if status in {"completed", "success", "succeeded", "done"}:
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
        full_result = result or {}
        payload = self._unwrap_tripo_payload(full_result)
        thumbnail = (
            self._extract_thumbnail(payload)
            or self._extract_thumbnail(full_result)
            or ""
        )

        # First, try to get the original mesh URL for GLB preview
        mesh_url, mesh_format = self._extract_mesh_url(payload)
        glb_location = None
        glb_bytes = None

        if mesh_url:
            glb_bytes = await self._download_bytes(mesh_url)
            # Always save GLB for preview purposes
            glb_location = self._store.save_bytes(glb_bytes, ".glb", "glb")
            LOGGER.info("Saved GLB for preview", location=glb_location)

        # Try server-side 3MF conversion first
        convert_payload = await self._convert_tripo_task_to_3mf(task_id)
        if convert_payload:
            content, convert_task_id = convert_payload
            threemf_location = self._store.save_bytes(content, ".3mf", "3mf")
            LOGGER.info("Saved 3MF from server conversion", location=threemf_location)
            metadata = {
                "task_id": task_id or "",
                "convert_task_id": convert_task_id or "",
                "thumbnail": thumbnail,
                "source_image": reference.source_url or reference.download_url or "",
                "original_format": "3mf",
                "friendly_name": reference.friendly_name or "",
                "glb_location": glb_location or "",
                "threemf_location": threemf_location,
            }

            # Emit event for background rename
            asyncio.create_task(
                self._emit_rename_event(
                    glb_location=glb_location,
                    threemf_location=threemf_location,
                    thumbnail=thumbnail,
                    prompt=reference.friendly_name or reference.title or "",
                )
            )

            return CADArtifact(
                provider="tripo",
                artifact_type="3mf",
                location=threemf_location,
                metadata={k: v for k, v in metadata.items() if v},
            )

        # Fall back to local conversion if server conversion failed
        if not mesh_url:
            LOGGER.warning("Tripo job completed without mesh URL", task_id=task_id)
            return None

        threemf_location = None
        artifact_type = "glb"
        primary_location = glb_location

        if self._mesh_converter and glb_bytes:
            try:
                converted = await asyncio.to_thread(
                    self._mesh_converter, glb_bytes, mesh_format
                )
                threemf_location = self._store.save_bytes(converted, ".3mf", "3mf")
                artifact_type = "3mf"
                primary_location = threemf_location
                LOGGER.info("Saved 3MF from local conversion", location=threemf_location)
            except MeshConversionError as exc:
                LOGGER.warning(
                    "3MF conversion skipped, using GLB only",
                    task_id=task_id,
                    error=str(exc),
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    "Unexpected 3MF conversion failure",
                    task_id=task_id,
                    error=str(exc),
                )

        metadata = {
            "task_id": task_id or "",
            "thumbnail": thumbnail,
            "source_image": reference.source_url or reference.download_url or "",
            "original_format": mesh_format or "",
            "mesh_url": mesh_url,
            "friendly_name": reference.friendly_name or "",
            "glb_location": glb_location or "",
        }
        if threemf_location:
            metadata["threemf_location"] = threemf_location

        # Emit event for background rename
        asyncio.create_task(
            self._emit_rename_event(
                glb_location=glb_location,
                threemf_location=threemf_location,
                thumbnail=thumbnail,
                prompt=reference.friendly_name or reference.title or "",
            )
        )

        return CADArtifact(
            provider="tripo",
            artifact_type=artifact_type,
            location=primary_location or glb_location or "",
            metadata={k: v for k, v in metadata.items() if v},
        )

    async def _convert_tripo_task_to_3mf(
        self, task_id: Optional[str]
    ) -> Optional[tuple[bytes, Optional[str]]]:
        if not self._tripo_convert_enabled or not self._tripo or not task_id:
            return None
        try:
            convert_job = await self._tripo.start_convert_task(
                original_task_id=task_id,
                fmt="3MF",
                face_limit=self._tripo_face_limit,
                unit=self._tripo_unit,
            )
            convert_result = await self._await_tripo_completion(convert_job)
            payload = self._unwrap_tripo_payload(convert_result)
            threemf_url = self._extract_3mf_url(payload)
            if not threemf_url:
                LOGGER.warning(
                    "Tripo convert completed without 3MF URL",
                    task_id=convert_job.get("task_id"),
                )
                return None
            data = await self._download_bytes(threemf_url)
            return data, convert_job.get("task_id")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Tripo 3MF convert failed",
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
    def _extract_3mf_url(payload: Dict[str, Any]) -> Optional[str]:
        if not payload:
            return None
        candidates: List[Optional[str]] = []
        # Check common 3MF field names from Tripo API
        for key in ("3mf_model", "threemf_model", "model"):
            direct = payload.get(key)
            if isinstance(direct, str):
                candidates.append(direct)
            elif isinstance(direct, dict):
                candidates.append(direct.get("url"))
                candidates.append(direct.get("download_url"))
        # Check direct url/download_url (after unwrapping)
        candidates.append(payload.get("url"))
        candidates.append(payload.get("download_url"))
        model_section = payload.get("model") or {}
        candidates.extend(
            [
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

    @staticmethod
    def _unwrap_tripo_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        for key in ("result", "output", "model"):
            inner = payload.get(key)
            if isinstance(inner, dict):
                return inner
        return payload

    async def _emit_rename_event(
        self,
        glb_location: Optional[str],
        threemf_location: Optional[str],
        thumbnail: Optional[str],
        prompt: Optional[str],
        step_location: Optional[str] = None,
    ) -> None:
        """Emit event for background rename processing.

        For GLB/3MF: Uses prompt extraction first, falls back to vision if thumbnail available.
        For STEP: Uses prompt extraction only (no vision, STEP files can't be previewed).

        This runs in the background and does not block artifact creation.
        If renaming fails, the original UUID-based filename is preserved.
        """
        # Skip if no files and no prompt to work with
        if not (glb_location or threemf_location or step_location):
            LOGGER.debug("Skipping rename - no files to rename")
            return

        # For STEP-only, we need a prompt (no thumbnail fallback)
        if step_location and not glb_location and not threemf_location and not prompt:
            LOGGER.debug("Skipping STEP rename - no prompt available")
            return

        # For GLB/3MF, we need either thumbnail or prompt
        if (glb_location or threemf_location) and not thumbnail and not prompt:
            LOGGER.debug("Skipping rename - no thumbnail or prompt available")
            return

        try:
            from .workers.rename_handler import handle_artifact_saved

            result = await handle_artifact_saved({
                "glb_location": glb_location,
                "threemf_location": threemf_location,
                "step_location": step_location,
                "thumbnail": thumbnail,
                "prompt": prompt,
            })
            if result.get("success"):
                LOGGER.info(
                    "Artifact rename completed",
                    glb_new=result.get("glb_new"),
                    threemf_new=result.get("threemf_new"),
                    step_new=result.get("step_new"),
                )
        except Exception as e:
            LOGGER.warning("Failed to emit rename event", error=str(e))
