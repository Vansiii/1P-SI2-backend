"""add_arrived_at_to_tracking_sessions

Revision ID: 5450761a33ab
Revises: ed64a62f1f1b
Create Date: 2026-04-18 06:00:16.465517

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5450761a33ab'
down_revision: Union[str, Sequence[str], None] = 'ed64a62f1f1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add arrived_at column to tracking_sessions
    op.add_column(
        'tracking_sessions',
        sa.Column('arrived_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove arrived_at column from tracking_sessions
    op.drop_column('tracking_sessions', 'arrived_at')
