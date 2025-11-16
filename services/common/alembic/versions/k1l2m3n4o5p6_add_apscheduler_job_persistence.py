"""add apscheduler job persistence

Revision ID: k1l2m3n4o5p6
Revises: f7g8h9i0j1k2
Create Date: 2025-01-16 12:00:00.000000

APScheduler requires a jobs table to persist scheduled jobs across restarts.
This prevents job loss when the brain service restarts.

Table schema matches APScheduler's SQLAlchemyJobStore requirements.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, None] = 'f7g8h9i0j1k2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create apscheduler_jobs table for persistent job storage.

    APScheduler's SQLAlchemyJobStore requires this exact schema:
    - id: Job identifier (primary key)
    - next_run_time: When the job should next execute (indexed for performance)
    - job_state: Pickled job state (trigger, function, args, etc.)
    """
    op.create_table(
        'apscheduler_jobs',
        sa.Column('id', sa.String(191), primary_key=True, nullable=False),
        sa.Column('next_run_time', sa.Float(25), nullable=True, index=True),
        sa.Column('job_state', postgresql.BYTEA(), nullable=False),
    )

    # Index on next_run_time for efficient job scheduling queries
    op.create_index(
        'ix_apscheduler_jobs_next_run_time',
        'apscheduler_jobs',
        ['next_run_time'],
        unique=False
    )


def downgrade() -> None:
    """Remove apscheduler_jobs table."""
    op.drop_index('ix_apscheduler_jobs_next_run_time', table_name='apscheduler_jobs')
    op.drop_table('apscheduler_jobs')
