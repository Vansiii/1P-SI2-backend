"""add service ratings table

Revision ID: add_service_ratings
Revises: h123456789ab
Create Date: 2026-04-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_service_ratings'
down_revision: Union[str, None] = 'i4j5k6l7m8n9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create service_ratings table
    op.create_table(
        'service_ratings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('workshop_id', sa.Integer(), nullable=False),
        sa.Column('technician_id', sa.Integer(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidentes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workshop_id'], ['workshops.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['technician_id'], ['technicians.id'], ondelete='SET NULL'),
        sa.CheckConstraint('rating >= 1 AND rating <= 5', name='check_rating_range')
    )
    
    # Create indexes
    op.create_index('idx_service_ratings_incident_unique', 'service_ratings', ['incident_id'], unique=True)
    op.create_index('idx_service_ratings_workshop', 'service_ratings', ['workshop_id', 'created_at'])
    op.create_index('idx_service_ratings_technician', 'service_ratings', ['technician_id', 'created_at'])
    op.create_index('idx_service_ratings_client', 'service_ratings', ['client_id', 'created_at'])
    op.create_index(op.f('ix_service_ratings_incident_id'), 'service_ratings', ['incident_id'], unique=False)
    op.create_index(op.f('ix_service_ratings_client_id'), 'service_ratings', ['client_id'], unique=False)
    op.create_index(op.f('ix_service_ratings_workshop_id'), 'service_ratings', ['workshop_id'], unique=False)
    op.create_index(op.f('ix_service_ratings_technician_id'), 'service_ratings', ['technician_id'], unique=False)
    op.create_index(op.f('ix_service_ratings_created_at'), 'service_ratings', ['created_at'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_service_ratings_created_at'), table_name='service_ratings')
    op.drop_index(op.f('ix_service_ratings_technician_id'), table_name='service_ratings')
    op.drop_index(op.f('ix_service_ratings_workshop_id'), table_name='service_ratings')
    op.drop_index(op.f('ix_service_ratings_client_id'), table_name='service_ratings')
    op.drop_index(op.f('ix_service_ratings_incident_id'), table_name='service_ratings')
    op.drop_index('idx_service_ratings_client', table_name='service_ratings')
    op.drop_index('idx_service_ratings_technician', table_name='service_ratings')
    op.drop_index('idx_service_ratings_workshop', table_name='service_ratings')
    op.drop_index('idx_service_ratings_incident_unique', table_name='service_ratings')
    
    # Drop table
    op.drop_table('service_ratings')
