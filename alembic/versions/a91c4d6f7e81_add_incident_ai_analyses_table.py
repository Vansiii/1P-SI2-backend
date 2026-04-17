"""add_incident_ai_analyses_table

Revision ID: a91c4d6f7e81
Revises: bcfa17e3a088, f1a2b3c4d5e6
Create Date: 2026-04-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a91c4d6f7e81'
down_revision: Union[str, Sequence[str], None] = ('bcfa17e3a088', 'f1a2b3c4d5e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create technical table for UC10 incident AI analyses."""
    op.create_table(
        'incident_ai_analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('prompt_version', sa.String(length=40), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('priority', sa.String(length=20), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('is_ambiguous', sa.Boolean(), nullable=False),
        sa.Column('confidence', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('findings_json', sa.Text(), nullable=True),
        sa.Column('missing_data_json', sa.Text(), nullable=True),
        sa.Column('workshop_recommendation', sa.Text(), nullable=True),
        sa.Column('raw_response_json', sa.Text(), nullable=True),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name='check_incident_ai_analysis_status',
        ),
        sa.CheckConstraint(
            "priority IN ('alta', 'media', 'baja') OR priority IS NULL",
            name='check_incident_ai_analysis_priority',
        ),
        sa.CheckConstraint(
            'confidence BETWEEN 0 AND 1 OR confidence IS NULL',
            name='check_incident_ai_analysis_confidence',
        ),
        sa.ForeignKeyConstraint(['incident_id'], ['incidentes.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index('ix_incident_ai_analyses_incident_id', 'incident_ai_analyses', ['incident_id'])
    op.create_index('ix_incident_ai_analyses_status', 'incident_ai_analyses', ['status'])
    op.create_index('ix_incident_ai_analyses_request_hash', 'incident_ai_analyses', ['request_hash'])
    op.create_index('ix_incident_ai_analyses_created_at', 'incident_ai_analyses', ['created_at'])


def downgrade() -> None:
    """Drop technical UC10 incident AI analyses table."""
    op.drop_index('ix_incident_ai_analyses_created_at', table_name='incident_ai_analyses')
    op.drop_index('ix_incident_ai_analyses_request_hash', table_name='incident_ai_analyses')
    op.drop_index('ix_incident_ai_analyses_status', table_name='incident_ai_analyses')
    op.drop_index('ix_incident_ai_analyses_incident_id', table_name='incident_ai_analyses')

    op.drop_table('incident_ai_analyses')
