"""Initial database schema with all KITTY models.

Revision ID: 001
Revises:
Create Date: 2025-11-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all KITTY database tables."""

    # Users
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('display_name', sa.String(length=120), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('roles', postgresql.JSONB(), nullable=False),
        sa.Column('tailscale_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Zones
    op.create_table(
        'zones',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('hazard_level', sa.Enum('low', 'medium', 'high', name='hazardlevel'), nullable=False),
        sa.Column('requires_ppe', sa.Boolean(), nullable=False),
        sa.Column('unifi_door_ids', postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Zone Presence
    op.create_table(
        'zone_presence',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('zone_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('status', sa.Enum('present', 'unknown', 'vacated', name='telemetrystatus'), nullable=False),
        sa.Column('observed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['zone_id'], ['zones.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Devices
    op.create_table(
        'devices',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('external_id', sa.String(length=255), nullable=False),
        sa.Column('kind', sa.Enum('printer', 'camera', 'light', 'door', 'power', 'sensor', name='devicekind'), nullable=False),
        sa.Column('zone_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('capabilities', postgresql.JSONB(), nullable=False),
        sa.Column('online_state', sa.String(length=32), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['zone_id'], ['zones.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id')
    )

    # Conversation Sessions
    op.create_table(
        'conversation_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('context_key', sa.String(length=255), nullable=False),
        sa.Column('state', postgresql.JSONB(), nullable=False),
        sa.Column('active_participants', postgresql.JSONB(), nullable=False),
        sa.Column('last_message_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Safety Events
    op.create_table(
        'safety_events',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('event_type', sa.Enum('hazard_request', 'unlock', 'power_enable', 'override', name='safetyeventtype'), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('zone_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('initiated_by', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('approved_by', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('signature', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'approved', 'denied', name='safetyeventstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('evidence_key', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.ForeignKeyConstraint(['zone_id'], ['zones.id']),
        sa.ForeignKeyConstraint(['initiated_by'], ['users.id']),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Device Commands
    op.create_table(
        'device_commands',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('intent', sa.String(length=120), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('requested_by', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('status', sa.Enum('pending', 'sent', 'acked', 'failed', name='commandstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('ack_at', sa.DateTime(), nullable=True),
        sa.Column('safety_event_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation_sessions.id']),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id']),
        sa.ForeignKeyConstraint(['safety_event_id'], ['safety_events.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Telemetry Events
    op.create_table(
        'telemetry_events',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('topic', sa.String(length=255), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Routing Decisions
    op.create_table(
        'routing_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('request_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('selected_tier', sa.Enum('local', 'mcp', 'frontier', name='routingtier'), nullable=False),
        sa.Column('confidence', sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('cost_estimate', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('escalation_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation_sessions.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # CAD Jobs
    op.create_table(
        'cad_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('policy_mode', sa.Enum('online', 'offline', 'auto', name='cadpolicy'), nullable=False),
        sa.Column('status', sa.Enum('queued', 'running', 'completed', 'failed', name='cadstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation_sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # CAD Artifacts
    op.create_table(
        'cad_artifacts',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('cad_job_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('provider', sa.Enum('zoo', 'tripo', 'cadquery', 'freecad', 'triposr', 'instantmesh', name='cadprovider'), nullable=False),
        sa.Column('artifact_key', sa.String(length=255), nullable=False),
        sa.Column('artifact_type', sa.String(length=32), nullable=False),
        sa.Column('artifact_metadata', postgresql.JSONB(), nullable=False),
        sa.Column('quality_score', sa.Numeric(precision=3, scale=2), nullable=True),
        sa.ForeignKeyConstraint(['cad_job_id'], ['cad_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('artifact_key')
    )

    # Fabrication Jobs
    op.create_table(
        'fabrication_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('cad_artifact_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('gcode_path', sa.String(length=255), nullable=False),
        sa.Column('status', sa.Enum('preparing', 'printing', 'paused', 'completed', 'failed', 'aborted', name='fabricationstatus'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('requested_by', postgresql.UUID(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.ForeignKeyConstraint(['cad_artifact_id'], ['cad_artifacts.id']),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Print Monitor Events
    op.create_table(
        'print_monitor_events',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('fabrication_job_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('confidence', sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column('snapshot_key', sa.String(length=255), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fabrication_job_id'], ['fabrication_jobs.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Access Policies
    op.create_table(
        'access_policies',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('zone_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('required_roles', postgresql.JSONB(), nullable=False),
        sa.Column('requires_dual_confirm', sa.Boolean(), nullable=False),
        sa.Column('requires_presence', sa.Boolean(), nullable=False),
        sa.Column('pqe_checks', postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['zone_id'], ['zones.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Notifications
    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('channel', sa.String(length=32), nullable=False),
        sa.Column('recipient', sa.String(length=255), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('related_job_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Conversation Projects
    op.create_table(
        'conversation_projects',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('artifacts', postgresql.JSONB(), nullable=False),
        sa.Column('project_metadata', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation_sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Goals
    op.create_table(
        'goals',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('goal_type', sa.Enum('research', 'fabrication', 'improvement', 'optimization', name='goaltype'), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('estimated_budget', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('estimated_duration_hours', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('identified', 'approved', 'rejected', 'completed', name='goalstatus'), nullable=False),
        sa.Column('identified_at', sa.DateTime(), nullable=False),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('approved_by', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('goal_metadata', postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Projects
    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('goal_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('proposed', 'approved', 'in_progress', 'completed', 'cancelled', name='projectstatus'), nullable=False),
        sa.Column('budget_allocated', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('budget_spent', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('project_metadata', postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['goal_id'], ['goals.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Tasks
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'in_progress', 'completed', 'failed', 'blocked', name='taskstatus'), nullable=False),
        sa.Column('priority', sa.Enum('low', 'medium', 'high', 'critical', name='taskpriority'), nullable=False),
        sa.Column('depends_on', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('scheduled_for', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result', postgresql.JSONB(), nullable=False),
        sa.Column('task_metadata', postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['depends_on'], ['tasks.id']),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Discovered Devices (Network Discovery Service)
    op.create_table(
        'discovered_devices',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('discovered_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('discovery_method', sa.String(length=32), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('mac_address', sa.String(length=17), nullable=True),
        sa.Column('hostname', sa.String(length=255), nullable=True),
        sa.Column('device_type', sa.String(length=32), nullable=False),
        sa.Column('manufacturer', sa.String(length=120), nullable=True),
        sa.Column('model', sa.String(length=120), nullable=True),
        sa.Column('serial_number', sa.String(length=255), nullable=True),
        sa.Column('firmware_version', sa.String(length=120), nullable=True),
        sa.Column('services', postgresql.JSONB(), nullable=False),
        sa.Column('capabilities', postgresql.JSONB(), nullable=False),
        sa.Column('approved', sa.Boolean(), nullable=False),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('approved_by', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_online', sa.Boolean(), nullable=False),
        sa.Column('confidence_score', sa.Numeric(precision=3, scale=2), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Discovery Scans
    op.create_table(
        'discovery_scans',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('methods', postgresql.JSONB(), nullable=False),
        sa.Column('devices_found', sa.Integer(), nullable=False),
        sa.Column('errors', postgresql.JSONB(), nullable=False),
        sa.Column('triggered_by', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Drop all KITTY database tables."""
    op.drop_table('discovery_scans')
    op.drop_table('discovered_devices')
    op.drop_table('tasks')
    op.drop_table('projects')
    op.drop_table('goals')
    op.drop_table('conversation_projects')
    op.drop_table('notifications')
    op.drop_table('access_policies')
    op.drop_table('print_monitor_events')
    op.drop_table('fabrication_jobs')
    op.drop_table('cad_artifacts')
    op.drop_table('cad_jobs')
    op.drop_table('routing_decisions')
    op.drop_table('telemetry_events')
    op.drop_table('device_commands')
    op.drop_table('safety_events')
    op.drop_table('conversation_sessions')
    op.drop_table('devices')
    op.drop_table('zone_presence')
    op.drop_table('zones')
    op.drop_table('users')
