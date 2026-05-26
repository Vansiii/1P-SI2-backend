"""fix cancellation_requests unique constraint - allow multiple requests per incident

Revision ID: fix_cancellation_uniqueness
Revises: add_ws_immediate_sent
Create Date: 2026-05-24 19:00:00.000000

Previously, incident_id had a UNIQUE constraint meaning only ONE cancellation
request per incident could ever exist. This prevented users from creating a new
request after a previous one was rejected or expired.

This migration:
  1. Drops the global UNIQUE constraint on incident_id
  2. Creates a PARTIAL unique index: only ONE *pending* request per incident
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'fix_cancellation_uniqueness'
down_revision: Union[str, None] = 'add_ws_immediate_sent'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        'ix_cancellation_requests_incident_id',
        'cancellation_requests',
        type_='unique'
    )
    op.create_index(
        'ix_cancellation_requests_incident_id_pending_unique',
        'cancellation_requests',
        ['incident_id'],
        unique=True,
        postgresql_where="status = 'pending'"
    )


def downgrade() -> None:
    op.drop_index(
        'ix_cancellation_requests_incident_id_pending_unique',
        table_name='cancellation_requests',
        postgresql_where="status = 'pending'"
    )
    op.create_unique_constraint(
        'ix_cancellation_requests_incident_id',
        'cancellation_requests',
        ['incident_id']
    )
