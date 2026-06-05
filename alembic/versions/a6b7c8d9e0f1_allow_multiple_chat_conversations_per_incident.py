"""allow_multiple_chat_conversations_per_incident

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-06-04 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a6b7c8d9e0f1'
down_revision: Union[str, Sequence[str], None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index('ix_conversations_incident_id', table_name='conversations')
    op.create_index(
        'ix_conversations_incident_id',
        'conversations',
        ['incident_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_conversations_incident_id', table_name='conversations')
    op.create_index(
        'ix_conversations_incident_id',
        'conversations',
        ['incident_id'],
        unique=True,
    )
