"""add_sync_operations_table

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-04

Creates sync_operations table for offline queue idempotency and audit trail.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sync_operations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_operation_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('operation_type', sa.String(length=50), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'pending', 'processing', 'completed', 'failed',
                'conflict', 'duplicate', 'expired',
                name='syncoperationstatus'
            ),
            nullable=False,
            server_default='pending',
        ),
        sa.Column('request_payload', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('response_payload', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('conflict_code', sa.String(length=50), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('app_platform', sa.String(length=20), nullable=True),
        sa.Column('app_version', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
    )

    op.create_index('ix_sync_operations_client_operation_id', 'sync_operations',
                    ['client_operation_id'], unique=True)
    op.create_index('idx_sync_ops_user_status', 'sync_operations',
                    ['user_id', 'status'])
    op.create_index('idx_sync_ops_tenant', 'sync_operations',
                    ['tenant_id'])
    op.create_index('idx_sync_ops_created', 'sync_operations',
                    ['created_at'])
    op.create_index(op.f('ix_sync_operations_user_id'), 'sync_operations',
                    ['user_id'], unique=False)
    op.create_index(op.f('ix_sync_operations_tenant_id'), 'sync_operations',
                    ['tenant_id'], unique=False)
    op.create_index(op.f('ix_sync_operations_status'), 'sync_operations',
                    ['status'], unique=False)
    op.create_index(op.f('ix_sync_operations_id'), 'sync_operations',
                    ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sync_operations_id'), table_name='sync_operations')
    op.drop_index(op.f('ix_sync_operations_status'), table_name='sync_operations')
    op.drop_index(op.f('ix_sync_operations_tenant_id'), table_name='sync_operations')
    op.drop_index(op.f('ix_sync_operations_user_id'), table_name='sync_operations')
    op.drop_index('idx_sync_ops_created', table_name='sync_operations')
    op.drop_index('idx_sync_ops_tenant', table_name='sync_operations')
    op.drop_index('idx_sync_ops_user_status', table_name='sync_operations')
    op.drop_index('ix_sync_operations_client_operation_id', table_name='sync_operations')

    op.drop_table('sync_operations')
    op.execute('DROP TYPE IF EXISTS syncoperationstatus')
