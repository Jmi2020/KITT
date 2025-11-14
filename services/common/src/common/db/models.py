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

    # Relationships
    goal: Mapped[Optional[Goal]] = relationship(back_populates="print_outcomes")
    material: Mapped[Material] = relationship(back_populates="print_outcomes")


class QueuedPrint(Base):
    """Phase 4: Print queue with optimization metadata.

    Tracks queued print jobs with priority scoring, deadline management,
    and optimization reasoning.
    """

    __tablename__ = "print_queue"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    stl_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Assignment
    printer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), nullable=False)
    spool_id: Mapped[Optional[str]] = mapped_column(ForeignKey("inventory.id"))

    # Scheduling
    status: Mapped[QueueStatus] = mapped_column(Enum(QueueStatus), nullable=False)
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

    # Timestamps
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    material: Mapped[Material] = relationship(back_populates="queued_prints")
    spool: Mapped[Optional[InventoryItem]] = relationship(back_populates="queued_prints")


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
]
