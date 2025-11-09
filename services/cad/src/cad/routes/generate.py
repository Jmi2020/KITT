"""CAD generation API."""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..cycler import CADArtifact
from ..dependencies import get_cad_cycler

router = APIRouter(prefix="/api/cad", tags=["cad"])


class GenerateRequest(BaseModel):
    conversation_id: str = Field(..., alias="conversationId")
    prompt: str
    references: Optional[Dict[str, str]] = None
    image_refs: Optional[List[str]] = Field(default=None, alias="imageRefs")


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
    artifacts: List[CADArtifact] = await cycler.run(
        body.prompt, body.references, body.image_refs
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
