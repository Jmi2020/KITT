"""CAD generation API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import AliasChoices, BaseModel, Field, ConfigDict

from ..cycler import CADArtifact
from ..dependencies import get_cad_cycler
from ..models import ImageReference

router = APIRouter(prefix="/api/cad", tags=["cad"])


class ImageReferencePayload(BaseModel):
    """Payload describing a stored image reference."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(default=None, alias="id")
    download_url: Optional[str] = Field(
        default=None,
        alias="downloadUrl",
        validation_alias=AliasChoices("downloadUrl", "download_url"),
    )
    storage_uri: Optional[str] = Field(
        default=None,
        alias="storageUri",
        validation_alias=AliasChoices("storageUri", "storage_uri"),
    )
    source_url: Optional[str] = Field(
        default=None,
        alias="sourceUrl",
        validation_alias=AliasChoices("sourceUrl", "source_url", "image_url"),
    )
    title: Optional[str] = None
    source: Optional[str] = None
    caption: Optional[str] = None
    friendly_name: Optional[str] = Field(
        default=None,
        alias="friendlyName",
        validation_alias=AliasChoices("friendlyName", "friendly_name"),
    )

    def to_internal(self) -> ImageReference:
        return ImageReference(
            reference_id=self.id,
            download_url=self.download_url,
            storage_uri=self.storage_uri,
            source_url=self.source_url,
            title=self.title,
            source=self.source,
            caption=self.caption,
            friendly_name=self.friendly_name,
        )


class GenerateRequest(BaseModel):
    conversation_id: str = Field(..., alias="conversationId")
    prompt: str
    references: Optional[Dict[str, str]] = None
    image_refs_raw: Optional[List[Any]] = Field(default=None, alias="imageRefs")
    mode: Optional[str] = Field(default=None, alias="mode")


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str
    artifact_type: str = Field(..., alias="artifactType")
    location: str
    metadata: Dict[str, str]


class GenerateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str = Field(..., alias="conversationId")
    artifacts: List[ArtifactResponse]


def _parse_image_ref(item: Any) -> Optional[ImageReference]:
    if isinstance(item, ImageReferencePayload):
        return item.to_internal()
    if isinstance(item, ImageReference):
        return item
    if isinstance(item, str):
        return ImageReference(download_url=item)
    if isinstance(item, dict):
        return ImageReferencePayload(**item).to_internal()
    return None


@router.post("/generate", response_model=GenerateResponse)
async def generate_cad(
    body: GenerateRequest, cycler=Depends(get_cad_cycler)
) -> GenerateResponse:
    parsed_refs: List[ImageReference] = []
    if body.image_refs_raw:
        for item in body.image_refs_raw:
            parsed = _parse_image_ref(item)
            if parsed:
                parsed_refs.append(parsed)

    artifacts: List[CADArtifact] = await cycler.run(
        body.prompt,
        body.references,
        parsed_refs or None,
        mode=body.mode,
    )
    return GenerateResponse(
        conversation_id=body.conversation_id,
        artifacts=[
            ArtifactResponse(
                provider=item.provider,
                artifact_type=item.artifact_type,
                location=item.location,
                metadata=item.metadata,
            )
            for item in artifacts
        ],
    )
