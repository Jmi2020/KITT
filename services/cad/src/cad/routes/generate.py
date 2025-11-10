"""CAD generation API."""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from fastapi import APIRouter, Depends
from pydantic import AliasChoices, BaseModel, Field
from pydantic import ConfigDict

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

    def to_internal(self) -> ImageReference:
        return ImageReference(
            reference_id=self.id,
            download_url=self.download_url,
            storage_uri=self.storage_uri,
            source_url=self.source_url,
            title=self.title,
            source=self.source,
            caption=self.caption,
        )


class GenerateRequest(BaseModel):
    conversation_id: str = Field(..., alias="conversationId")
    prompt: str
    references: Optional[Dict[str, str]] = None
    image_refs: Optional[List[Union[ImageReferencePayload, str]]] = Field(
        default=None, alias="imageRefs"
    )


class ArtifactResponse(BaseModel):
    provider: str
    artifact_type: str = Field(..., alias="artifactType")
    location: str
    metadata: Dict[str, str]


class GenerateResponse(BaseModel):
    conversation_id: str = Field(..., alias="conversationId")
    artifacts: List[ArtifactResponse]


@router.post("/generate", response_model=GenerateResponse)
async def generate_cad(
    body: GenerateRequest, cycler=Depends(get_cad_cycler)
) -> GenerateResponse:
    parsed_refs: List[ImageReference] = []
    if body.image_refs:
        for item in body.image_refs:
            if isinstance(item, ImageReferencePayload):
                parsed_refs.append(item.to_internal())
            elif isinstance(item, str):
                parsed_refs.append(ImageReference(download_url=item))

    artifacts: List[CADArtifact] = await cycler.run(
        body.prompt,
        body.references,
        parsed_refs or None,
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
