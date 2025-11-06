"""Project memory routes for KITTY."""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, ConfigDict

from common.db.projects import list_projects, upsert_project

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ArtifactModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str
    artifact_type: str = Field(..., alias="artifactType")
    location: str
    metadata: Dict[str, str] = Field(default_factory=dict)


class ProjectRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str = Field(..., alias="conversationId")
    title: Optional[str] = None
    summary: Optional[str] = None
    artifacts: List[ArtifactModel] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_id: str = Field(..., alias="projectId")
    conversation_id: str = Field(..., alias="conversationId")
    title: Optional[str]
    summary: Optional[str]
    artifacts: List[ArtifactModel]
    metadata: Dict[str, str]
    updated_at: str = Field(..., alias="updatedAt")


@router.get("/", response_model=List[ProjectResponse])
async def get_projects(
    conversation_id: Optional[str] = Query(default=None, alias="conversationId"),
) -> List[ProjectResponse]:
    projects = list_projects(conversation_id)
    return [
        ProjectResponse(
            project_id=p.id,
            conversation_id=p.conversation_id,
            title=p.title,
            summary=p.summary,
            artifacts=[ArtifactModel(**artifact) for artifact in (p.artifacts or [])],
            metadata=p.metadata or {},
            updated_at=p.updated_at.isoformat(),
        )
        for p in projects
    ]


@router.post("/", response_model=ProjectResponse)
async def upsert_project_endpoint(payload: ProjectRequest) -> ProjectResponse:
    project = upsert_project(
        conversation_id=payload.conversation_id,
        title=payload.title,
        summary=payload.summary,
        artifacts=[artifact.model_dump(by_alias=True) for artifact in payload.artifacts],
        metadata=payload.metadata,
    )
    return ProjectResponse(
        project_id=project.id,
        conversation_id=project.conversation_id,
        title=project.title,
        summary=project.summary,
        artifacts=[ArtifactModel(**artifact) for artifact in (project.artifacts or [])],
        metadata=project.metadata or {},
        updated_at=project.updated_at.isoformat(),
    )
