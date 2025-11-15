"""add conversation history persistence

Revision ID: c5d9e8f1c2b3
Revises: a2b3c4d5
Create Date: 2025-11-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM


# revision identifiers, used by Alembic.
revision = 'c5d9e8f1c2b3'
down_revision = 'a2b3c4d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    role_enum = ENUM('user', 'assistant', 'system', 'tool', name='conversationrole')
    role_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        'conversation_sessions',
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False)
    )
    op.add_column('conversation_sessions', sa.Column('title', sa.String(length=200), nullable=True))
    op.add_column(
        'conversation_sessions',
        sa.Column('message_count', sa.Integer(), server_default='0', nullable=False)
    )
    op.add_column('conversation_sessions', sa.Column('last_user_message', sa.Text(), nullable=True))
    op.add_column('conversation_sessions', sa.Column('last_assistant_message', sa.Text(), nullable=True))

    op.create_table(
        'conversation_messages',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('role', ENUM(name='conversationrole', create_type=False), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('message_metadata', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversation_sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'ix_conversation_messages_conversation_id_created',
        'conversation_messages',
        ['conversation_id', 'created_at']
    )


def downgrade() -> None:
    op.drop_index('ix_conversation_messages_conversation_id_created', table_name='conversation_messages')
    op.drop_table('conversation_messages')

    op.drop_column('conversation_sessions', 'last_assistant_message')
    op.drop_column('conversation_sessions', 'last_user_message')
    op.drop_column('conversation_sessions', 'message_count')
    op.drop_column('conversation_sessions', 'title')
    op.drop_column('conversation_sessions', 'created_at')

    role_enum = ENUM('user', 'assistant', 'system', 'tool', name='conversationrole')
    role_enum.drop(op.get_bind(), checkfirst=True)
