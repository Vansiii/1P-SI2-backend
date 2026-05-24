"""add ws_immediate_sent column to outbox_events

Revision ID: add_ws_immediate_sent
Revises: add_service_ratings
Create Date: 2026-05-20 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_ws_immediate_sent'
down_revision: Union[str, None] = 'add_service_ratings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'outbox_events',
        sa.Column(
            'ws_immediate_sent',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
            comment="Whether immediate WebSocket was already sent by EventPublisher"
        )
    )


def downgrade() -> None:
    op.drop_column('outbox_events', 'ws_immediate_sent')
