"""add timeout status to ai analysis

Revision ID: i4j5k6l7m8n9
Revises: g3c4d5e6f7h8
Create Date: 2026-04-25 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'i4j5k6l7m8n9'
down_revision = 'g3c4d5e6f7h8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old constraint
    op.drop_constraint(
        'check_incident_ai_analysis_status',
        'incident_ai_analyses',
        type_='check'
    )
    
    # Add new constraint with 'timeout' status
    op.create_check_constraint(
        'check_incident_ai_analysis_status',
        'incident_ai_analyses',
        "status IN ('pending', 'processing', 'completed', 'failed', 'timeout')"
    )


def downgrade() -> None:
    # Drop new constraint
    op.drop_constraint(
        'check_incident_ai_analysis_status',
        'incident_ai_analyses',
        type_='check'
    )
    
    # Restore old constraint without 'timeout'
    op.create_check_constraint(
        'check_incident_ai_analysis_status',
        'incident_ai_analyses',
        "status IN ('pending', 'processing', 'completed', 'failed')"
    )
