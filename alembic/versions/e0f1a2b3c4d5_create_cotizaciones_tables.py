"""create_cotizaciones_tables

Revision ID: e0f1a2b3c4d5
Revises: d8fa9b0b655b
Create Date: 2026-06-08

Crea las tablas cotizaciones y cotizacion_respuestas que la migracion #31
(d8fa9b0b655b) debio crear pero no lo hizo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e0f1a2b3c4d5'
down_revision: Union[str, Sequence[str], None] = 'd8fa9b0b655b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cotizaciones',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('vehiculo_id', sa.Integer(), sa.ForeignKey('vehiculos.id'), nullable=False),
        sa.Column('workshop_id', sa.Integer(), sa.ForeignKey('workshops.id'), nullable=True),
        sa.Column('latitud', sa.Numeric(10, 8), nullable=False),
        sa.Column('longitud', sa.Numeric(11, 8), nullable=False),
        sa.Column('direccion_referencia', sa.String(500), nullable=True),
        sa.Column('descripcion_dano', sa.Text(), nullable=False),
        sa.Column('imagenes_dano', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('audio_diagnostico', sa.String(500), nullable=True),
        sa.Column('categoria_ia', sa.String(100), nullable=True),
        sa.Column('prioridad_ia', sa.String(20), nullable=True),
        sa.Column('resumen_ia', sa.Text(), nullable=True),
        sa.Column('es_ambiguo', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('servicios_cotizados', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('costo_total_estimado', sa.Numeric(12, 2), nullable=True),
        sa.Column('tiempo_total_estimado_minutos', sa.Integer(), nullable=True),
        sa.Column('notas_cotizacion', sa.Text(), nullable=True),
        sa.Column('estado', sa.String(50), nullable=False, server_default=sa.text("'pendiente_cotizacion'")),
        sa.Column('stripe_payment_intent_id', sa.String(255), nullable=True),
        sa.Column('monto_pagado', sa.Numeric(12, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('cotizado_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('taller_seleccionado_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pagado_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completado_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "estado IN ('pendiente_cotizacion', 'cotizando', 'cotizado', 'taller_seleccionado', "
            "'pago_pendiente', 'pagado', 'en_proceso', 'completado', 'cancelado', 'rechazado')",
            name="check_cotizacion_estado_valid"
        ),
    )
    op.create_index('idx_cotizaciones_client_estado', 'cotizaciones', ['client_id', 'estado'])
    op.create_index('idx_cotizaciones_tenant_estado', 'cotizaciones', ['tenant_id', 'estado'])
    op.create_index('idx_cotizaciones_workshop', 'cotizaciones', ['workshop_id'])
    op.create_index('ix_cotizaciones_client_id', 'cotizaciones', ['client_id'])
    op.create_index('ix_cotizaciones_estado', 'cotizaciones', ['estado'])
    op.create_index('ix_cotizaciones_created_at', 'cotizaciones', ['created_at'])
    op.create_index('ix_cotizaciones_tenant_id', 'cotizaciones', ['tenant_id'])
    op.create_index('ix_cotizaciones_vehiculo_id', 'cotizaciones', ['vehiculo_id'])
    op.create_index('ix_cotizaciones_workshop_id', 'cotizaciones', ['workshop_id'])

    op.create_table(
        'cotizacion_respuestas',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('cotizacion_id', sa.Integer(), sa.ForeignKey('cotizaciones.id'), nullable=False),
        sa.Column('workshop_id', sa.Integer(), sa.ForeignKey('workshops.id'), nullable=False),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=True),
        sa.Column('servicios', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('costo_total', sa.Numeric(12, 2), nullable=False),
        sa.Column('tiempo_estimado_minutos', sa.Integer(), nullable=False),
        sa.Column('tiempo_estimado_texto', sa.String(200), nullable=False),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('valida_hasta', sa.DateTime(timezone=True), nullable=False),
        sa.Column('estado', sa.String(50), nullable=False, server_default=sa.text("'pendiente'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'aceptada', 'rechazada', 'expirada')",
            name="check_cotizacion_respuesta_estado_valid"
        ),
    )
    op.create_index('idx_cotizacion_resp_cotizacion', 'cotizacion_respuestas', ['cotizacion_id'])
    op.create_index('idx_cotizacion_resp_workshop', 'cotizacion_respuestas', ['workshop_id'])
    op.create_index('ix_cotizacion_respuestas_cotizacion_id', 'cotizacion_respuestas', ['cotizacion_id'])
    op.create_index('ix_cotizacion_respuestas_estado', 'cotizacion_respuestas', ['estado'])
    op.create_index('ix_cotizacion_respuestas_tenant_id', 'cotizacion_respuestas', ['tenant_id'])
    op.create_index('ix_cotizacion_respuestas_workshop_id', 'cotizacion_respuestas', ['workshop_id'])


def downgrade() -> None:
    op.drop_table('cotizacion_respuestas')
    op.drop_table('cotizaciones')
