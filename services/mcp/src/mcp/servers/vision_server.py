# noqa: D401
"""Vision MCP Server: search, rank, and store reference images."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx

try:  # pragma: no cover - optional dependency
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None  # type: ignore[assignment]

try:  # optional CLIP dependencies
    import torch
    import open_clip  # type: ignore
    from PIL import Image
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    open_clip = None  # type: ignore[assignment]
    Image = None  # type: ignore[assignment]

from minio import Minio

from common.config import settings

from ..server import MCPServer, ToolDefinition, ToolResult

LOGGER = logging.getLogger(__name__)


@dataclass
class ImageHit:
    """Normalized image metadata returned to tools."""

    id: str
    title: str
    image_url: str
    page_url: str
    thumbnail_url: Optional[str]
    source: str
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "image_url": self.image_url,
            "page_url": self.page_url,
            "thumbnail_url": self.thumbnail_url,
            "source": self.source,
            "description": self.description,
        }


class ImageSearchClient:
    """Image search coordinator supporting SearXNG, Brave, and DuckDuckGo fallback."""

    def __init__(
        self,
        searx_url: Optional[str],
        safe_level: str = "moderate",
        brave_api_key: Optional[str] = None,
        brave_endpoint: Optional[str] = None,
        provider: str = "auto",
    ) -> None:
        self._searx_url = searx_url.rstrip("/") if searx_url else None
        self._safesearch = safe_level or "moderate"
        self._brave_api_key = brave_api_key
        self._brave_endpoint = brave_endpoint.rstrip("/") if brave_endpoint else None
        self._provider = (provider or "auto").lower()

    async def search(self, query: str, max_results: int = 8) -> List[ImageHit]:
        if not query:
            return []

        for strategy in self._strategy_order():
            if strategy == "brave" and self._brave_api_key and self._brave_endpoint:
                hits = await self._search_brave(query, max_results)
            elif strategy == "searxng" and self._searx_url:
                hits = await self._search_searx(query, max_results)
            elif strategy == "duckduckgo":
                hits = await self._search_duckduckgo(query, max_results)
            else:
                continue

            if hits:
                LOGGER.info("Image search satisfied via %s provider", strategy)
                return hits

        LOGGER.warning("Image search providers returned no results for query '%s'", query)
        return []

    def _strategy_order(self) -> List[str]:
        order: List[str] = []
        if self._provider == "brave":
            order.extend(["brave", "searxng", "duckduckgo"])
        elif self._provider == "searxng":
            order.extend(["searxng", "duckduckgo"])
        elif self._provider == "duckduckgo":
            order.append("duckduckgo")
        else:
            if self._searx_url:
                order.append("searxng")
            if self._brave_api_key and self._brave_endpoint:
                order.append("brave")
            order.append("duckduckgo")
        return order

    async def _search_searx(self, query: str, max_results: int) -> List[ImageHit]:
        url = f"{self._searx_url}/search"
        params = {
            "q": query,
            "format": "json",
            "categories": "images",
            "language": "en",
            "safesearch": 1 if self._safesearch != "off" else 0,
            "pageno": 1,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("SearXNG image search unavailable: %s", exc)
            return []

        hits: List[ImageHit] = []
        seen: set[str] = set()
        for row in payload.get("results", [])[:max_results]:
            image_url = row.get("img_src") or row.get("image")
            page_url = row.get("url")
            if not image_url or not page_url or image_url in seen:
                continue
            seen.add(image_url)
            hits.append(
                ImageHit(
                    id=uuid4().hex,
                    title=row.get("title") or "Untitled",
                    image_url=image_url,
                    page_url=page_url,
                    thumbnail_url=row.get("thumbnail_src"),
                    source=self._extract_source(page_url),
                    description=row.get("content") or row.get("description"),
                )
            )
        return hits

    async def _search_brave(self, query: str, max_results: int) -> List[ImageHit]:
        params = {
            "q": query,
            "count": max(1, min(max_results, 40)),
            "safesearch": self._brave_safesearch(),
        }
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._brave_api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self._brave_endpoint, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Brave image search failed: %s", exc)
            return []

        hits: List[ImageHit] = []
        seen: set[str] = set()
        for row in payload.get("results", [])[:max_results]:
            props = row.get("properties") or {}
            image_url = props.get("url") or row.get("thumbnail") or row.get("url")
            page_url = row.get("source") or row.get("page_url") or row.get("url")
            if not image_url or not page_url or image_url in seen:
                continue
            seen.add(image_url)
            hits.append(
                ImageHit(
                    id=uuid4().hex,
                    title=row.get("title") or "Untitled",
                    image_url=image_url,
                    page_url=page_url,
                    thumbnail_url=row.get("thumbnail"),
                    source=self._extract_source(page_url),
                    description=row.get("description"),
                )
            )
        return hits

    def _brave_safesearch(self) -> str:
        level = (self._safesearch or "").lower()
        if level in {"off", "strict", "moderate"}:
            return level
        return "moderate"

    async def _search_duckduckgo(self, query: str, max_results: int) -> List[ImageHit]:
        hits: List[ImageHit] = []
        seen: set[str] = set()
        try:
            loop = asyncio.get_event_loop()
            if DDGS is None:
                raise RuntimeError("duckduckgo_search not installed")
            rows = await loop.run_in_executor(
                None,
                lambda: list(
                    DDGS().images(
                        keywords=query,
                        safesearch=self._safesearch,
                        max_results=max_results,
                    )
                ),
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("DuckDuckGo image search failed: %s", exc)
            return []

        for row in rows:
            image_url = row.get("image")
            page_url = row.get("url") or row.get("source")
            if not image_url or not page_url or image_url in seen:
                continue
            seen.add(image_url)
            hits.append(
                ImageHit(
                    id=uuid4().hex,
                    title=row.get("title") or "Untitled",
                    image_url=image_url,
                    page_url=page_url,
                    thumbnail_url=row.get("thumbnail"),
                    source=self._extract_source(page_url),
                    description=row.get("snippet") or row.get("description"),
                )
            )
        return hits

    @staticmethod
    def _extract_source(url: str) -> str:
        try:
            netloc = urlparse(url).netloc
            return netloc[4:] if netloc.startswith("www.") else netloc
        except Exception:  # noqa: BLE001
            return ""


class ReferenceStore:
    """Persist selected references to MinIO or local storage."""

    def __init__(
        self,
        *,
        bucket: Optional[str] = None,
        minio_client: Optional[Minio] = None,
        local_root: Optional[Path] = None,
    ) -> None:
        self._bucket = bucket or settings.minio_bucket
        self._minio: Optional[Minio] = minio_client
        self._local_root: Optional[Path] = local_root

        if self._minio is None and settings.minio_access_key and settings.minio_secret_key:
            endpoint = settings.minio_endpoint.replace("http://", "").replace("https://", "")
            secure = settings.minio_endpoint.startswith("https")
            client = Minio(
                endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=secure,
            )
            if not client.bucket_exists(self._bucket):
                client.make_bucket(self._bucket)
            self._minio = client

        self._public_base = (
            os.getenv("GATEWAY_PUBLIC_URL")
            or os.getenv("KITTY_API_BASE")
            or "http://localhost:8080"
        ).rstrip("/")
        self._public_local_root = Path(os.getenv("KITTY_STORAGE_ROOT", "storage"))

        if self._minio is None:
            root = self._local_root or Path("storage/references")
            root.mkdir(parents=True, exist_ok=True)
            self._local_root = root

    async def save(
        self,
        session_id: str,
        image_bytes: bytes,
        content_type: str,
        name: Optional[str] = None,
    ) -> Dict[str, str]:
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        slug = self._sanitize_name(name) if name else uuid4().hex
        object_name = f"references/{session_id}/{slug}-{uuid4().hex}{ext}"
        if self._minio:
            from io import BytesIO

            stream = BytesIO(image_bytes)
            self._minio.put_object(
                self._bucket,
                object_name,
                data=stream,
                length=len(image_bytes),
                content_type=content_type or "application/octet-stream",
            )
            url = self._minio.presigned_get_object(self._bucket, object_name)
            return {"storage_uri": f"minio://{self._bucket}/{object_name}", "url": url}
        assert self._local_root is not None
        path = self._local_root / object_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes)
        return {
            "storage_uri": str(path),
            "url": self._public_url(path),
        }

    @staticmethod
    def _sanitize_name(name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]", "-", name).strip("-")
        return safe or "reference"

    def _public_url(self, path: Path) -> str:
        if not self._public_base:
            return str(path)
        try:
            relative = path.relative_to(self._public_local_root)
        except Exception:
            relative = path
        return f"{self._public_base}/storage/{relative.as_posix()}"


class VisionMCPServer(MCPServer):
    """Vision MCP server exposing image search/filter/store tools."""

    def __init__(self) -> None:
        super().__init__(
            name="vision",
            description="Image search, lightweight relevance scoring, and reference storage",
        )
        searx_url = (
            os.getenv("INTERNAL_SEARXNG_BASE_URL")
            or os.getenv("SEARXNG_BASE_URL")
            or settings.internal_searxng_base_url
            or settings.searxng_base_url
        )
        safe_level = os.getenv("IMAGE_SEARCH_SAFESEARCH", settings.image_search_safesearch)
        brave_api_key = os.getenv("BRAVE_SEARCH_API_KEY", settings.brave_search_api_key)
        brave_endpoint = os.getenv("BRAVE_SEARCH_ENDPOINT", settings.brave_search_endpoint)
        provider = os.getenv("IMAGE_SEARCH_PROVIDER", settings.image_search_provider)
        self._searcher = ImageSearchClient(
            searx_url=searx_url,
            safe_level=safe_level or "moderate",
            brave_api_key=brave_api_key,
            brave_endpoint=brave_endpoint,
            provider=provider or "auto",
        )
        self._store = ReferenceStore()
        self._clip = ClipScorer.create()
        self._clip_weight = float(os.getenv("VISION_CLIP_WEIGHT", "0.7")) if self._clip else 0.0
        self._clip_max_images = int(os.getenv("VISION_CLIP_MAX_IMAGES", "8"))
        self._image_timeout = float(os.getenv("VISION_IMAGE_TIMEOUT", "10"))
        self._register_tools()

    def _register_tools(self) -> None:
        self.register_tool(
            ToolDefinition(
                name="image_search",
                description=(
                    "Search the web for images using SearXNG (if configured) or Brave Search (when an API key "
                    "is provided), with DuckDuckGo as a final fallback. Returns normalized hits with titles, "
                    "image URLs, thumbnails, and source pages."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Image search query"},
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of images to return (default 8)",
                            "minimum": 1,
                            "maximum": 24,
                            "default": 8,
                        },
                    },
                    "required": ["query"],
                },
            )
        )

        self.register_tool(
            ToolDefinition(
                name="image_filter",
                description=(
                    "Compute relevance scores for candidate images using keyword heuristics "
                    "and CLIP-based scoring when available."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Original user query"},
                        "images": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "image_url": {"type": "string"},
                                },
                                "required": ["id", "image_url"],
                            },
                        },
                        "min_score": {
                            "type": "number",
                            "description": "Minimum score (0-1) to keep (default 0)",
                            "minimum": 0,
                            "maximum": 1,
                            "default": 0.0,
                        },
                    },
                    "required": ["query", "images"],
                },
            )
        )

        self.register_tool(
            ToolDefinition(
                name="store_selection",
                description=(
                    "Persist selected reference images to artifact storage (MinIO or local). "
                    "Returns storage URIs and presigned URLs for CAD or future workflows."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Caller-provided session identifier"},
                        "images": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "image_url": {"type": "string"},
                                    "title": {"type": "string"},
                                    "source": {"type": "string"},
                                    "caption": {"type": "string"},
                                },
                                "required": ["image_url"],
                            },
                        },
                    },
                    "required": ["session_id", "images"],
                },
            )
        )

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:  # noqa: D401
        if tool_name == "image_search":
            return await self._tool_image_search(arguments)
        if tool_name == "image_filter":
            return await self._tool_image_filter(arguments)
        if tool_name == "store_selection":
            return await self._tool_store_selection(arguments)
        return ToolResult(success=False, error=f"Tool '{tool_name}' not found")

    async def _tool_image_search(self, args: Dict[str, Any]) -> ToolResult:
        query = args.get("query", "").strip()
        max_results = int(args.get("max_results", 8))
        hits = await self._searcher.search(query, max_results=max_results)
        return ToolResult(success=True, data={"results": [hit.to_dict() for hit in hits]})

    async def _tool_image_filter(self, args: Dict[str, Any]) -> ToolResult:
        query = args.get("query", "").lower()
        tokens = [t for t in re.split(r"\W+", query) if t]
        min_score = float(args.get("min_score", 0.0))
        results: List[Dict[str, Any]] = []
        clip_enabled = self._clip is not None and self._clip_weight > 0
        async with httpx.AsyncClient(timeout=self._image_timeout) as client:
            for idx, image in enumerate(args.get("images", [])):
                text = " ".join(
                    filter(
                        None,
                        [
                            str(image.get("title", "")),
                            str(image.get("description", "")),
                            str(image.get("source", "")),
                        ],
                    )
                ).lower()
                heuristic = self._score(tokens, text)
                clip_score = None
                if clip_enabled and idx < self._clip_max_images:
                    clip_score = await self._score_clip(client, query, image.get("image_url"))
                final_score = heuristic
                if clip_score is not None:
                    clip_norm = (clip_score + 1) / 2  # [-1,1] -> [0,1]
                    final_score = (1 - self._clip_weight) * heuristic + self._clip_weight * clip_norm
                if final_score >= min_score:
                    item = dict(image)
                    item["score"] = round(final_score, 3)
                    if clip_score is not None:
                        item["clip_score"] = round(clip_score, 3)
                    results.append(item)
        results.sort(key=lambda item: item.get("score", 0), reverse=True)
        return ToolResult(success=True, data={"results": results})

    async def _tool_store_selection(self, args: Dict[str, Any]) -> ToolResult:
        session_id = args.get("session_id", uuid4().hex)
        images = args.get("images", [])
        stored: List[Dict[str, Any]] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36",
            "Referer": "https://www.google.com",
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
            for image in images:
                url = image.get("image_url")
                if not url:
                    continue
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    meta = await self._store.save(
                        session_id=session_id,
                        image_bytes=resp.content,
                        content_type=resp.headers.get("content-type", "image/jpeg"),
                        name=image.get("name") or image.get("friendly_name"),
                    )
                    stored.append(
                        {
                            "id": image.get("id") or uuid4().hex,
                            "title": image.get("title"),
                            "source": image.get("source"),
                            "caption": image.get("caption"),
                            "image_url": url,
                            "storage_uri": meta["storage_uri"],
                            "download_url": meta["url"],
                            "friendly_name": image.get("name") or image.get("friendly_name"),
                            "friendlyName": image.get("name") or image.get("friendly_name"),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("Failed to store image %s: %s", url, exc)
        return ToolResult(success=True, data={"stored": stored, "session_id": session_id})

    @staticmethod
    def _score(tokens: List[str], text: str) -> float:
        if not tokens:
            return 0.0
        if not text:
            return 0.0
        matches = sum(1 for token in tokens if token and token in text)
        return matches / len(tokens)

    async def fetch_resource(self, uri: str) -> Dict[str, Any]:  # noqa: D401
        raise ValueError(f"No resources available for {self.name}")

    async def _score_clip(
        self, client: httpx.AsyncClient, query: str, url: Optional[str]
    ) -> Optional[float]:
        if not self._clip or not url:
            return None
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return self._clip.score(query, resp.content)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("CLIP scoring failed for %s: %s", url, exc)
            return None


class ClipScorer:
    """Optional CLIP scorer using open_clip if available."""

    def __init__(self, model: Any, preprocess: Any, tokenizer: Any, device: str) -> None:
        self._model = model
        self._preprocess = preprocess
        self._tokenizer = tokenizer
        self._device = device
        self._pos_templates = ["{}", "a high quality photo of {}", "a close-up of {}"]
        self._neg_templates = ["cartoon {}", "toy {}", "statue {}"]

    @classmethod
    def create(cls) -> Optional["ClipScorer"]:
        if torch is None or open_clip is None or Image is None:
            LOGGER.info("CLIP scorer unavailable (missing torch/open_clip/Pillow)")
            return None
        try:
            device = "cpu"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():  # type: ignore[attr-defined]
                device = "mps"
            model, _, preprocess = open_clip.create_model_and_transforms(
                "ViT-B-32", pretrained="laion2b_s34b_b79k", device=device
            )
            tokenizer = open_clip.get_tokenizer("ViT-B-32")
            return cls(model, preprocess, tokenizer, device)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Failed to initialize CLIP scorer: %s", exc)
            return None

    def score(self, query: str, image_bytes: bytes) -> float:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image_input = self._preprocess(image).unsqueeze(0)
        positives = [template.format(query) for template in self._pos_templates]
        negatives = [template.format(query) for template in self._neg_templates]
        with torch.no_grad():
            image_features = self._model.encode_image(image_input.to(self._device))
            pos_features = self._encode_text(positives)
            neg_features = self._encode_text(negatives)
        image_features /= image_features.norm(dim=-1, keepdim=True)
        pos_features /= pos_features.norm(dim=-1, keepdim=True)
        neg_features /= neg_features.norm(dim=-1, keepdim=True)
        pos_score = (image_features @ pos_features.T).max().item()
        neg_score = (image_features @ neg_features.T).max().item()
        return pos_score - neg_score

    def _encode_text(self, prompts: List[str]):
        tokens = self._tokenizer(prompts)
        with torch.no_grad():
            features = self._model.encode_text(tokens.to(self._device))
        return features


__all__ = ["VisionMCPServer"]
