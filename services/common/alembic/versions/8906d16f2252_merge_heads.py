"""merge heads

Revision ID: 8906d16f2252
Revises: 001, db9a62569b46
Create Date: 2025-11-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8906d16f2252'
down_revision: Union[str, Sequence[str], None] = ('001', 'db9a62569b46')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge two heads - no schema changes needed."""
    pass


def downgrade() -> None:
    """Downgrade merge - no schema changes needed."""
    pass
