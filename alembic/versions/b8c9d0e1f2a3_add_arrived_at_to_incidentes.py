"""add_arrived_at_to_incidentes

Revision ID: b8c9d0e1f2a3
Revises: a6b7c8d9e0f1
Create Date: 2026-06-07

Adds arrived_at timestamp column to incidentes table for tracking
when the technician arrives at the incident location.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a6b7c8d9e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'incidentes',
        sa.Column('arrived_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('incidentes', 'arrived_at')
