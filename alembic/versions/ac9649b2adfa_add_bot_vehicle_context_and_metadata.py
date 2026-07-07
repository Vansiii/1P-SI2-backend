"""add_bot_vehicle_context_and_metadata

Revision ID: ac9649b2adfa
Revises: 16e12fa82588
Create Date: 2026-07-05 18:39:02.300848

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ac9649b2adfa'
down_revision: Union[str, Sequence[str], None] = '16e12fa82588'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### bot_conversations: contexto vehicular opcional ###
    op.add_column('bot_conversations', sa.Column('vehicle_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_bot_conversations_vehicle_id', 'bot_conversations', 'vehiculos',
        ['vehicle_id'], ['id'], ondelete='SET NULL'
    )
    op.create_index(
        op.f('ix_bot_conversations_vehicle_id'), 'bot_conversations', ['vehicle_id'], unique=False
    )

    # ### bot_messages: metadata de IA (modelo usado, tokens, latencia, tool calls) ###
    op.add_column('bot_messages', sa.Column('model_used', sa.String(length=80), nullable=True))
    op.add_column('bot_messages', sa.Column('tokens_used', sa.Integer(), nullable=True))
    op.add_column('bot_messages', sa.Column('response_time_ms', sa.Integer(), nullable=True))
    op.add_column('bot_messages', sa.Column('tool_calls', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('bot_messages', 'tool_calls')
    op.drop_column('bot_messages', 'response_time_ms')
    op.drop_column('bot_messages', 'tokens_used')
    op.drop_column('bot_messages', 'model_used')

    op.drop_index(op.f('ix_bot_conversations_vehicle_id'), table_name='bot_conversations')
    op.drop_constraint('fk_bot_conversations_vehicle_id', 'bot_conversations', type_='foreignkey')
    op.drop_column('bot_conversations', 'vehicle_id')
