"""merge tenant and timeout branches

Revision ID: 95dd24b258e1
Revises: c2d3e4f5a6b7, i4j5k6l7m8n0
Create Date: 2026-05-26 19:05:17.262912

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95dd24b258e1'
down_revision: Union[str, Sequence[str], None] = ('c2d3e4f5a6b7', 'i4j5k6l7m8n0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
