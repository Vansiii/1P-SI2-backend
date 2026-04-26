"""add cancellation requests table

Revision ID: f2b3c4d5e6f7
Revises: 35383c48189f
Create Date: 2026-04-19 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b3c4d5e6f7'
down_revision: Union[str, None] = '35383c48189f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create cancellation_requests table
    op.create_table(
        'cancellation_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('requested_by', sa.String(length=20), nullable=False),
        sa.Column('requested_by_user_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('response_by_user_id', sa.Integer(), nullable=True),
        sa.Column('response_message', sa.Text(), nullable=True),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'rejected', 'expired')", name='check_cancellation_status_valid'),
        sa.CheckConstraint("requested_by IN ('client', 'workshop')", name='check_requested_by_valid'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidentes.id'], ),
        sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['response_by_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('incident_id')
    )
    op.create_index(op.f('ix_cancellation_requests_incident_id'), 'cancellation_requests', ['incident_id'], unique=False)
    op.create_index(op.f('ix_cancellation_requests_status'), 'cancellation_requests', ['status'], unique=False)
    op.create_index(op.f('ix_cancellation_requests_created_at'), 'cancellation_requests', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cancellation_requests_created_at'), table_name='cancellation_requests')
    op.drop_index(op.f('ix_cancellation_requests_status'), table_name='cancellation_requests')
    op.drop_index(op.f('ix_cancellation_requests_incident_id'), table_name='cancellation_requests')
    op.drop_table('cancellation_requests')
