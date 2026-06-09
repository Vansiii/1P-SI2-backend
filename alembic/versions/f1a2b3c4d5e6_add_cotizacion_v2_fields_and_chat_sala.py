"""add_cotizacion_v2_fields_and_chat_sala

Revision ID: g1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-06-08

Migracion aditiva para CU32 v2:
- Agrega 4 columnas nuevas a cotizaciones (incidente_id, chat_sala_id, monto_aceptado, version)
- Agrega 2 nuevos estados al CHECK constraint (negociando, aceptado)
- Crea tabla cotizacion_chat_salas para negociacion via chat
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'g1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e0f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Agregar nuevas columnas a cotizaciones
    op.add_column('cotizaciones', sa.Column(
        'incidente_id', sa.Integer(), sa.ForeignKey('incidentes.id'), nullable=True,
        comment='Incidente vinculado (v2, cotizacion desde detalle de taller)'
    ))
    op.create_index('ix_cotizaciones_incidente_id', 'cotizaciones', ['incidente_id'])

    op.add_column('cotizaciones', sa.Column(
        'chat_sala_id', sa.Integer(), nullable=True,
        comment='FK a cotizacion_chat_salas (se agrega FK despues de crear la tabla)'
    ))

    op.add_column('cotizaciones', sa.Column(
        'monto_aceptado', sa.Numeric(12, 2), nullable=True,
        comment='Monto aceptado por el cliente al finalizar negociacion'
    ))

    op.add_column('cotizaciones', sa.Column(
        'version', sa.String(10), nullable=False, server_default=sa.text("'v1'"),
        comment='Version del flujo: v1 (solicitud al vacio) o v2 (desde taller especifico)'
    ))
    op.create_index('ix_cotizaciones_version', 'cotizaciones', ['version'])

    # 2. Actualizar CHECK constraint para incluir nuevos estados
    op.execute(
        "ALTER TABLE cotizaciones DROP CONSTRAINT IF EXISTS check_cotizacion_estado_valid"
    )
    op.create_check_constraint(
        'check_cotizacion_estado_valid',
        'cotizaciones',
        "estado IN ('pendiente_cotizacion', 'cotizando', 'cotizado', "
        "'taller_seleccionado', 'pago_pendiente', 'pagado', 'en_proceso', "
        "'completado', 'cancelado', 'rechazado', 'negociando', 'aceptado')"
    )

    # 3. Crear tabla cotizacion_chat_salas
    op.create_table(
        'cotizacion_chat_salas',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('cotizacion_id', sa.Integer(), sa.ForeignKey('cotizaciones.id'), nullable=False),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('workshop_id', sa.Integer(), sa.ForeignKey('workshops.id'), nullable=False),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=True),
        sa.Column('estado', sa.String(30), nullable=False, server_default=sa.text("'activa'")),
        sa.Column('ultima_oferta_monto', sa.Numeric(12, 2), nullable=True),
        sa.Column('ultima_oferta_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('cerrada_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "estado IN ('activa', 'cerrada_aceptada', 'cerrada_sin_acuerdo')",
            name="check_cotizacion_chat_sala_estado"
        ),
    )
    op.create_index('ix_cotizacion_chat_salas_cotizacion', 'cotizacion_chat_salas', ['cotizacion_id'])
    op.create_index('ix_cotizacion_chat_salas_conversation', 'cotizacion_chat_salas', ['conversation_id'])
    op.create_index('ix_cotizacion_chat_salas_estado', 'cotizacion_chat_salas', ['estado'])
    op.create_index('ix_cotizacion_chat_salas_tenant_id', 'cotizacion_chat_salas', ['tenant_id'])

    # 4. Agregar FK de chat_sala_id a cotizaciones (ahora que la tabla existe)
    op.create_foreign_key(
        'fk_cotizaciones_chat_sala',
        'cotizaciones', 'cotizacion_chat_salas',
        ['chat_sala_id'], ['id']
    )


def downgrade() -> None:
    # Revertir FK
    op.drop_constraint('fk_cotizaciones_chat_sala', 'cotizaciones', type_='foreignkey')

    # Revertir tabla
    op.drop_table('cotizacion_chat_salas')

    # Revertir CHECK constraint
    op.execute(
        "ALTER TABLE cotizaciones DROP CONSTRAINT IF EXISTS check_cotizacion_estado_valid"
    )
    op.create_check_constraint(
        'check_cotizacion_estado_valid',
        'cotizaciones',
        "estado IN ('pendiente_cotizacion', 'cotizando', 'cotizado', 'taller_seleccionado', "
        "'pago_pendiente', 'pagado', 'en_proceso', 'completado', 'cancelado', 'rechazado')"
    )

    # Revertir columnas
    op.drop_index('ix_cotizaciones_version', table_name='cotizaciones')
    op.drop_column('cotizaciones', 'version')
    op.drop_column('cotizaciones', 'monto_aceptado')
    op.drop_index('ix_cotizaciones_incidente_id', table_name='cotizaciones')
    op.drop_column('cotizaciones', 'chat_sala_id')
    op.drop_column('cotizaciones', 'incidente_id')
