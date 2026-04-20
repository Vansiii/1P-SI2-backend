"""add sin_taller_disponible to estado_actual constraint

Revision ID: a1b2c3d4e5f6
Revises: f2b3c4d5e6f7
Create Date: 2026-04-19 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use raw SQL to drop and recreate the constraint in a single statement
    # This avoids the Supabase statement_timeout issue with separate DDL calls
    op.execute("""
        ALTER TABLE incidentes
            DROP CONSTRAINT check_estado_actual_valid,
            ADD CONSTRAINT check_estado_actual_valid
                CHECK (estado_actual IN ('pendiente', 'asignado', 'en_proceso', 'resuelto', 'cancelado', 'sin_taller_disponible'))
    """)


def downgrade() -> None:
    # Reset any rows with the new state before removing it from the constraint
    op.execute(
        "UPDATE incidentes SET estado_actual = 'pendiente' WHERE estado_actual = 'sin_taller_disponible'"
    )
    op.execute("""
        ALTER TABLE incidentes
            DROP CONSTRAINT check_estado_actual_valid,
            ADD CONSTRAINT check_estado_actual_valid
                CHECK (estado_actual IN ('pendiente', 'asignado', 'en_proceso', 'resuelto', 'cancelado'))
    """)
