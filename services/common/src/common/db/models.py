"""SQLAlchemy models reflecting the shared data model."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RoleEnum(enum.Enum):
    operator = "operator"
    engineer = "engineer"
    safety = "safety"
    admin = "admin"


class HazardLevel(enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class DeviceKind(enum.Enum):
    printer = "printer"
    camera = "camera"
    light = "light"
    door = "door"
    power = "power"
    sensor = "sensor"


class CommandStatus(enum.Enum):
    pending = "pending"
    sent = "sent"
    acked = "acked"
    failed = "failed"


class TelemetryStatus(enum.Enum):
    present = "present"
    unknown = "unknown"
    vacated = "vacated"


class RoutingTier(enum.Enum):
    local = "local"
    mcp = "mcp"
    frontier = "frontier"


class CADProvider(enum.Enum):
    zoo = "zoo"
    tripo = "tripo"
    cadquery = "cadquery"
    freecad = "freecad"
    triposr = "triposr"
    instantmesh = "instantmesh"


class CADPolicy(enum.Enum):
    online = "online"
    offline = "offline"
    auto = "auto"


class CADStatus(enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class FabricationStatus(enum.Enum):
    preparing = "preparing"
    printing = "printing"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    aborted = "aborted"


class SafetyEventType(enum.Enum):
    hazard_request = "hazard_request"
    unlock = "unlock"
    power_enable = "power_enable"
    override = "override"


class SafetyEventStatus(enum.Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"


class GoalType(enum.Enum):
    research = "research"
    fabrication = "fabrication"
    improvement = "improvement"
    optimization = "optimization"


class GoalStatus(enum.Enum):
    identified = "identified"
    approved = "approved"
    rejected = "rejected"
    completed = "completed"


class ProjectStatus(enum.Enum):
    proposed = "proposed"
    approved = "approved"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class TaskStatus(enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    blocked = "blocked"


class TaskPriority(enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    roles: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    tailscale_id: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    routing_decisions: Mapped[List["RoutingDecision"]] = relationship(back_populates="user")
    safety_events: Mapped[List["SafetyEvent"]] = relationship(
        foreign_keys="SafetyEvent.initiated_by", back_populates="initiated_by_user"
    )


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    hazard_level: Mapped[HazardLevel] = mapped_column(Enum(HazardLevel), nullable=False)
    requires_ppe: Mapped[bool] = mapped_column(Boolean, default=False)
    unifi_door_ids: Mapped[List[str]] = mapped_column(JSONB, default=list)

    devices: Mapped[List["Device"]] = relationship(back_populates="zone")
    policies: Mapped[List["AccessPolicy"]] = relationship(back_populates="zone")


class ZonePresence(Base):
    __tablename__ = "zone_presence"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[TelemetryStatus] = mapped_column(Enum(TelemetryStatus), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    zone: Mapped[Zone] = relationship()
    user: Mapped[User] = relationship()


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    kind: Mapped[DeviceKind] = mapped_column(Enum(DeviceKind), nullable=False)
    zone_id: Mapped[Optional[str]] = mapped_column(ForeignKey("zones.id"))
    capabilities: Mapped[dict] = mapped_column(JSONB, default=dict)
    online_state: Mapped[str] = mapped_column(String(32), default="offline")
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    zone: Mapped[Optional[Zone]] = relationship(back_populates="devices")
    commands: Mapped[List["DeviceCommand"]] = relationship(back_populates="device")


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    context_key: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    active_participants: Mapped[List[str]] = mapped_column(JSONB, default=list)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DeviceCommand(Base):
    __tablename__ = "device_commands"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversation_sessions.id"))
    intent: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[CommandStatus] = mapped_column(
        Enum(CommandStatus), default=CommandStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ack_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    safety_event_id: Mapped[Optional[str]] = mapped_column(ForeignKey("safety_events.id"))

    device: Mapped[Device] = relationship(back_populates="commands")
    safety_event: Mapped[Optional["SafetyEvent"]] = relationship(back_populates="device_command")


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_sessions.id"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    selected_tier: Mapped[RoutingTier] = mapped_column(Enum(RoutingTier), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_estimate: Mapped[float] = mapped_column(Numeric(12, 6), default=0.0)
    escalation_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))

    user: Mapped[Optional[User]] = relationship(back_populates="routing_decisions")


class CADJob(Base):
    __tablename__ = "cad_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_sessions.id"), nullable=False
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    policy_mode: Mapped[CADPolicy] = mapped_column(Enum(CADPolicy), default=CADPolicy.auto)
    status: Mapped[CADStatus] = mapped_column(Enum(CADStatus), default=CADStatus.queued)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    artifacts: Mapped[List["CADArtifact"]] = relationship(back_populates="cad_job")


class CADArtifact(Base):
    __tablename__ = "cad_artifacts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    cad_job_id: Mapped[str] = mapped_column(ForeignKey("cad_jobs.id"), nullable=False)
    provider: Mapped[CADProvider] = mapped_column(Enum(CADProvider), nullable=False)
    artifact_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    quality_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 2))

    cad_job: Mapped[CADJob] = relationship(back_populates="artifacts")


class FabricationJob(Base):
    __tablename__ = "fabrication_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    cad_artifact_id: Mapped[Optional[str]] = mapped_column(ForeignKey("cad_artifacts.id"))
    gcode_path: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[FabricationStatus] = mapped_column(
        Enum(FabricationStatus), default=FabricationStatus.preparing
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))

    monitor_events: Mapped[List["PrintMonitorEvent"]] = relationship(
        back_populates="fabrication_job"
    )


class PrintMonitorEvent(Base):
    __tablename__ = "print_monitor_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    fabrication_job_id: Mapped[str] = mapped_column(
        ForeignKey("fabrication_jobs.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    snapshot_key: Mapped[Optional[str]] = mapped_column(String(255))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    fabrication_job: Mapped[FabricationJob] = relationship(back_populates="monitor_events")


class SafetyEvent(Base):
    __tablename__ = "safety_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    event_type: Mapped[SafetyEventType] = mapped_column(Enum(SafetyEventType), nullable=False)
    device_id: Mapped[Optional[str]] = mapped_column(ForeignKey("devices.id"))
    zone_id: Mapped[Optional[str]] = mapped_column(ForeignKey("zones.id"))
    initiated_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SafetyEventStatus] = mapped_column(
        Enum(SafetyEventStatus), default=SafetyEventStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    evidence_key: Mapped[Optional[str]] = mapped_column(String(255))

    initiated_by_user: Mapped[User] = relationship(
        foreign_keys=[initiated_by], back_populates="safety_events"
    )
    device_command: Mapped[Optional[DeviceCommand]] = relationship(back_populates="safety_event")


class AccessPolicy(Base):
    __tablename__ = "access_policies"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), nullable=False)
    required_roles: Mapped[List[str]] = mapped_column(JSONB, default=list)
    requires_dual_confirm: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_presence: Mapped[bool] = mapped_column(Boolean, default=True)
    pqe_checks: Mapped[dict] = mapped_column(JSONB, default=dict)

    zone: Mapped[Zone] = relationship(back_populates="policies")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    related_job_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConversationProject(Base):
    __tablename__ = "conversation_projects"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_sessions.id"), nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String(200))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    artifacts: Mapped[list] = mapped_column(JSONB, default=list)
    project_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Goal(Base):
    """High-level objectives identified by KITTY for autonomous work."""

    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    goal_type: Mapped[GoalType] = mapped_column(Enum(GoalType), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_budget: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    estimated_duration_hours: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[GoalStatus] = mapped_column(Enum(GoalStatus), default=GoalStatus.identified)
    identified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    goal_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    projects: Mapped[List["Project"]] = relationship(back_populates="goal")
    approver: Mapped[Optional[User]] = relationship()


class Project(Base):
    """Autonomous projects KITTY undertakes to achieve goals."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    goal_id: Mapped[Optional[str]] = mapped_column(ForeignKey("goals.id"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.proposed
    )
    budget_allocated: Mapped[float] = mapped_column(Numeric(12, 6), default=0.0)
    budget_spent: Mapped[float] = mapped_column(Numeric(12, 6), default=0.0)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    project_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    goal: Mapped[Optional[Goal]] = relationship(back_populates="projects")
    tasks: Mapped[List["Task"]] = relationship(back_populates="project")
    creator: Mapped[Optional[User]] = relationship()


class Task(Base):
    """Actionable steps within projects, supporting dependencies and scheduling."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.pending)
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority), default=TaskPriority.medium
    )
    depends_on: Mapped[Optional[str]] = mapped_column(ForeignKey("tasks.id"))
    assigned_to: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"))
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    task_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    project: Mapped[Project] = relationship(back_populates="tasks")
    dependency: Mapped[Optional["Task"]] = relationship(remote_side="Task.id")
    assignee: Mapped[Optional[User]] = relationship()


__all__ = [
    "Base",
    # Enums
    "RoleEnum",
    "HazardLevel",
    "DeviceKind",
    "CommandStatus",
    "TelemetryStatus",
    "RoutingTier",
    "CADProvider",
    "CADPolicy",
    "CADStatus",
    "FabricationStatus",
    "SafetyEventType",
    "SafetyEventStatus",
    "GoalType",
    "GoalStatus",
    "ProjectStatus",
    "TaskStatus",
    "TaskPriority",
    # Models
    "User",
    "Zone",
    "ZonePresence",
    "Device",
    "DeviceCommand",
    "TelemetryEvent",
    "ConversationSession",
    "RoutingDecision",
    "CADJob",
    "CADArtifact",
    "FabricationJob",
    "PrintMonitorEvent",
    "SafetyEvent",
    "AccessPolicy",
    "Notification",
    "ConversationProject",
    "Goal",
    "Project",
    "Task",
]
