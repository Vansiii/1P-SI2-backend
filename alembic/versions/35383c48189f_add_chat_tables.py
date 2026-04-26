"""add_chat_tables

Revision ID: 35383c48189f
Revises: 5450761a33ab
Create Date: 2026-04-18 06:17:26.462807

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35383c48189f'
down_revision: Union[str, Sequence[str], None] = '5450761a33ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create conversations table
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('workshop_id', sa.Integer(), nullable=True),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('unread_count_client', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unread_count_workshop', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidentes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workshop_id'], ['workshops.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_conversations_incident_id', 'conversations', ['incident_id'], unique=True)
    op.create_index('ix_conversations_client_id', 'conversations', ['client_id'])
    op.create_index('ix_conversations_workshop_id', 'conversations', ['workshop_id'])

    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('message_type', sa.String(20), nullable=False, server_default='text'),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidentes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_messages_incident_id', 'messages', ['incident_id'])
    op.create_index('ix_messages_sender_id', 'messages', ['sender_id'])
    op.create_index('ix_messages_is_read', 'messages', ['is_read'])
    op.create_index('ix_messages_created_at', 'messages', ['created_at'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop messages table
    op.drop_index('ix_messages_created_at', 'messages')
    op.drop_index('ix_messages_is_read', 'messages')
    op.drop_index('ix_messages_sender_id', 'messages')
    op.drop_index('ix_messages_incident_id', 'messages')
    op.drop_table('messages')

    # Drop conversations table
    op.drop_index('ix_conversations_workshop_id', 'conversations')
    op.drop_index('ix_conversations_client_id', 'conversations')
    op.drop_index('ix_conversations_incident_id', 'conversations')
    op.drop_table('conversations')
