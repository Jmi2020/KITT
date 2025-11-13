"""add_outcome_tracking_for_phase3

Revision ID: 691659ea
Revises: 8906d16f2252
Create Date: 2025-11-13

Phase 3: Learning "The Reflection"
- Add goal_outcomes table for tracking goal effectiveness
- Enhance goals table with effectiveness scoring
- Enhance projects table with actual cost/duration tracking
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = '691659ea'
down_revision = '8906d16f2252'
branch_labels = None
depends_on = None


def upgrade():
    """Apply Phase 3 outcome tracking schema changes."""
    # Create goal_outcomes table
    op.create_table(
        'goal_outcomes',
        sa.Column('id', UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column('goal_id', UUID(as_uuid=False), sa.ForeignKey('goals.id'), nullable=False),

        # Measurement window
        sa.Column('baseline_date', sa.DateTime, nullable=False),
        sa.Column('measurement_date', sa.DateTime, nullable=False),

        # Baseline metrics (before goal execution)
        sa.Column('baseline_metrics', JSONB, nullable=False),

        # Post-execution metrics
        sa.Column('outcome_metrics', JSONB, nullable=False),

        # Effectiveness scoring (0-100)
        sa.Column('impact_score', sa.Numeric(5, 2)),
        sa.Column('roi_score', sa.Numeric(5, 2)),
        sa.Column('adoption_score', sa.Numeric(5, 2)),
        sa.Column('quality_score', sa.Numeric(5, 2)),
        sa.Column('effectiveness_score', sa.Numeric(5, 2)),  # Weighted average

        # Metadata
        sa.Column('measurement_method', sa.String(50)),  # 'kb_usage', 'failure_rate', 'cost_savings'
        sa.Column('notes', sa.Text),
        sa.Column('measured_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('measured_by', sa.String(100), server_default='system-autonomous'),

        sa.UniqueConstraint('goal_id', name='uq_goal_outcomes_goal_id')
    )

    # Create indexes for performance
    op.create_index(
        'idx_goal_outcomes_effectiveness',
        'goal_outcomes',
        ['effectiveness_score'],
        postgresql_using='btree'
    )

    op.create_index(
        'idx_goal_outcomes_goal_id',
        'goal_outcomes',
        ['goal_id'],
        postgresql_using='btree'
    )

    # Enhance goals table with effectiveness tracking
    op.add_column('goals', sa.Column('effectiveness_score', sa.Numeric(5, 2)))
    op.add_column('goals', sa.Column('outcome_measured_at', sa.DateTime))
    op.add_column('goals', sa.Column('learn_from', sa.Boolean, server_default='true'))
    op.add_column('goals', sa.Column('baseline_captured', sa.Boolean, server_default='false'))
    op.add_column('goals', sa.Column('baseline_captured_at', sa.DateTime))

    # Enhance projects table with actual tracking
    op.add_column('projects', sa.Column('actual_cost_usd', sa.Numeric(12, 6)))
    op.add_column('projects', sa.Column('actual_duration_hours', sa.Integer))
    op.add_column('projects', sa.Column('completed_at', sa.DateTime))


def downgrade():
    """Rollback Phase 3 outcome tracking schema changes."""
    # Drop indexes
    op.drop_index('idx_goal_outcomes_effectiveness', table_name='goal_outcomes')
    op.drop_index('idx_goal_outcomes_goal_id', table_name='goal_outcomes')

    # Drop goal_outcomes table
    op.drop_table('goal_outcomes')

    # Remove columns from goals table
    op.drop_column('goals', 'effectiveness_score')
    op.drop_column('goals', 'outcome_measured_at')
    op.drop_column('goals', 'learn_from')
    op.drop_column('goals', 'baseline_captured')
    op.drop_column('goals', 'baseline_captured_at')

    # Remove columns from projects table
    op.drop_column('projects', 'actual_cost_usd')
    op.drop_column('projects', 'actual_duration_hours')
    op.drop_column('projects', 'completed_at')
