"""add_rechazos_taller_table

Revision ID: f1a2b3c4d5e6
Revises: e8b757791785
Create Date: 2026-04-10 03:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e8b757791785'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Crear tabla rechazos_taller
    op.create_table(
        'rechazos_taller',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incidente_id', sa.Integer(), nullable=False),
        sa.Column('taller_id', sa.Integer(), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['incidente_id'], ['incidentes.id'], ),
        sa.ForeignKeyConstraint(['taller_id'], ['workshops.id'], ),
    )
    
    # Crear índices
    op.create_index('ix_rechazos_taller_incidente_id', 'rechazos_taller', ['incidente_id'])
    op.create_index('ix_rechazos_taller_taller_id', 'rechazos_taller', ['taller_id'])
    op.create_index('ix_rechazos_taller_created_at', 'rechazos_taller', ['created_at'])


def downgrade() -> None:
    # Eliminar índices
    op.drop_index('ix_rechazos_taller_created_at', table_name='rechazos_taller')
    op.drop_index('ix_rechazos_taller_taller_id', table_name='rechazos_taller')
    op.drop_index('ix_rechazos_taller_incidente_id', table_name='rechazos_taller')
    
    # Eliminar tabla
    op.drop_table('rechazos_taller')
