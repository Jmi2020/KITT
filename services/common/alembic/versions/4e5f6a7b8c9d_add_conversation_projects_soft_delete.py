"""Add soft delete and indexes to conversation_projects

Revision ID: 4e5f6a7b8c9d
Revises: c1d2e3f4
Create Date: 2025-11-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4e5f6a7b8c9d"
down_revision = "c1d2e3f4_autonomy_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversation_projects", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_conversation_projects_conversation_id_updated_at",
        "conversation_projects",
        ["conversation_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_projects_updated_at",
        "conversation_projects",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_projects_artifacts_gin",
        "conversation_projects",
        ["artifacts"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_projects_artifacts_gin", table_name="conversation_projects")
    op.drop_index("ix_conversation_projects_updated_at", table_name="conversation_projects")
    op.drop_index("ix_conversation_projects_conversation_id_updated_at", table_name="conversation_projects")
    op.drop_column("conversation_projects", "deleted_at")
