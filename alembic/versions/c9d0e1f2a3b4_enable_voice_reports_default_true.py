"""enable_voice_reports_default_true

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-07

Changes enable_voice_reports default to true for all subscription plans.
Voice reports should be available to all workshops by default.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE subscription_plans SET enable_voice_reports = true"
    )
    op.alter_column(
        'subscription_plans', 'enable_voice_reports',
        server_default=sa.text('true')
    )


def downgrade() -> None:
    op.alter_column(
        'subscription_plans', 'enable_voice_reports',
        server_default=sa.text('false')
    )
