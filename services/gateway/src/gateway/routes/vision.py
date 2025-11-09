from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

MCP_SRC = Path(__file__).resolve().parents[4] / "mcp" / "src"
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from mcp.servers.vision_server import VisionMCPServer  # noqa: E402

router = APIRouter(prefix="/api/vision", tags=["vision"])
_server = VisionMCPServer()


class ImageSearchRequest(BaseModel):
    query: str
    max_results: int = Field(8, ge=1, le=24)


class ImageSearchResponse(BaseModel):
    results: List[dict]


class ImageFilterRequest(BaseModel):
    query: str
    images: List[dict]
    min_score: float = Field(0.0, ge=0.0, le=1.0)


class ImageFilterResponse(BaseModel):
    results: List[dict]


class ImageSelection(BaseModel):
    id: Optional[str] = None
    image_url: str
    title: Optional[str] = None
    source: Optional[str] = None
    caption: Optional[str] = None


class StoreSelectionRequest(BaseModel):
    session_id: Optional[str] = None
    images: List[ImageSelection]


class StoreSelectionResponse(BaseModel):
    session_id: str
    stored: List[dict]


async def _execute(tool_name: str, payload: dict) -> dict:
    result = await _server.execute_tool(tool_name, payload)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or f"{tool_name} failed")
    return result.data or {}


@router.post("/search", response_model=ImageSearchResponse)
async def search_images(body: ImageSearchRequest) -> ImageSearchResponse:
    data = await _execute("image_search", body.model_dump())
    return ImageSearchResponse(results=data.get("results", []))


@router.post("/filter", response_model=ImageFilterResponse)
async def filter_images(body: ImageFilterRequest) -> ImageFilterResponse:
    data = await _execute("image_filter", body.model_dump())
    return ImageFilterResponse(results=data.get("results", []))


@router.post("/store", response_model=StoreSelectionResponse)
async def store_selection(body: StoreSelectionRequest) -> StoreSelectionResponse:
    payload = body.model_dump()
    data = await _execute("store_selection", payload)
    return StoreSelectionResponse(**data)
