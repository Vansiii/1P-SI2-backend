"""add_optimized_indexes

Revision ID: f9e8d7c6b5a4
Revises: g3c4d5e6f7h8
Create Date: 2026-04-22 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9e8d7c6b5a4'
down_revision: Union[str, None] = 'g3c4d5e6f7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add optimized indexes for real-time queries.
    
    These indexes improve performance for:
    - Incident queries by status and creation date
    - Workshop-specific incident queries
    - Tracking location queries
    - Chat message queries
    - Notification queries
    """
    
    # ═══════════════════════════════════════════════════════════════════════════
    # INCIDENTES TABLE INDEXES
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Index for querying incidents by status and creation date (dashboard, lists)
    # Used by: GET /incidents?estado=pendiente, dashboard queries
    op.create_index(
        'idx_incidentes_estado_fecha',
        'incidentes',
        ['estado_actual', sa.text('created_at DESC')],
        postgresql_where=sa.text("estado_actual IN ('pendiente', 'asignado', 'aceptado', 'en_camino', 'en_proceso')")
    )
    
    # Index for workshop-specific incident queries
    # Used by: GET /workshops/{id}/incidents
    op.create_index(
        'idx_incidentes_taller_estado',
        'incidentes',
        ['taller_id', 'estado_actual'],
        postgresql_where=sa.text("taller_id IS NOT NULL")
    )
    
    # Index for technician-specific incident queries
    # Used by: GET /technicians/{id}/incidents
    op.create_index(
        'idx_incidentes_tecnico_estado',
        'incidentes',
        ['tecnico_id', 'estado_actual'],
        postgresql_where=sa.text("tecnico_id IS NOT NULL")
    )
    
    # Index for client-specific incident queries
    # Used by: GET /clients/{id}/incidents
    op.create_index(
        'idx_incidentes_client_fecha',
        'incidentes',
        ['client_id', sa.text('created_at DESC')]
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TECHNICIAN_LOCATION_HISTORY TABLE INDEXES
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Index for technician location history (most recent first)
    # Used by: Real-time tracking, distance calculations
    op.create_index(
        'idx_tech_location_history_tech_recorded',
        'technician_location_history',
        ['technician_id', sa.text('recorded_at DESC')]
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # MESSAGES TABLE INDEXES (Chat)
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Index for incident messages (most recent first)
    # Used by: GET /incidents/{id}/messages
    op.create_index(
        'idx_messages_incident_created',
        'messages',
        ['incident_id', sa.text('created_at DESC')]
    )
    
    # Index for unread messages
    # Used by: Unread message counts
    op.create_index(
        'idx_messages_unread',
        'messages',
        ['is_read', 'created_at'],
        postgresql_where=sa.text("is_read = false")
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NOTIFICATIONS TABLE INDEXES
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Index for user notifications (most recent first)
    # Used by: GET /users/{id}/notifications
    op.create_index(
        'idx_notifications_user_created',
        'notifications',
        ['user_id', sa.text('created_at DESC')]
    )
    
    # Index for unread notifications
    # Used by: Notification badge counts
    op.create_index(
        'idx_notifications_user_unread',
        'notifications',
        ['user_id', 'created_at'],
        postgresql_where=sa.text("is_read = false")
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TRACKING_SESSIONS TABLE INDEXES
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Index for active tracking sessions
    # Used by: Timeout checks, active session queries
    op.create_index(
        'idx_tracking_sessions_active',
        'tracking_sessions',
        ['is_active', 'started_at'],
        postgresql_where=sa.text("is_active = true")
    )
    
    # Index for incident tracking sessions
    # Used by: GET /incidents/{id}/tracking-sessions
    op.create_index(
        'idx_tracking_sessions_incident_started',
        'tracking_sessions',
        ['incidente_id', sa.text('started_at DESC')],
        postgresql_where=sa.text("incidente_id IS NOT NULL")
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ASSIGNMENT_ATTEMPTS TABLE INDEXES
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Index for pending assignment attempts (timeout checks)
    # Used by: check_assignment_timeouts()
    op.create_index(
        'idx_assignment_attempts_pending',
        'assignment_attempts',
        ['status', 'attempted_at'],
        postgresql_where=sa.text("status = 'pending'")
    )
    
    # Index for incident assignment history
    # Used by: Assignment cascading, history queries
    op.create_index(
        'idx_assignment_attempts_incident_created',
        'assignment_attempts',
        ['incident_id', sa.text('created_at DESC')]
    )
    
    # Index for workshop assignment attempts
    # Used by: Workshop-specific assignment queries
    op.create_index(
        'idx_assignment_attempts_workshop_status',
        'assignment_attempts',
        ['workshop_id', 'status', 'created_at']
    )


def downgrade() -> None:
    """Remove optimized indexes."""
    
    # Drop all indexes in reverse order
    op.drop_index('idx_assignment_attempts_workshop_status', table_name='assignment_attempts')
    op.drop_index('idx_assignment_attempts_incident_created', table_name='assignment_attempts')
    op.drop_index('idx_assignment_attempts_pending', table_name='assignment_attempts')
    
    op.drop_index('idx_tracking_sessions_incident_started', table_name='tracking_sessions')
    op.drop_index('idx_tracking_sessions_active', table_name='tracking_sessions')
    
    op.drop_index('idx_notifications_user_unread', table_name='notifications')
    op.drop_index('idx_notifications_user_created', table_name='notifications')
    
    op.drop_index('idx_messages_unread', table_name='messages')
    op.drop_index('idx_messages_incident_created', table_name='messages')
    
    op.drop_index('idx_tech_location_history_tech_recorded', table_name='technician_location_history')
    
    op.drop_index('idx_incidentes_client_fecha', table_name='incidentes')
    op.drop_index('idx_incidentes_tecnico_estado', table_name='incidentes')
    op.drop_index('idx_incidentes_taller_estado', table_name='incidentes')
    op.drop_index('idx_incidentes_estado_fecha', table_name='incidentes')
