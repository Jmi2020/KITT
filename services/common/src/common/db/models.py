"""SQLAlchemy models reflecting the shared data model."""

from __future__ import annotations

import enum
from datetime import datetime, date
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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
    procurement = "procurement"  # Phase 4: Material procurement research


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


class DiscoveryMethod(enum.Enum):
    """Discovery method for network devices."""
    mdns = "mdns"
    ssdp = "ssdp"
    bamboo_udp = "bamboo_udp"
    snapmaker_udp = "snapmaker_udp"
    network_scan = "network_scan"
    manual = "manual"


class DiscoveredDeviceType(enum.Enum):
    """Types of discovered network devices."""
    printer_3d = "printer_3d"
    printer_cnc = "printer_cnc"
    printer_laser = "printer_laser"
    raspberry_pi = "raspberry_pi"
    esp32 = "esp32"
    esp8266 = "esp8266"
    smart_home = "smart_home"
    unknown = "unknown"


class ScanStatus(enum.Enum):
    """Discovery scan status."""
    running = "running"
    completed = "completed"
    failed = "failed"


class FailureReason(enum.Enum):
    """Phase 4: Print failure classification."""
    first_layer_adhesion = "first_layer_adhesion"
    warping = "warping"
    stringing = "stringing"
    spaghetti = "spaghetti"
    nozzle_clog = "nozzle_clog"
    filament_runout = "filament_runout"
    layer_shift = "layer_shift"
    overheating = "overheating"
    support_failure = "support_failure"
    user_cancelled = "user_cancelled"
    power_failure = "power_failure"
    other = "other"


class InventoryStatus(enum.Enum):
    """Phase 4: Material inventory spool status."""
    available = "available"
    in_use = "in_use"
    depleted = "depleted"
    reserved = "reserved"


class QueueStatus(enum.Enum):
    """Phase 4: Print queue job status."""
    queued = "queued"
    scheduled = "scheduled"  # P3: Assigned to printer, not yet started
    slicing = "slicing"      # P3: Generating G-code
    uploading = "uploading"  # P3: Uploading to printer
    printing = "printing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(200))
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_user_message: Mapped[Optional[str]] = mapped_column(Text)
    last_assistant_message: Mapped[Optional[str]] = mapped_column(Text)


class ConversationRole(enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_sessions.id"), nullable=False
    )
    role: Mapped[ConversationRole] = mapped_column(Enum(ConversationRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    conversation: Mapped[ConversationSession] = relationship()


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
    __table_args__ = (
        Index(
            "ix_conversation_projects_conversation_id_updated_at",
            "conversation_id",
            "updated_at",
        ),
        Index("ix_conversation_projects_updated_at", "updated_at"),
        Index(
            "ix_conversation_projects_artifacts_gin",
            "artifacts",
            postgresql_using="gin",
        ),
    )

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
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


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

    # Phase 3: Outcome tracking and effectiveness
    effectiveness_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    outcome_measured_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    learn_from: Mapped[bool] = mapped_column(default=True)  # Use in feedback loop
    baseline_captured: Mapped[bool] = mapped_column(default=False)
    baseline_captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    projects: Mapped[List["Project"]] = relationship(back_populates="goal")
    outcome: Mapped[Optional["GoalOutcome"]] = relationship(back_populates="goal", uselist=False)
    print_outcomes: Mapped[List["PrintOutcome"]] = relationship(back_populates="goal")  # Phase 4
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

    # Phase 3: Actual tracking for effectiveness measurement
    actual_cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(12, 6))
    actual_duration_hours: Mapped[Optional[int]] = mapped_column(Integer)

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


class GoalOutcome(Base):
    """Phase 3: Outcome tracking and effectiveness measurement for completed goals.

    Tracks baseline metrics, outcome metrics, and effectiveness scores to enable
    learning and continuous improvement of autonomous goal generation.
    """

    __tablename__ = "goal_outcomes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id"), nullable=False, unique=True)

    # Measurement window
    baseline_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    measurement_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Baseline metrics (before goal execution)
    # Example: {"related_failures": 8, "kb_views": 0, "manual_research_hours": 4.5}
    baseline_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Post-execution metrics (30 days after completion)
    # Example: {"related_failures": 2, "kb_views": 23, "time_saved_hours": 15.2}
    outcome_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Effectiveness scoring (0-100 scale)
    impact_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))  # Problem solved
    roi_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))  # Return on investment
    adoption_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))  # Usage metrics
    quality_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))  # Output quality
    effectiveness_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))  # Weighted avg

    # Metadata
    measurement_method: Mapped[Optional[str]] = mapped_column(String(50))  # 'kb_usage', 'failure_rate'
    notes: Mapped[Optional[str]] = mapped_column(Text)
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    measured_by: Mapped[str] = mapped_column(String(100), default="system-autonomous")

    goal: Mapped[Goal] = relationship(back_populates="outcome")


class Material(Base):
    """Phase 4: Filament material catalog.

    Tracks material properties, costs, and temperature ranges for
    intelligent material selection and inventory management.
    """

    __tablename__ = "materials"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # e.g., "pla_black_esun"
    material_type: Mapped[str] = mapped_column(String(50), nullable=False)  # pla, petg, abs, tpu
    color: Mapped[str] = mapped_column(String(50), nullable=False)
    manufacturer: Mapped[str] = mapped_column(String(120), nullable=False)
    cost_per_kg_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    density_g_cm3: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)  # e.g., 1.24 for PLA

    # Temperature ranges
    nozzle_temp_min_c: Mapped[int] = mapped_column(Integer, nullable=False)
    nozzle_temp_max_c: Mapped[int] = mapped_column(Integer, nullable=False)
    bed_temp_min_c: Mapped[int] = mapped_column(Integer, nullable=False)
    bed_temp_max_c: Mapped[int] = mapped_column(Integer, nullable=False)

    # Material properties
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)  # strength, flexibility, food_safe, etc.
    sustainability_score: Mapped[Optional[int]] = mapped_column(Integer)  # 0-100

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.utcnow)

    # Relationships
    inventory: Mapped[List["InventoryItem"]] = relationship(back_populates="material")
    print_outcomes: Mapped[List["PrintOutcome"]] = relationship(back_populates="material")
    queued_prints: Mapped[List["QueuedPrint"]] = relationship(back_populates="material")


class InventoryItem(Base):
    """Phase 4: Physical filament spool inventory.

    Tracks individual spools with current weight, enabling material
    usage tracking and low-inventory alerts.
    """

    __tablename__ = "inventory"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # spool ID
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(120))  # shelf, bin, printer
    purchase_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    initial_weight_grams: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    current_weight_grams: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[InventoryStatus] = mapped_column(Enum(InventoryStatus), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.utcnow)

    # Relationships
    material: Mapped[Material] = relationship(back_populates="inventory")
    queued_prints: Mapped[List["QueuedPrint"]] = relationship(back_populates="spool")


class PrintOutcome(Base):
    """Phase 4: Historical print job outcomes for learning.

    Captures success/failure, quality scores, and print settings to enable
    intelligent success prediction and setting recommendations.
    """

    __tablename__ = "print_outcomes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    goal_id: Mapped[Optional[str]] = mapped_column(ForeignKey("goals.id"))  # if autonomous
    printer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False)

    # Outcome
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_reason: Mapped[Optional[FailureReason]] = mapped_column(Enum(FailureReason))
    quality_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)  # 0-100

    # Actuals
    actual_duration_hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    actual_cost_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    material_used_grams: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Print Settings
    print_settings: Mapped[dict] = mapped_column(JSONB, nullable=False)  # temp, speed, layer height, infill

    # Quality Metrics (if available)
    quality_metrics: Mapped[dict] = mapped_column(JSONB, default=dict)  # layer_consistency, surface_finish

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Visual Evidence (Phase 1: Human-in-Loop)
    initial_snapshot_url: Mapped[Optional[str]] = mapped_column(String(500))  # First layer snapshot
    final_snapshot_url: Mapped[Optional[str]] = mapped_column(String(500))  # Completed print
    snapshot_urls: Mapped[list] = mapped_column(JSONB, default=list)  # All periodic snapshots
    video_url: Mapped[Optional[str]] = mapped_column(String(500))  # Full timelapse (optional)

    # Human Feedback (Phase 1: Human-in-Loop)
    human_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    review_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100))

    # Visual Characteristics (Phase 2+: Future Autonomous Detection)
    visual_defects: Mapped[list] = mapped_column(JSONB, default=list)  # Detected visual issues
    anomaly_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_confidence: Mapped[Optional[float]] = mapped_column(Numeric(3, 2))  # 0.00-1.00
    auto_stopped: Mapped[bool] = mapped_column(Boolean, default=False)  # Did KITTY auto-stop?

    # Relationships
    goal: Mapped[Optional[Goal]] = relationship(back_populates="print_outcomes")
    material: Mapped[Material] = relationship(back_populates="print_outcomes")


class QueuedPrint(Base):
    """Phase 4: Print queue with optimization metadata.

    Tracks queued print jobs with priority scoring, deadline management,
    and optimization reasoning. Enhanced in P3 #20 for multi-printer coordination.
    """

    __tablename__ = "print_queue"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    job_name: Mapped[str] = mapped_column(String(255), nullable=False)  # P3: User-friendly name

    # Files
    stl_path: Mapped[str] = mapped_column(String(500), nullable=False)
    gcode_path: Mapped[Optional[str]] = mapped_column(String(500))  # P3: Generated after slicing

    # Assignment
    printer_id: Mapped[Optional[str]] = mapped_column(String(100))  # P3: Assigned after scheduling (nullable)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False)
    spool_id: Mapped[Optional[str]] = mapped_column(ForeignKey("inventory.id"))

    # Print Settings
    print_settings: Mapped[dict] = mapped_column(JSONB, nullable=False)  # P3: {nozzle_temp, bed_temp, layer_height, infill, speed}

    # Scheduling
    status: Mapped[QueueStatus] = mapped_column(Enum(QueueStatus), nullable=False)
    status_reason: Mapped[Optional[str]] = mapped_column(Text)  # P3: Error details if failed
    priority: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-10
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime)
    scheduled_start: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Estimates
    estimated_duration_hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    estimated_material_grams: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    success_probability: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))  # 0-100

    # Optimization Metadata
    priority_score: Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    optimization_reasoning: Mapped[Optional[str]] = mapped_column(Text)

    # Retry Logic (P3)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)

    # Tracking
    created_by: Mapped[Optional[str]] = mapped_column(String(100))  # P3: user_id or "autonomous"
    goal_id: Mapped[Optional[str]] = mapped_column(ForeignKey("goals.id"))  # P3: autonomous goal linkage
    outcome_id: Mapped[Optional[str]] = mapped_column(ForeignKey("print_outcomes.id"))  # P3: link to PrintOutcome

    # Timestamps
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    material: Mapped[Material] = relationship(back_populates="queued_prints")
    spool: Mapped[Optional[InventoryItem]] = relationship(back_populates="queued_prints")
    goal: Mapped[Optional[Goal]] = relationship()
    outcome: Mapped[Optional[PrintOutcome]] = relationship()
    status_history: Mapped[List["JobStatusHistory"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobStatusHistory(Base):
    """P3 #20: Audit trail for print job status changes.

    Tracks all status transitions for debugging and analytics.
    """

    __tablename__ = "job_status_history"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("print_queue.id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    changed_by: Mapped[Optional[str]] = mapped_column(String(100))

    # Relationships
    job: Mapped[QueuedPrint] = relationship(back_populates="status_history")


class DiscoveredDevice(Base):
    """Network-discovered IoT devices (printers, Raspberry Pi, ESP32, etc.)."""

    __tablename__ = "discovered_devices"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)

    # Discovery metadata
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    discovery_method: Mapped[str] = mapped_column(String(32), nullable=False)

    # Network information
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    mac_address: Mapped[Optional[str]] = mapped_column(String(17))
    hostname: Mapped[Optional[str]] = mapped_column(String(255))

    # Device identification
    device_type: Mapped[str] = mapped_column(String(32), nullable=False)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(120))
    model: Mapped[Optional[str]] = mapped_column(String(120))
    serial_number: Mapped[Optional[str]] = mapped_column(String(255))
    firmware_version: Mapped[Optional[str]] = mapped_column(String(120))

    # Service information
    services: Mapped[list] = mapped_column(JSONB, default=list)
    capabilities: Mapped[dict] = mapped_column(JSONB, default=dict)

    # User approval
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Status
    is_online: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence_score: Mapped[float] = mapped_column(Numeric(3, 2), default=0.5)


class DiscoveryScan(Base):
    """History of network discovery scans."""

    __tablename__ = "discovery_scans"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="running")
    methods: Mapped[list] = mapped_column(JSONB, default=list)
    devices_found: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    triggered_by: Mapped[Optional[str]] = mapped_column(String(255))


class AutonomousSchedule(Base):
    __tablename__ = "autonomous_schedules"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255))
    job_type: Mapped[str] = mapped_column(String(100))
    job_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    natural_language_schedule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cron_expression: Mapped[str] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    budget_limit_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_execution_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_execution_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class JobExecutionHistory(Base):
    __tablename__ = "job_execution_history"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(255))
    job_name: Mapped[str] = mapped_column(String(255))
    execution_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(50))
    budget_spent_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class BudgetForecast(Base):
    __tablename__ = "budget_forecasts"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    forecast_date: Mapped[date] = mapped_column(Date, unique=True)
    total_scheduled_jobs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    actual_cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    daily_limit_usd: Mapped[float] = mapped_column(Numeric(10, 4), default=5.00)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class CollectivePatternEnum(enum.Enum):
    """Collective deliberation patterns."""
    council = "council"
    debate = "debate"
    pipeline = "pipeline"


class CollectiveStatusEnum(enum.Enum):
    """Collective session status."""
    pending = "pending"
    running = "running"
    completed = "completed"
    error = "error"
    cancelled = "cancelled"


class CollectiveSessionRecord(Base):
    """Persistent storage for collective meta-agent sessions.

    Stores the full history of deliberation sessions including proposals,
    verdicts, and metadata for analysis and replay.
    """

    __tablename__ = "collective_sessions"
    __table_args__ = (
        Index("ix_collective_sessions_user_id", "user_id"),
        Index("ix_collective_sessions_created_at", "created_at"),
        Index("ix_collective_sessions_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Task and pattern
    task: Mapped[str] = mapped_column(Text, nullable=False)
    pattern: Mapped[CollectivePatternEnum] = mapped_column(
        Enum(CollectivePatternEnum), nullable=False
    )
    k: Mapped[int] = mapped_column(Integer, nullable=False)  # Number of specialists

    # Status
    status: Mapped[CollectiveStatusEnum] = mapped_column(
        Enum(CollectiveStatusEnum), default=CollectiveStatusEnum.pending
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Results (stored as JSON)
    proposals: Mapped[list] = mapped_column(JSONB, default=list)  # List of proposal dicts
    verdict: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    specialists_used: Mapped[list] = mapped_column(JSONB, default=list)  # Specialist IDs
    search_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    total_cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    session_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)  # Extra data

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# =============================================================================
# Dataset Generation & Fine-Tuning System
# =============================================================================


class TopicStatus(enum.Enum):
    """Status of a research topic for dataset generation."""
    pending = "pending"
    harvesting = "harvesting"
    extracting = "extracting"
    evaluating = "evaluating"
    mature = "mature"
    finetuning = "finetuning"
    completed = "completed"
    paused = "paused"


class ClaimType(enum.Enum):
    """Classification of extracted claims."""
    finding = "finding"           # Empirical result or discovery
    method = "method"             # Technique, algorithm, or approach
    definition = "definition"     # Concept or term definition
    comparison = "comparison"     # Comparison between approaches/results
    limitation = "limitation"     # Acknowledged limitation or constraint


class SectionType(enum.Enum):
    """Paper section where claim was extracted."""
    abstract = "abstract"
    introduction = "introduction"
    methods = "methods"
    results = "results"
    discussion = "discussion"
    conclusion = "conclusion"
    unknown = "unknown"


class EntryStatus(enum.Enum):
    """Evaluation status for claims and dataset entries."""
    pending = "pending"
    accepted = "accepted"
    refined = "refined"
    rejected = "rejected"


class BatchStatus(enum.Enum):
    """Status of a training batch."""
    pending = "pending"
    generating = "generating"
    completed = "completed"
    failed = "failed"


class ResearchTopic(Base):
    """Research topic for dataset generation and fine-tuning.

    Tracks the lifecycle of a research topic from initial harvesting
    through claim extraction, evaluation, and eventual fine-tuning.
    """

    __tablename__ = "research_topics"
    __table_args__ = (
        Index("ix_research_topics_status", "status"),
        Index("ix_research_topics_maturation", "maturation_score"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    query_terms: Mapped[list] = mapped_column(ARRAY(String), nullable=False)
    categories: Mapped[list] = mapped_column(ARRAY(String), default=list)
    sources: Mapped[list] = mapped_column(ARRAY(String), default=lambda: ["arxiv"])

    # Configuration
    target_papers: Mapped[int] = mapped_column(Integer, default=500)
    target_entries: Mapped[int] = mapped_column(Integer, default=5000)
    min_citations: Mapped[int] = mapped_column(Integer, default=0)
    date_from: Mapped[Optional[datetime]] = mapped_column(DateTime)
    date_to: Mapped[Optional[datetime]] = mapped_column(DateTime)
    auto_finetune: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status and progress
    status: Mapped[TopicStatus] = mapped_column(
        Enum(TopicStatus), default=TopicStatus.pending
    )
    papers_harvested: Mapped[int] = mapped_column(Integer, default=0)
    papers_processed: Mapped[int] = mapped_column(Integer, default=0)
    claims_extracted: Mapped[int] = mapped_column(Integer, default=0)
    claims_accepted: Mapped[int] = mapped_column(Integer, default=0)
    dataset_entries: Mapped[int] = mapped_column(Integer, default=0)

    # Maturation metrics
    maturation_score: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)
    topic_coverage_score: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)
    claim_conflict_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)

    # Configuration and metadata
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    topic_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.utcnow)
    last_harvest_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_evaluation_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    papers: Mapped[List["ResearchPaper"]] = relationship(
        "ResearchPaper",
        secondary="paper_topics",
        back_populates="topics"
    )
    dataset_entry_records: Mapped[List["DatasetEntry"]] = relationship(back_populates="topic")
    training_batches: Mapped[List["TrainingBatch"]] = relationship(back_populates="topic")
    expert_models: Mapped[List["ExpertModel"]] = relationship(back_populates="topic")


class ResearchPaper(Base):
    """Harvested research paper from academic sources.

    Stores paper metadata, content, and processing status.
    Papers can belong to multiple topics via the paper_topics junction table.
    """

    __tablename__ = "research_papers"
    __table_args__ = (
        Index("ix_research_papers_source", "source"),
        Index("ix_research_papers_harvested_at", "harvested_at"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)

    # Source IDs (at least one should be present)
    arxiv_id: Mapped[Optional[str]] = mapped_column(String(50), unique=True)
    semantic_scholar_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    pubmed_id: Mapped[Optional[str]] = mapped_column(String(50), unique=True)
    core_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True)
    doi: Mapped[Optional[str]] = mapped_column(String(255))

    # Content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[Optional[str]] = mapped_column(Text)
    full_text: Mapped[Optional[str]] = mapped_column(Text)
    authors: Mapped[list] = mapped_column(JSONB, default=list)
    published_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    citations_count: Mapped[int] = mapped_column(Integer, default=0)

    # Source and storage
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500))
    pdf_url: Mapped[Optional[str]] = mapped_column(String(500))
    pdf_path: Mapped[Optional[str]] = mapped_column(String(500))

    # Processing status
    text_extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    claims_extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Timestamps
    harvested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    topics: Mapped[List["ResearchTopic"]] = relationship(
        "ResearchTopic",
        secondary="paper_topics",
        back_populates="papers"
    )
    claims: Mapped[List["ExtractedClaim"]] = relationship(back_populates="paper")


class PaperTopic(Base):
    """Junction table for paper-topic many-to-many relationship."""

    __tablename__ = "paper_topics"
    __table_args__ = (
        Index("ix_paper_topics_topic_id", "topic_id"),
    )

    paper_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_papers.id", ondelete="CASCADE"),
        primary_key=True
    )
    topic_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_topics.id", ondelete="CASCADE"),
        primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ExtractedClaim(Base):
    """Claim extracted from a research paper.

    Includes classification, evidence quotes, and evaluation status.
    """

    __tablename__ = "extracted_claims"
    __table_args__ = (
        Index("ix_extracted_claims_paper_id", "paper_id"),
        Index("ix_extracted_claims_type", "claim_type"),
        Index("ix_extracted_claims_fingerprint", "dedupe_fingerprint"),
        Index("ix_extracted_claims_eval_status", "evaluation_status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    paper_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_papers.id", ondelete="CASCADE"),
        nullable=False
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Claim content
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[ClaimType] = mapped_column(Enum(ClaimType), nullable=False)
    section: Mapped[SectionType] = mapped_column(
        Enum(SectionType), default=SectionType.unknown
    )

    # Evidence
    evidence_quotes: Mapped[list] = mapped_column(JSONB, nullable=False)
    evidence_positions: Mapped[list] = mapped_column(JSONB, default=list)
    citations: Mapped[list] = mapped_column(JSONB, default=list)

    # Scores
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)
    provenance_score: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)
    entailment_score: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)
    novelty_score: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)

    # Embedding and deduplication
    embedding_id: Mapped[Optional[str]] = mapped_column(String(100))
    dedupe_fingerprint: Mapped[Optional[str]] = mapped_column(String(32))

    # Evaluation
    evaluation_status: Mapped[EntryStatus] = mapped_column(
        Enum(EntryStatus), default=EntryStatus.pending
    )
    evaluation_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    paper: Mapped["ResearchPaper"] = relationship(back_populates="claims")


class DatasetEntry(Base):
    """Alpaca-format training dataset entry.

    Generated from extracted claims for fine-tuning.
    """

    __tablename__ = "dataset_entries"
    __table_args__ = (
        Index("ix_dataset_entries_topic_id", "topic_id"),
        Index("ix_dataset_entries_status", "evaluation_status"),
        Index("ix_dataset_entries_quality", "quality_score"),
        Index("ix_dataset_entries_batch_id", "batch_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_topics.id", ondelete="CASCADE"),
        nullable=False
    )

    # Alpaca format fields
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    input: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, nullable=False)

    # Provenance
    source_paper_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    source_claim_ids: Mapped[list] = mapped_column(JSONB, nullable=False)

    # Quality
    quality_score: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)
    evaluation_status: Mapped[EntryStatus] = mapped_column(
        Enum(EntryStatus), default=EntryStatus.pending
    )
    evaluation_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Batch tracking
    batch_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False))

    # Timestamps
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    topic: Mapped["ResearchTopic"] = relationship(back_populates="dataset_entry_records")


class TrainingBatch(Base):
    """Training batch export for fine-tuning.

    Tracks batches of dataset entries exported for training.
    """

    __tablename__ = "training_batches"
    __table_args__ = (
        Index("ix_training_batches_topic_id", "topic_id"),
        Index("ix_training_batches_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    topic_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_topics.id", ondelete="CASCADE"),
        nullable=False
    )

    # Batch info
    batch_number: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    file_format: Mapped[str] = mapped_column(String(20), default="alpaca_json")
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)

    # Status
    status: Mapped[BatchStatus] = mapped_column(
        Enum(BatchStatus), default=BatchStatus.pending
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Quality metrics
    avg_quality_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4))
    accepted_count: Mapped[Optional[int]] = mapped_column(Integer)
    rejected_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    topic: Mapped["ResearchTopic"] = relationship(back_populates="training_batches")


class ExpertModel(Base):
    """Fine-tuned expert model registry.

    Tracks expert models created from research topic datasets.
    """

    __tablename__ = "expert_models"
    __table_args__ = (
        Index("ix_expert_models_topic_id", "topic_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    topic_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_topics.id", ondelete="SET NULL")
    )
    topic_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Model info
    base_model: Mapped[str] = mapped_column(String(255), nullable=False)
    adapter_path: Mapped[Optional[str]] = mapped_column(String(500))
    gguf_path: Mapped[Optional[str]] = mapped_column(String(500))

    # Training info
    training_samples: Mapped[int] = mapped_column(Integer, nullable=False)
    training_epochs: Mapped[int] = mapped_column(Integer, nullable=False)
    training_loss: Mapped[Optional[float]] = mapped_column(Numeric(8, 6))
    validation_loss: Mapped[Optional[float]] = mapped_column(Numeric(8, 6))

    # Training config and metrics
    training_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_in_kitt: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.utcnow)

    # Relationships
    topic: Mapped[Optional["ResearchTopic"]] = relationship(back_populates="expert_models")


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
    "DiscoveryMethod",
    "DiscoveredDeviceType",
    "ScanStatus",
    "FailureReason",  # Phase 4
    "InventoryStatus",  # Phase 4
    "QueueStatus",  # Phase 4
    # Models
    "User",
    "Zone",
    "ZonePresence",
    "Device",
    "DeviceCommand",
    "TelemetryEvent",
    "ConversationSession",
    "ConversationRole",
    "ConversationMessage",
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
    "GoalOutcome",
    "Material",  # Phase 4
    "InventoryItem",  # Phase 4
    "PrintOutcome",  # Phase 4
    "QueuedPrint",  # Phase 4
    "DiscoveredDevice",
    "DiscoveryScan",
    "AutonomousSchedule",
    "JobExecutionHistory",
    "BudgetForecast",
    # Collective meta-agent
    "CollectivePatternEnum",
    "CollectiveStatusEnum",
    "CollectiveSessionRecord",
    # Dataset Generation & Fine-Tuning
    "TopicStatus",
    "ClaimType",
    "SectionType",
    "EntryStatus",
    "BatchStatus",
    "ResearchTopic",
    "ResearchPaper",
    "PaperTopic",
    "ExtractedClaim",
    "DatasetEntry",
    "TrainingBatch",
    "ExpertModel",
]
