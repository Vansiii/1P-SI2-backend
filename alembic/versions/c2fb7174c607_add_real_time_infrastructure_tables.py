"""add_real_time_infrastructure_tables

Revision ID: c2fb7174c607
Revises: a91c4d6f7e81
Create Date: 2026-04-18 04:25:36.708439

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2fb7174c607'
down_revision: Union[str, Sequence[str], None] = 'a91c4d6f7e81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Crear tabla technician_location_history
    op.create_table(
        'technician_location_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('technician_id', sa.Integer(), nullable=False),
        sa.Column('latitude', sa.Numeric(precision=10, scale=8), nullable=False),
        sa.Column('longitude', sa.Numeric(precision=11, scale=8), nullable=False),
        sa.Column('accuracy', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('speed', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('heading', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['technician_id'], ['technicians.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tech_location_tech_time', 'technician_location_history', ['technician_id', 'recorded_at'], unique=False)
    
    # 2. Crear tabla tracking_sessions
    op.create_table(
        'tracking_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('technician_id', sa.Integer(), nullable=False),
        sa.Column('incidente_id', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('total_distance_km', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.ForeignKeyConstraint(['technician_id'], ['technicians.id'], ),
        sa.ForeignKeyConstraint(['incidente_id'], ['incidentes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tracking_sessions_technician', 'tracking_sessions', ['technician_id'], unique=False)
    op.create_index('ix_tracking_sessions_active', 'tracking_sessions', ['is_active'], unique=False)
    
    # 3. Agregar campos a technicians
    op.add_column('technicians', sa.Column('location_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('technicians', sa.Column('location_accuracy', sa.Numeric(precision=6, scale=2), nullable=True))
    op.add_column('technicians', sa.Column('is_online', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('technicians', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    
    # 4. Crear tabla notifications
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('data_json', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'], unique=False)
    op.create_index('ix_notifications_is_read', 'notifications', ['is_read'], unique=False)
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'], unique=False)
    
    # 5. Crear tabla push_tokens
    op.create_table(
        'push_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=500), nullable=False),
        sa.Column('platform', sa.String(length=20), nullable=False),
        sa.Column('device_id', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("platform IN ('android', 'ios', 'web')", name='check_platform_valid')
    )
    op.create_index('ix_push_tokens_user_id', 'push_tokens', ['user_id'], unique=False)
    op.create_index('ix_push_tokens_token', 'push_tokens', ['token'], unique=True)
    op.create_index('ix_push_tokens_is_active', 'push_tokens', ['is_active'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Eliminar en orden inverso
    op.drop_index('ix_push_tokens_is_active', table_name='push_tokens')
    op.drop_index('ix_push_tokens_token', table_name='push_tokens')
    op.drop_index('ix_push_tokens_user_id', table_name='push_tokens')
    op.drop_table('push_tokens')
    
    op.drop_index('ix_notifications_created_at', table_name='notifications')
    op.drop_index('ix_notifications_is_read', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_table('notifications')
    
    op.drop_column('technicians', 'last_seen_at')
    op.drop_column('technicians', 'is_online')
    op.drop_column('technicians', 'location_accuracy')
    op.drop_column('technicians', 'location_updated_at')
    
    op.drop_index('ix_tracking_sessions_active', table_name='tracking_sessions')
    op.drop_index('ix_tracking_sessions_technician', table_name='tracking_sessions')
    op.drop_table('tracking_sessions')
    
    op.drop_index('ix_tech_location_tech_time', table_name='technician_location_history')
    op.drop_table('technician_location_history')
