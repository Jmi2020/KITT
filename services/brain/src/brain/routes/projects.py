"""Project memory routes for KITTY."""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict, field_validator

from common.db.projects import (
    append_artifacts,
    get_project,
    list_projects,
    update_project,
    upsert_project,
)

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


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: Optional[str] = None
    summary: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    artifacts: Optional[List[ArtifactModel]] = None


class ArtifactAppendRequest(BaseModel):
    artifacts: List[ArtifactModel] = Field(default_factory=list)

    @field_validator("artifacts")
    @classmethod
    def require_non_empty(cls, v: List[ArtifactModel]) -> List[ArtifactModel]:
        if not v:
            raise ValueError("artifacts must not be empty")
        return v


def serialize_project(project) -> ProjectResponse:
    return ProjectResponse(
        project_id=project.id,
        conversation_id=project.conversation_id,
        title=project.title,
        summary=project.summary,
        artifacts=[ArtifactModel(**artifact) for artifact in (project.artifacts or [])],
        metadata=project.project_metadata or {},
        updated_at=project.updated_at.isoformat(),
    )


@router.get("/", response_model=List[ProjectResponse])
async def get_projects(
    conversation_id: Optional[str] = Query(default=None, alias="conversationId"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    artifact_type: Optional[str] = Query(default=None, alias="artifactType"),
) -> List[ProjectResponse]:
    projects = list_projects(conversation_id, limit, offset, artifact_type)
    return [serialize_project(p) for p in projects]


@router.get("", response_model=List[ProjectResponse], include_in_schema=False)
async def get_projects_no_slash(
    conversation_id: Optional[str] = Query(default=None, alias="conversationId"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    artifact_type: Optional[str] = Query(default=None, alias="artifactType"),
) -> List[ProjectResponse]:
    return await get_projects(conversation_id, limit, offset, artifact_type)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project_detail(project_id: str) -> ProjectResponse:
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return serialize_project(project)


@router.post("/", response_model=ProjectResponse)
async def upsert_project_endpoint(payload: ProjectRequest) -> ProjectResponse:
    project = upsert_project(
        conversation_id=payload.conversation_id,
        title=payload.title,
        summary=payload.summary,
        artifacts=[artifact.model_dump(by_alias=True) for artifact in payload.artifacts],
        metadata=payload.metadata,
    )
    return serialize_project(project)


@router.post("", response_model=ProjectResponse, include_in_schema=False)
async def upsert_project_endpoint_no_slash(payload: ProjectRequest) -> ProjectResponse:
    return await upsert_project_endpoint(payload)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project_endpoint(project_id: str, payload: ProjectUpdateRequest) -> ProjectResponse:
    project = update_project(
        project_id=project_id,
        title=payload.title,
        summary=payload.summary,
        metadata=payload.metadata,
        artifacts=[a.model_dump(by_alias=True) for a in payload.artifacts] if payload.artifacts is not None else None,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return serialize_project(project)


@router.post("/{project_id}/artifacts", response_model=ProjectResponse)
async def append_artifacts_endpoint(project_id: str, payload: ArtifactAppendRequest) -> ProjectResponse:
    project = append_artifacts(
        project_id=project_id,
        artifacts=[artifact.model_dump(by_alias=True) for artifact in payload.artifacts],
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return serialize_project(project)
