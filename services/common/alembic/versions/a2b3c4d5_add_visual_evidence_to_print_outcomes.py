"""add_visual_evidence_to_print_outcomes

Revision ID: a2b3c4d5
Revises: 6e45f2a1
Create Date: 2025-11-14

Phase 4.2: Computer Vision Print Monitoring Integration
- Add visual evidence fields to print_outcomes table (snapshot URLs, video URL)
- Add human feedback workflow fields (review status, timestamps, reviewer)
- Add future autonomous detection fields (anomaly detection, confidence, auto-stop)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'a2b3c4d5'
down_revision = '6e45f2a1'
branch_labels = None
depends_on = None


def upgrade():
    """Add visual evidence and human feedback fields to print_outcomes."""

    # Visual Evidence (Phase 1: Human-in-Loop)
    op.add_column('print_outcomes', sa.Column('initial_snapshot_url', sa.String(500), nullable=True))
    op.add_column('print_outcomes', sa.Column('final_snapshot_url', sa.String(500), nullable=True))
    op.add_column('print_outcomes', sa.Column('snapshot_urls', JSONB, nullable=False, server_default='[]'))
    op.add_column('print_outcomes', sa.Column('video_url', sa.String(500), nullable=True))

    # Human Feedback (Phase 1: Human-in-Loop)
    op.add_column('print_outcomes', sa.Column('human_reviewed', sa.Boolean, nullable=False, server_default='false'))
    op.add_column('print_outcomes', sa.Column('review_requested_at', sa.DateTime, nullable=True))
    op.add_column('print_outcomes', sa.Column('reviewed_at', sa.DateTime, nullable=True))
    op.add_column('print_outcomes', sa.Column('reviewed_by', sa.String(100), nullable=True))

    # Visual Characteristics (Phase 2+: Future Autonomous Detection)
    op.add_column('print_outcomes', sa.Column('visual_defects', JSONB, nullable=False, server_default='[]'))
    op.add_column('print_outcomes', sa.Column('anomaly_detected', sa.Boolean, nullable=False, server_default='false'))
    op.add_column('print_outcomes', sa.Column('anomaly_confidence', sa.Numeric(3, 2), nullable=True))
    op.add_column('print_outcomes', sa.Column('auto_stopped', sa.Boolean, nullable=False, server_default='false'))

    # Create indexes for common queries
    op.create_index(
        'ix_print_outcomes_human_reviewed',
        'print_outcomes',
        ['human_reviewed'],
        postgresql_where=sa.text('human_reviewed = false')
    )
    op.create_index(
        'ix_print_outcomes_anomaly_detected',
        'print_outcomes',
        ['anomaly_detected'],
        postgresql_where=sa.text('anomaly_detected = true')
    )


def downgrade():
    """Remove visual evidence and human feedback fields from print_outcomes."""

    # Drop indexes
    op.drop_index('ix_print_outcomes_anomaly_detected', table_name='print_outcomes')
    op.drop_index('ix_print_outcomes_human_reviewed', table_name='print_outcomes')

    # Drop columns (reverse order)
    op.drop_column('print_outcomes', 'auto_stopped')
    op.drop_column('print_outcomes', 'anomaly_confidence')
    op.drop_column('print_outcomes', 'anomaly_detected')
    op.drop_column('print_outcomes', 'visual_defects')

    op.drop_column('print_outcomes', 'reviewed_by')
    op.drop_column('print_outcomes', 'reviewed_at')
    op.drop_column('print_outcomes', 'review_requested_at')
    op.drop_column('print_outcomes', 'human_reviewed')

    op.drop_column('print_outcomes', 'video_url')
    op.drop_column('print_outcomes', 'snapshot_urls')
    op.drop_column('print_outcomes', 'final_snapshot_url')
    op.drop_column('print_outcomes', 'initial_snapshot_url')
