"""add autonomous project management models

Revision ID: db9a62569b46
Revises:
Create Date: 2025-01-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'db9a62569b46'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create goal type enum
    goal_type_enum = postgresql.ENUM('research', 'fabrication', 'improvement', 'optimization', name='goaltype')
    goal_type_enum.create(op.get_bind(), checkfirst=True)

    # Create goal status enum
    goal_status_enum = postgresql.ENUM('identified', 'approved', 'rejected', 'completed', name='goalstatus')
    goal_status_enum.create(op.get_bind(), checkfirst=True)

    # Create project status enum
    project_status_enum = postgresql.ENUM('proposed', 'approved', 'in_progress', 'completed', 'cancelled', name='projectstatus')
    project_status_enum.create(op.get_bind(), checkfirst=True)

    # Create task status enum
    task_status_enum = postgresql.ENUM('pending', 'in_progress', 'completed', 'failed', 'blocked', name='taskstatus')
    task_status_enum.create(op.get_bind(), checkfirst=True)

    # Create task priority enum
    task_priority_enum = postgresql.ENUM('low', 'medium', 'high', 'critical', name='taskpriority')
    task_priority_enum.create(op.get_bind(), checkfirst=True)

    # Create goals table
    op.create_table('goals',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('goal_type', goal_type_enum, nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('estimated_budget', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('estimated_duration_hours', sa.Integer(), nullable=True),
        sa.Column('status', goal_status_enum, nullable=False, server_default='identified'),
        sa.Column('identified_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('approved_by', sa.String(), nullable=True),
        sa.Column('goal_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create projects table
    op.create_table('projects',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('goal_id', sa.String(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', project_status_enum, nullable=False, server_default='proposed'),
        sa.Column('budget_allocated', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0.0'),
        sa.Column('budget_spent', sa.Numeric(precision=12, scale=6), nullable=False, server_default='0.0'),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('project_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['goal_id'], ['goals.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create tasks table
    op.create_table('tasks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', task_status_enum, nullable=False, server_default='pending'),
        sa.Column('priority', task_priority_enum, nullable=False, server_default='medium'),
        sa.Column('depends_on', sa.String(), nullable=True),
        sa.Column('assigned_to', sa.String(), nullable=True),
        sa.Column('scheduled_for', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('task_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ),
        sa.ForeignKeyConstraint(['depends_on'], ['tasks.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('tasks')
    op.drop_table('projects')
    op.drop_table('goals')

    # Drop enums
    task_priority_enum = postgresql.ENUM('low', 'medium', 'high', 'critical', name='taskpriority')
    task_priority_enum.drop(op.get_bind(), checkfirst=True)

    task_status_enum = postgresql.ENUM('pending', 'in_progress', 'completed', 'failed', 'blocked', name='taskstatus')
    task_status_enum.drop(op.get_bind(), checkfirst=True)

    project_status_enum = postgresql.ENUM('proposed', 'approved', 'in_progress', 'completed', 'cancelled', name='projectstatus')
    project_status_enum.drop(op.get_bind(), checkfirst=True)

    goal_status_enum = postgresql.ENUM('identified', 'approved', 'rejected', 'completed', name='goalstatus')
    goal_status_enum.drop(op.get_bind(), checkfirst=True)

    goal_type_enum = postgresql.ENUM('research', 'fabrication', 'improvement', 'optimization', name='goaltype')
    goal_type_enum.drop(op.get_bind(), checkfirst=True)
