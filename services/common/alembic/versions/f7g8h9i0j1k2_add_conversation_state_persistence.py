"""add conversation state persistence for hazard confirmations

Revision ID: f7g8h9i0j1k2
Revises: c5d9e8f1c2b3
Create Date: 2025-11-16

Adds persistent storage for conversation state including:
- Agent reasoning history
- Pending confirmations for hazard operations
- Conversation metadata

This prevents data loss on brain service restart, which could cause
double-execution of hazardous operations.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f7g8h9i0j1k2'
down_revision = 'c5d9e8f1c2b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add columns for persistent conversation state."""

    # Add user_id to track conversation owner
    op.add_column(
        'conversation_sessions',
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=True)
    )
    op.create_foreign_key(
        'fk_conversation_sessions_user_id',
        'conversation_sessions',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_index(
        'ix_conversation_sessions_user_id',
        'conversation_sessions',
        ['user_id']
    )

    # Add agent history (list of AgentStep objects)
    op.add_column(
        'conversation_sessions',
        sa.Column(
            'agent_history',
            postgresql.JSONB(),
            server_default='[]',
            nullable=False,
            comment='Ordered list of agent reasoning steps'
        )
    )

    # Add pending confirmation (critical for hazard operations)
    op.add_column(
        'conversation_sessions',
        sa.Column(
            'pending_confirmation',
            postgresql.JSONB(),
            nullable=True,
            comment='Pending confirmation for hazardous operation (tool_name, args, phrase, etc.)'
        )
    )

    # Add conversation metadata
    op.add_column(
        'conversation_sessions',
        sa.Column(
            'conversation_metadata',
            postgresql.JSONB(),
            server_default='{}',
            nullable=False,
            comment='Custom metadata for conversation (tags, flags, etc.)'
        )
    )

    # Add updated_at timestamp
    op.add_column(
        'conversation_sessions',
        sa.Column(
            'updated_at',
            sa.DateTime(),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
            comment='Last update timestamp'
        )
    )

    # Create index for finding conversations with pending confirmations
    op.create_index(
        'ix_conversation_sessions_pending_confirmation',
        'conversation_sessions',
        ['pending_confirmation'],
        postgresql_where=sa.text('pending_confirmation IS NOT NULL')
    )

    # Create index for cleanup queries
    op.create_index(
        'ix_conversation_sessions_updated_at',
        'conversation_sessions',
        ['updated_at']
    )


def downgrade() -> None:
    """Remove conversation state persistence columns."""

    op.drop_index('ix_conversation_sessions_updated_at', table_name='conversation_sessions')
    op.drop_index('ix_conversation_sessions_pending_confirmation', table_name='conversation_sessions')
    op.drop_column('conversation_sessions', 'updated_at')
    op.drop_column('conversation_sessions', 'conversation_metadata')
    op.drop_column('conversation_sessions', 'pending_confirmation')
    op.drop_column('conversation_sessions', 'agent_history')

    op.drop_index('ix_conversation_sessions_user_id', table_name='conversation_sessions')
    op.drop_constraint('fk_conversation_sessions_user_id', 'conversation_sessions', type_='foreignkey')
    op.drop_column('conversation_sessions', 'user_id')
