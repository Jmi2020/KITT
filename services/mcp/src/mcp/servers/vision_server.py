# noqa: D401
"""Vision MCP Server: search, rank, and store reference images."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx
try:
    from duckduckgo_search import DDGS
except ImportError:  # pragma: no cover - optional dependency
    DDGS = None  # type: ignore[assignment]

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
    """Best-effort image search using SearXNG with DuckDuckGo fallback."""

    def __init__(self, searx_url: Optional[str], safe_level: str = "moderate") -> None:
        self._searx_url = searx_url.rstrip("/") if searx_url else None
        self._safesearch = safe_level

    async def search(self, query: str, max_results: int = 8) -> List[ImageHit]:
        if not query:
            return []

        if self._searx_url:
            result = await self._search_searx(query, max_results)
            if result:
                return result

        return await self._search_duckduckgo(query, max_results)

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

        if self._minio is None:
            root = self._local_root or Path("storage/references")
            root.mkdir(parents=True, exist_ok=True)
            self._local_root = root

    async def save(self, session_id: str, image_bytes: bytes, content_type: str) -> Dict[str, str]:
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        object_name = f"references/{session_id}/{uuid4().hex}{ext}"
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
        return {"storage_uri": str(path), "url": str(path)}


class VisionMCPServer(MCPServer):
    """Vision MCP server exposing image search/filter/store tools."""

    def __init__(self) -> None:
        super().__init__(
            name="vision",
            description="Image search, lightweight relevance scoring, and reference storage",
        )
        searx_url = os.getenv("SEARXNG_BASE_URL")
        safe_level = os.getenv("IMAGE_SEARCH_SAFESEARCH", "moderate")
        self._searcher = ImageSearchClient(searx_url=searx_url, safe_level=safe_level)
        self._store = ReferenceStore()
        self._register_tools()

    def _register_tools(self) -> None:
        self.register_tool(
            ToolDefinition(
                name="image_search",
                description=(
                    "Search the web for images using SearXNG (if configured) with a DuckDuckGo fallback. "
                    "Returns normalized hits with titles, image URLs, thumbnails, and source pages."
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
                    "Compute lightweight relevance scores for candidate images. "
                    "Uses keyword overlap as a fast heuristic (Gemma-based vision scoring planned)."
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
            return self._tool_image_filter(arguments)
        if tool_name == "store_selection":
            return await self._tool_store_selection(arguments)
        return ToolResult(success=False, error=f"Tool '{tool_name}' not found")

    async def _tool_image_search(self, args: Dict[str, Any]) -> ToolResult:
        query = args.get("query", "").strip()
        max_results = int(args.get("max_results", 8))
        hits = await self._searcher.search(query, max_results=max_results)
        return ToolResult(success=True, data={"results": [hit.to_dict() for hit in hits]})

    def _tool_image_filter(self, args: Dict[str, Any]) -> ToolResult:
        query = args.get("query", "").lower()
        tokens = [t for t in re.split(r"\W+", query) if t]
        min_score = float(args.get("min_score", 0.0))
        results: List[Dict[str, Any]] = []
        for image in args.get("images", []):
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
            score = self._score(tokens, text)
            if score >= min_score:
                item = dict(image)
                item["score"] = round(score, 3)
                results.append(item)
        results.sort(key=lambda item: item.get("score", 0), reverse=True)
        return ToolResult(success=True, data={"results": results})

    async def _tool_store_selection(self, args: Dict[str, Any]) -> ToolResult:
        session_id = args.get("session_id", uuid4().hex)
        images = args.get("images", [])
        stored: List[Dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30) as client:
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
                    )
                    stored.append(
                        {
                            "id": image.get("id") or uuid4().hex,
                            "title": image.get("title"),
                            "source": image.get("source"),
                            "caption": image.get("caption"),
                            "storage_uri": meta["storage_uri"],
                            "download_url": meta["url"],
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


__all__ = ["VisionMCPServer"]
