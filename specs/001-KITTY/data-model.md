# KITTY Data Model

## Overview

Entities supporting conversational orchestration, fabrication control, CAD AI generation, routing auditability, and safety compliance. All persisted records live in PostgreSQL unless noted. Artifacts (STEP/STL/images) are stored in MinIO with references captured below.

## Entities

### User
- **Fields**: `id (uuid)`, `display_name (string)`, `email (string, optional)`, `roles (array<enum>)`, `tailscale_id (string, optional)`, `created_at (timestamp)`
- **Relationships**: Many `User` ↔ Many `Zone` via `ZonePresence`; One `User` ↔ Many `RoutingDecision`; One `User` ↔ Many `SafetyEvent`
- **Validation**: `display_name` required; `roles` must include at least one of `operator`, `engineer`, `safety`, `admin`; email optional for offline operators

### Zone
- **Fields**: `id (uuid)`, `name (string)`, `hazard_level (enum: low|medium|high)`, `requires_ppe (bool)`, `unifi_door_ids (array<string>)`
- **Relationships**: One `Zone` ↔ Many `Device`; One `Zone` ↔ Many `AccessPolicy`; Many `User` ↔ Many `Zone` via `ZonePresence`
- **Validation**: `hazard_level` drives confirmation UX (high requires dual confirmation)

### ZonePresence
- **Fields**: `id (uuid)`, `zone_id (uuid)`, `user_id (uuid)`, `source (enum: unifi|manual|override)`, `status (enum: present|unknown|vacated)`, `observed_at (timestamp)`
- **Relationships**: Many-to-many join between `User` and `Zone`
- **Validation**: `observed_at` must be within configurable TTL to satisfy hazard workflows

### Device
- **Fields**: `id (uuid)`, `external_id (string)`, `kind (enum: printer|camera|light|door|power|sensor)`, `zone_id (uuid)`, `capabilities (jsonb)`, `online_state (enum: online|offline|fault)`, `last_seen (timestamp)`
- **Relationships**: One `Device` ↔ Many `DeviceCommand`; One `Device` ↔ Many `TelemetryEvent`
- **Validation**: `external_id` must be unique within integration; `capabilities` enumerates allowed intents

### DeviceCommand
- **Fields**: `id (uuid)`, `device_id (uuid)`, `conversation_id (uuid)`, `intent (string)`, `payload (jsonb)`, `requested_by (uuid)`, `status (enum: pending|sent|acked|failed)`, `created_at (timestamp)`, `ack_at (timestamp, optional)`
- **Relationships**: Many commands belong to a `ConversationSession`; optionally links to `FabricationJob`
- **Validation**: payload schema validated per device capability; hazardous intents require signature reference to `SafetyEvent`

### TelemetryEvent
- **Fields**: `id (uuid)`, `device_id (uuid)`, `topic (string)`, `payload (jsonb)`, `recorded_at (timestamp)`
- **Relationships**: Many events per `Device`; optionally associated to `FabricationJob` or `ConversationSession`
- **Validation**: `payload` stored raw; ingestion enforces size limit (≤64 KB)

### ConversationSession
- **Fields**: `id (uuid)`, `context_key (string)`, `state (jsonb)`, `active_participants (array<uuid>)`, `last_message_at (timestamp)`
- **Relationships**: One session ↔ Many `DeviceCommand`, `RoutingDecision`, `CADJob`
- **Validation**: `state` persists conversation memory; TTL-based cleanup after inactivity

### RoutingDecision
- **Fields**: `id (uuid)`, `conversation_id (uuid)`, `request_id (uuid)`, `input_hash (string)`, `selected_tier (enum: local|mcp|frontier)`, `confidence (float)`, `cost_estimate (numeric)`, `latency_ms (int)`, `escalation_reason (string)`, `performed_by (uuid|null for system)`
- **Relationships**: Many decisions per session; cost metrics aggregated for observability
- **Validation**: `confidence` range 0–1; `cost_estimate` recorded even when zero; `selected_tier` determines metrics labels

### CADJob
- **Fields**: `id (uuid)`, `conversation_id (uuid)`, `prompt (text)`, `policy_mode (enum: online|offline)`, `status (enum: queued|running|completed|failed)`, `created_at`, `completed_at`
- **Relationships**: One job ↔ Many `CADArtifact`; optionally links to `FabricationJob` when manufacturing initiated
- **Validation**: Offline mode requires fallback pipeline availability; `prompt` sanitized for logging

### CADArtifact
- **Fields**: `id (uuid)`, `cad_job_id (uuid)`, `provider (enum: zoo|tripo|cadquery|freecad|triposr|instantmesh)`, `artifact_key (string S3 path)`, `artifact_type (enum: step|dxf|stl|obj|preview)`, `metadata (jsonb)`, `quality_score (float)`
- **Relationships**: Many artifacts per `CADJob`
- **Validation**: `artifact_key` unique; metadata includes bounding box, material hints, generation params

### FabricationJob
- **Fields**: `id (uuid)`, `device_id (uuid)`, `cad_artifact_id (uuid, optional)`, `gcode_path (string)`, `status (enum: preparing|printing|paused|completed|failed|aborted)`, `started_at`, `completed_at`, `requested_by (uuid)`
- **Relationships**: One job ↔ Many `PrintMonitorEvent`; optional link to `DeviceCommand`
- **Validation**: `gcode_path` points to MinIO object; hazardous materials flagged via metadata

### PrintMonitorEvent
- **Fields**: `id (uuid)`, `fabrication_job_id (uuid)`, `event_type (enum: first_layer_ok|spaghetti_detected|nozzle_clog|completed)`, `confidence (float)`, `snapshot_key (string)`, `occurred_at (timestamp)`
- **Relationships**: Many events per `FabricationJob`
- **Validation**: `confidence` required; `snapshot_key` optional for benign events but mandatory for failure states

### SafetyEvent
- **Fields**: `id (uuid)`, `event_type (enum: hazard_request|unlock|power_enable|override)`, `device_id (uuid, optional)`, `zone_id (uuid, optional)`, `initiated_by (uuid)`, `approved_by (uuid, optional)`, `signature (string)`, `status (enum: pending|approved|denied)`, `created_at`, `resolved_at`
- **Relationships**: Linked to `DeviceCommand` or `AccessPolicy`; snapshots referenced via `evidence_key`
- **Validation**: `signature` must verify against hardware token/public key; `approved_by` required when status=approved

### AccessPolicy
- **Fields**: `id (uuid)`, `name (string)`, `zone_id (uuid)`, `required_roles (array<enum>)`, `requires_dual_confirm (bool)`, `requires_presence (bool)`, `pqe_checks (jsonb)`
- **Relationships**: One policy ↔ Many `SafetyEvent`; per-zone association ensures consistent enforcement
- **Validation**: `required_roles` cannot be empty; `requires_dual_confirm` auto-enforced for high hazard levels

### Notification
- **Fields**: `id (uuid)`, `channel (enum: push|email|slack|webhook)`, `recipient (string)`, `payload (jsonb)`, `status (enum: queued|sent|failed)`, `related_job_id (uuid, optional)`, `created_at`
- **Relationships**: Optional link to `FabricationJob`, `SafetyEvent`, or `RoutingDecision`
- **Validation**: `payload` sanitized; offline queue retry with exponential backoff captured in metadata

## Derived Relationships

- Starting a print creates `FabricationJob` linked to originating `DeviceCommand` and any `CADArtifact` used.  
- Hazardous commands spawn `SafetyEvent` prior to command execution; command status remains `pending` until approval recorded.  
- Routing escalations attach to the same `ConversationSession` to maintain audit trail for cost reporting.  
- CAD jobs in offline mode log fallback provider usage for observability dashboards.

## State Transitions

- **FabricationJob**: `preparing → printing → (paused ↔ printing) → completed|failed|aborted`  
- **CADJob**: `queued → running → completed|failed`  
- **SafetyEvent**: `pending → approved|denied` (approved may trigger `resolved_at` upon execution)  
- **DeviceCommand**: `pending → sent → acked|failed`

## Validation Rules Summary

- Hazard-level zones automatically enforce dual confirmation and presence checks.  
- Offline CAD fallback must succeed before returning response when policy=offline; failure escalates to operator alert.  
- Routing decisions require latency & confidence metrics even for cached responses to satisfy observability SLOs.
