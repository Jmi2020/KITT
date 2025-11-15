"""add_phase4_fabrication_intelligence

Revision ID: 6e45f2a1
Revises: 691659ea
Create Date: 2025-11-14

Phase 4: Fabrication Intelligence "Making Things"
- Add materials table for filament catalog
- Add inventory table for spool tracking
- Add print_outcomes table for learning from print results
- Add print_queue table for queue optimization
- Add procurement goal type for autonomous material procurement
- Add new enums: FailureReason, InventoryStatus, QueueStatus
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID, ENUM


# revision identifiers, used by Alembic.
revision = '6e45f2a1'
down_revision = '691659ea'
branch_labels = None
depends_on = None


def upgrade():
    """Apply Phase 4 fabrication intelligence schema changes."""

    # Add new enum types
    failure_reason_enum = ENUM(
        'first_layer_adhesion', 'warping', 'stringing', 'spaghetti',
        'nozzle_clog', 'filament_runout', 'layer_shift', 'overheating',
        'support_failure', 'user_cancelled', 'power_failure', 'other',
        name='failurereason'
    )
    failure_reason_enum.create(op.get_bind(), checkfirst=True)

    inventory_status_enum = ENUM(
        'available', 'in_use', 'depleted', 'reserved',
        name='inventorystatus'
    )
    inventory_status_enum.create(op.get_bind(), checkfirst=True)

    queue_status_enum = ENUM(
        'queued', 'printing', 'completed', 'failed', 'cancelled',
        name='queuestatus'
    )
    queue_status_enum.create(op.get_bind(), checkfirst=True)

    # Add 'procurement' to GoalType enum
    # Note: In PostgreSQL, adding enum values requires special handling
    op.execute("ALTER TYPE goaltype ADD VALUE IF NOT EXISTS 'procurement'")

    # Create materials table
    op.create_table(
        'materials',
        sa.Column('id', sa.String(100), primary_key=True, nullable=False),
        sa.Column('material_type', sa.String(50), nullable=False),
        sa.Column('color', sa.String(50), nullable=False),
        sa.Column('manufacturer', sa.String(120), nullable=False),
        sa.Column('cost_per_kg_usd', sa.Numeric(10, 2), nullable=False),
        sa.Column('density_g_cm3', sa.Numeric(4, 2), nullable=False),

        # Temperature ranges
        sa.Column('nozzle_temp_min_c', sa.Integer, nullable=False),
        sa.Column('nozzle_temp_max_c', sa.Integer, nullable=False),
        sa.Column('bed_temp_min_c', sa.Integer, nullable=False),
        sa.Column('bed_temp_max_c', sa.Integer, nullable=False),

        # Material properties
        sa.Column('properties', JSONB, server_default='{}'),
        sa.Column('sustainability_score', sa.Integer),

        # Metadata
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.text('CURRENT_TIMESTAMP'))
    )

    # Create inventory table
    op.create_table(
        'inventory',
        sa.Column('id', sa.String(100), primary_key=True, nullable=False),
        sa.Column('material_id', sa.String(100), sa.ForeignKey('materials.id'), nullable=False),
        sa.Column('location', sa.String(120)),
        sa.Column('purchase_date', sa.DateTime, nullable=False),
        sa.Column('initial_weight_grams', sa.Numeric(10, 2), nullable=False),
        sa.Column('current_weight_grams', sa.Numeric(10, 2), nullable=False),
        sa.Column('status', ENUM(name='inventorystatus', create_type=False), nullable=False),
        sa.Column('notes', sa.Text),

        # Metadata
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.text('CURRENT_TIMESTAMP'))
    )

    # Create print_outcomes table
    op.create_table(
        'print_outcomes',
        sa.Column('id', UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('job_id', sa.String(100), nullable=False, unique=True),
        sa.Column('goal_id', UUID(as_uuid=False), sa.ForeignKey('goals.id')),
        sa.Column('printer_id', sa.String(100), nullable=False),
        sa.Column('material_id', sa.String(100), sa.ForeignKey('materials.id'), nullable=False),

        # Outcome
        sa.Column('success', sa.Boolean, nullable=False),
        sa.Column('failure_reason', ENUM(name='failurereason', create_type=False)),
        sa.Column('quality_score', sa.Numeric(5, 2), nullable=False),

        # Actuals
        sa.Column('actual_duration_hours', sa.Numeric(6, 2), nullable=False),
        sa.Column('actual_cost_usd', sa.Numeric(10, 2), nullable=False),
        sa.Column('material_used_grams', sa.Numeric(10, 2), nullable=False),

        # Print Settings
        sa.Column('print_settings', JSONB, nullable=False),

        # Quality Metrics (if available)
        sa.Column('quality_metrics', JSONB, server_default='{}'),

        # Timestamps
        sa.Column('started_at', sa.DateTime, nullable=False),
        sa.Column('completed_at', sa.DateTime, nullable=False),
        sa.Column('measured_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.UniqueConstraint('job_id', name='uq_print_outcomes_job_id')
    )

    # Create print_queue table
    op.create_table(
        'print_queue',
        sa.Column('id', UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('job_id', sa.String(100), nullable=False, unique=True),
        sa.Column('stl_path', sa.String(500), nullable=False),

        # Assignment
        sa.Column('printer_id', sa.String(100), nullable=False),
        sa.Column('material_id', sa.String(100), sa.ForeignKey('materials.id'), nullable=False),
        sa.Column('spool_id', sa.String(100), sa.ForeignKey('inventory.id')),

        # Scheduling
        sa.Column('status', ENUM(name='queuestatus', create_type=False), nullable=False),
        sa.Column('priority', sa.Integer, nullable=False),
        sa.Column('deadline', sa.DateTime),
        sa.Column('scheduled_start', sa.DateTime),

        # Estimates
        sa.Column('estimated_duration_hours', sa.Numeric(6, 2), nullable=False),
        sa.Column('estimated_material_grams', sa.Numeric(10, 2), nullable=False),
        sa.Column('estimated_cost_usd', sa.Numeric(10, 2), nullable=False),
        sa.Column('success_probability', sa.Numeric(5, 2)),

        # Optimization Metadata
        sa.Column('priority_score', sa.Numeric(10, 4)),
        sa.Column('optimization_reasoning', sa.Text),

        # Timestamps
        sa.Column('queued_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('started_at', sa.DateTime),
        sa.Column('completed_at', sa.DateTime),

        sa.UniqueConstraint('job_id', name='uq_print_queue_job_id')
    )

    # Create indexes for performance
    # Materials indexes
    op.create_index(
        'idx_materials_type',
        'materials',
        ['material_type'],
        postgresql_using='btree'
    )

    # Inventory indexes
    op.create_index(
        'idx_inventory_material_id',
        'inventory',
        ['material_id'],
        postgresql_using='btree'
    )

    op.create_index(
        'idx_inventory_status',
        'inventory',
        ['status'],
        postgresql_using='btree'
    )

    op.create_index(
        'idx_inventory_weight',
        'inventory',
        ['current_weight_grams'],
        postgresql_using='btree'
    )

    # Print outcomes indexes
    op.create_index(
        'idx_print_outcomes_material_id',
        'print_outcomes',
        ['material_id'],
        postgresql_using='btree'
    )

    op.create_index(
        'idx_print_outcomes_printer_id',
        'print_outcomes',
        ['printer_id'],
        postgresql_using='btree'
    )

    op.create_index(
        'idx_print_outcomes_success',
        'print_outcomes',
        ['success'],
        postgresql_using='btree'
    )

    op.create_index(
        'idx_print_outcomes_completed_at',
        'print_outcomes',
        ['completed_at'],
        postgresql_using='btree'
    )

    op.create_index(
        'idx_print_outcomes_goal_id',
        'print_outcomes',
        ['goal_id'],
        postgresql_using='btree'
    )

    # Print queue indexes
    op.create_index(
        'idx_print_queue_status',
        'print_queue',
        ['status'],
        postgresql_using='btree'
    )

    op.create_index(
        'idx_print_queue_priority',
        'print_queue',
        ['priority'],
        postgresql_using='btree'
    )

    op.create_index(
        'idx_print_queue_deadline',
        'print_queue',
        ['deadline'],
        postgresql_using='btree'
    )

    op.create_index(
        'idx_print_queue_scheduled_start',
        'print_queue',
        ['scheduled_start'],
        postgresql_using='btree'
    )


def downgrade():
    """Rollback Phase 4 fabrication intelligence schema changes."""

    # Drop indexes
    op.drop_index('idx_materials_type', table_name='materials')
    op.drop_index('idx_inventory_material_id', table_name='inventory')
    op.drop_index('idx_inventory_status', table_name='inventory')
    op.drop_index('idx_inventory_weight', table_name='inventory')
    op.drop_index('idx_print_outcomes_material_id', table_name='print_outcomes')
    op.drop_index('idx_print_outcomes_printer_id', table_name='print_outcomes')
    op.drop_index('idx_print_outcomes_success', table_name='print_outcomes')
    op.drop_index('idx_print_outcomes_completed_at', table_name='print_outcomes')
    op.drop_index('idx_print_outcomes_goal_id', table_name='print_outcomes')
    op.drop_index('idx_print_queue_status', table_name='print_queue')
    op.drop_index('idx_print_queue_priority', table_name='print_queue')
    op.drop_index('idx_print_queue_deadline', table_name='print_queue')
    op.drop_index('idx_print_queue_scheduled_start', table_name='print_queue')

    # Drop tables (in reverse order of dependencies)
    op.drop_table('print_queue')
    op.drop_table('print_outcomes')
    op.drop_table('inventory')
    op.drop_table('materials')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS failurereason")
    op.execute("DROP TYPE IF EXISTS inventorystatus")
    op.execute("DROP TYPE IF EXISTS queuestatus")

    # Note: Cannot easily remove 'procurement' from GoalType enum in PostgreSQL
    # This would require dropping and recreating the enum with all values except 'procurement'
    # For safety, we leave it in place during downgrade
