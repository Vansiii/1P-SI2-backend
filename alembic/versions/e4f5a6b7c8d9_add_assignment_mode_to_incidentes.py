"""add_assignment_mode_to_incidentes

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-05-27

Adds assignment_mode column to incidentes for CU27 manual/auto selection flow.
- auto: system assigns automatically (existing behavior)
- manual: client selects workshop from compatible list
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('incidentes',
        sa.Column('assignment_mode', sa.String(20), nullable=False, server_default='auto')
    )
    op.create_index('idx_incidentes_assignment_mode', 'incidentes', ['assignment_mode'])


def downgrade() -> None:
    op.drop_index('idx_incidentes_assignment_mode', table_name='incidentes')
    op.drop_column('incidentes', 'assignment_mode')
