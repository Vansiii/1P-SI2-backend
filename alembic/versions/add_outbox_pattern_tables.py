"""add outbox pattern tables

Revision ID: g3c4d5e6f7h8
Revises: a1b2c3d4e5f6
Create Date: 2026-04-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'g3c4d5e6f7h8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if event_priority enum exists
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'event_priority')"
    ))
    enum_exists = result.scalar()
    
    # Create enum only if it doesn't exist
    if not enum_exists:
        conn.execute(sa.text(
            "CREATE TYPE event_priority AS ENUM ('low', 'medium', 'high', 'critical')"
        ))
    
    # Create outbox_events table
    op.create_table(
        'outbox_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False, server_default='1.0'),
        sa.Column('priority', sa.String(length=20), nullable=False, server_default='medium'),
        sa.Column('processed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        comment='Outbox events for transactional event publishing'
    )
    
    # Cast priority column to event_priority enum if enum was created
    if not enum_exists:
        # Drop default first
        op.execute(sa.text(
            "ALTER TABLE outbox_events ALTER COLUMN priority DROP DEFAULT"
        ))
        # Cast to enum
        op.execute(sa.text(
            "ALTER TABLE outbox_events ALTER COLUMN priority TYPE event_priority USING priority::event_priority"
        ))
        # Re-add default
        op.execute(sa.text(
            "ALTER TABLE outbox_events ALTER COLUMN priority SET DEFAULT 'medium'::event_priority"
        ))
    
    # Create indexes for outbox_events
    op.create_index('ix_outbox_events_id', 'outbox_events', ['id'])
    op.create_index('ix_outbox_events_event_id', 'outbox_events', ['event_id'], unique=True)
    op.create_index('ix_outbox_events_event_type', 'outbox_events', ['event_type'])
    op.create_index('ix_outbox_events_processed', 'outbox_events', ['processed'])
    op.create_index('ix_outbox_events_priority', 'outbox_events', ['priority'])
    op.create_index('ix_outbox_events_created_at', 'outbox_events', ['created_at'])
    
    # Composite index for processing pending events (with partial index)
    op.create_index(
        'idx_outbox_pending_priority',
        'outbox_events',
        ['processed', 'priority', 'created_at'],
        postgresql_where=sa.text('processed = false')
    )
    
    # Index for cleanup of old processed events (with partial index)
    op.create_index(
        'idx_outbox_processed_at',
        'outbox_events',
        ['processed_at'],
        postgresql_where=sa.text('processed = true')
    )
    
    # Index for retry logic (with partial index)
    op.create_index(
        'idx_outbox_retry',
        'outbox_events',
        ['processed', 'retry_count', 'created_at'],
        postgresql_where=sa.text('processed = false')
    )
    
    # Create event_log table
    op.create_table(
        'event_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('delivered_via', sa.String(length=20), nullable=False),
        sa.Column('delivered_to', sa.Integer(), nullable=False),
        sa.Column('delivered_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        comment='Log of all delivered events for recovery and analytics'
    )
    
    # Create indexes for event_log
    op.create_index('ix_event_log_id', 'event_log', ['id'])
    op.create_index('ix_event_log_event_id', 'event_log', ['event_id'])
    op.create_index('ix_event_log_event_type', 'event_log', ['event_type'])
    op.create_index('ix_event_log_delivered_to', 'event_log', ['delivered_to'])
    op.create_index('ix_event_log_delivered_at', 'event_log', ['delivered_at'])
    
    # Composite index for missed events recovery
    op.create_index(
        'idx_event_log_user_time',
        'event_log',
        ['delivered_to', 'delivered_at']
    )
    
    # Composite index for event type analytics
    op.create_index(
        'idx_event_log_type_time',
        'event_log',
        ['event_type', 'delivered_at']
    )


def downgrade() -> None:
    # Drop event_log table and indexes
    op.drop_index('idx_event_log_type_time', table_name='event_log')
    op.drop_index('idx_event_log_user_time', table_name='event_log')
    op.drop_index('ix_event_log_delivered_at', table_name='event_log')
    op.drop_index('ix_event_log_delivered_to', table_name='event_log')
    op.drop_index('ix_event_log_event_type', table_name='event_log')
    op.drop_index('ix_event_log_event_id', table_name='event_log')
    op.drop_index('ix_event_log_id', table_name='event_log')
    op.drop_table('event_log')
    
    # Drop outbox_events table and indexes
    op.drop_index('idx_outbox_retry', table_name='outbox_events')
    op.drop_index('idx_outbox_processed_at', table_name='outbox_events')
    op.drop_index('idx_outbox_pending_priority', table_name='outbox_events')
    op.drop_index('ix_outbox_events_created_at', table_name='outbox_events')
    op.drop_index('ix_outbox_events_priority', table_name='outbox_events')
    op.drop_index('ix_outbox_events_processed', table_name='outbox_events')
    op.drop_index('ix_outbox_events_event_type', table_name='outbox_events')
    op.drop_index('ix_outbox_events_event_id', table_name='outbox_events')
    op.drop_index('ix_outbox_events_id', table_name='outbox_events')
    op.drop_table('outbox_events')
    
    # Drop event_priority enum
    event_priority_enum = postgresql.ENUM(
        'low', 'medium', 'high', 'critical',
        name='event_priority'
    )
    event_priority_enum.drop(op.get_bind(), checkfirst=True)
