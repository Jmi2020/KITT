# Projects API Completion Plan

Status: draft  
Owner: engineering  
Date: 2025-11-25

## Goals
- Deliver a stable Projects API that the web UI can consume without fallback states.
- Normalize how conversation projects capture CAD/fabrication artifacts and metadata.
- Keep URLs gateway-resolvable for downloads; avoid printer-queue/research conflation.

## Data Model (API / DB)
- Project: `projectId`, `conversationId`, `title`, `summary`, `metadata`, `updatedAt`, `deletedAt?`.
- Artifacts: `provider`, `artifactType` (`stl|glb|gcode|thumbnail|log|other`), `location` (gateway URL or proxy path), `metadata` (glb_location, printer, slicer params, refs).
- Storage: Postgres table `conversation_projects` (existing); add `deleted_at` nullable, indexes on (`conversation_id`, `updated_at desc`), optional GIN on artifact types.
- API uses camelCase; DB uses snake_case (`project_metadata`); ensure serialization aligns.

## API Surface
- `GET /api/projects?conversationId=&limit=&cursor=&artifactType=` — paginated, sorted `updated_at desc`.
- `GET /api/projects/{projectId}` — fetch single.
- `POST /api/projects` — create/upsert by `conversationId` or explicit `projectId`; returns stored record.
- `PATCH /api/projects/{projectId}` — update title/summary/metadata; append/replace artifacts via flag.
- `DELETE /api/projects/{projectId}` — soft delete (sets `deleted_at`).
- `POST /api/projects/{projectId}/artifacts` — append validated artifacts.
- `GET /api/projects/{projectId}/artifacts` — list artifacts subset.
- File serving continues via gateway `/api/cad/artifacts/...` (reuse CAD proxy).

## Validation & Behavior
- Enforce JSON responses; consistent schema even on empty sets.
- Validate artifact `location` (no traversal), allowed `artifactType`, and max artifact count per project.
- 404 only for missing resources; 5xx for upstream issues.
- Normalize storage paths to gateway URLs before persisting.

## Ownership & Wiring
- Brain: on CAD completion or fabrication events, call `POST /api/projects` with conversationId + artifacts + summary/title; same for print queue completion (include gcode/logs).
- Gateway: proxy to brain (no local DB); continue serving artifacts via CAD proxy.
- UI: list projects, filter by conversation/artifactType, show download links, fall back to local STL list for offline scenarios.

## Auth / Limits
- Optional auth: restrict by conversation ownership/role once auth is wired.
- Rate-limit project creation if workflows flood; debounce in brain before upsert.

## Testing
- Unit: request/response models, validators, upsert semantics.
- Integration: create → list → append artifact → delete → list empty; CAD flow creates a project automatically.
- E2E: UI `?view=projects` shows seeded project and download link working through gateway.

## Implementation Steps
1) Migrations: add `deleted_at`, indexes; align column naming (`project_metadata`).  
2) Common DB layer: pagination, filters, artifact validation helpers.  
3) Brain routes: expand CRUD, artifact append, soft delete, validation; normalize paths.  
4) Gateway: ensure proxy covers new endpoints; keep CAD artifact proxy.  
5) UI: consume list with filters; handle pagination; keep local STL fallback.  
6) Tests: unit + integration + UI smoke; add sample fixture data for E2E.  
7) Docs: update OpenAPI spec (`specs/001-KITTY/contracts/openapi.yaml`) and UI feature matrix.  
