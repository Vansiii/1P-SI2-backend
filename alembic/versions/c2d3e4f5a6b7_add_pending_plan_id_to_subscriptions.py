"""add_pending_plan_id_to_subscriptions

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-26

Adds pending_plan_id FK to tenant_subscriptions for scheduled downgrades.
No data migration needed — new column defaults to NULL.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tenant_subscriptions',
        sa.Column(
            'pending_plan_id',
            sa.Integer(),
            sa.ForeignKey('subscription_plans.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('tenant_subscriptions', 'pending_plan_id')
