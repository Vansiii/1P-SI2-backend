"""add_service_catalog_fields

Revision ID: d3e4f5a6b7c8
Revises: 95dd24b258e1
Create Date: 2026-05-27

Adds fields to servicios, categorias, and servicios_taller for CU28 service catalog management.
- servicios: +descripcion
- categorias: +descripcion, +icon
- servicios_taller: +is_active, +modalidad, +tiempo_estimado_min, +descripcion, +deleted_at
- Indexes: idx_st_servicio_active, idx_st_taller_active
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = '95dd24b258e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- servicios: agregar descripcion ---
    op.add_column('servicios',
        sa.Column('descripcion', sa.String(500), nullable=True)
    )

    # --- categorias: agregar descripcion e icon ---
    op.add_column('categorias',
        sa.Column('descripcion', sa.String(500), nullable=True)
    )
    op.add_column('categorias',
        sa.Column('icon', sa.String(50), nullable=True)
    )

    # --- servicios_taller: agregar campos de catálogo ---
    op.add_column('servicios_taller',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true'))
    )
    op.add_column('servicios_taller',
        sa.Column('modalidad', sa.String(20), nullable=False, server_default='taller')
    )
    op.add_column('servicios_taller',
        sa.Column('tiempo_estimado_min', sa.Integer(), nullable=True)
    )
    op.add_column('servicios_taller',
        sa.Column('descripcion', sa.String(500), nullable=True)
    )
    op.add_column('servicios_taller',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )

    # --- Alter precio to nullable (opcional para algunos planes) ---
    op.alter_column('servicios_taller', 'precio',
        existing_type=sa.Numeric(10, 2),
        nullable=True
    )

    # --- Crear índices ---
    op.create_index('idx_st_servicio_active', 'servicios_taller', ['servicio_id', 'is_active'])
    op.create_index('idx_st_taller_active', 'servicios_taller', ['taller_id', 'is_active'])

    # ============================================================
    # SEED: Insertar categorías base
    # ============================================================
    categorias_data = [
        {"nombre": "Mecánica General", "icon": "build", "descripcion": "Servicios de mecánica general: motor, transmisión, frenos, suspensión."},
        {"nombre": "Electricidad", "icon": "bolt", "descripcion": "Sistema eléctrico: arranque, alternador, luces, cableado."},
        {"nombre": "Electrónica", "icon": "memory", "descripcion": "Sistema electrónico: ECU, sensores, computadora, diagnóstico."},
        {"nombre": "Chapería y Pintura", "icon": "palette", "descripcion": "Reparación de carrocería, pintura, enderezado."},
        {"nombre": "Remolque", "icon": "towing", "descripcion": "Servicio de grúa y remolque para vehículos."},
        {"nombre": "Llantas / Vulcanización", "icon": "tire_repair", "descripcion": "Cambio, reparación y balanceo de llantas."},
        {"nombre": "Batería", "icon": "battery_charging_full", "descripcion": "Cambio de batería, paso de corriente, diagnóstico."},
        {"nombre": "Motor", "icon": "engine", "descripcion": "Reparación mayor y menor de motor."},
        {"nombre": "Frenos", "icon": "disc_brake", "descripcion": "Reparación y cambio de frenos, discos y pastillas."},
        {"nombre": "Suspensión y Dirección", "icon": "settings", "descripcion": "Reparación de suspensión, amortiguadores, dirección."},
        {"nombre": "Aire Acondicionado", "icon": "ac_unit", "descripcion": "Carga, reparación y diagnóstico de aire acondicionado."},
        {"nombre": "Otros", "icon": "more_horiz", "descripcion": "Otros servicios no clasificados."},
    ]

    for cat in categorias_data:
        op.execute(
            sa.text(
                "INSERT INTO categorias (nombre, descripcion, icon) "
                "VALUES (:nombre, :descripcion, :icon) "
                "ON CONFLICT (nombre) DO UPDATE SET "
                "descripcion = EXCLUDED.descripcion, "
                "icon = EXCLUDED.icon"
            ).bindparams(
                nombre=cat["nombre"],
                descripcion=cat["descripcion"],
                icon=cat["icon"]
            )
        )


def downgrade() -> None:
    op.drop_index('idx_st_taller_active', table_name='servicios_taller')
    op.drop_index('idx_st_servicio_active', table_name='servicios_taller')
    op.alter_column('servicios_taller', 'precio',
        existing_type=sa.Numeric(10, 2),
        nullable=False
    )
    op.drop_column('servicios_taller', 'deleted_at')
    op.drop_column('servicios_taller', 'descripcion')
    op.drop_column('servicios_taller', 'tiempo_estimado_min')
    op.drop_column('servicios_taller', 'modalidad')
    op.drop_column('servicios_taller', 'is_active')
    op.drop_column('categorias', 'icon')
    op.drop_column('categorias', 'descripcion')
    op.drop_column('servicios', 'descripcion')
