"""seed_additional_base_services

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-09

Adds 30 new base services to the servicios table, organized by category.
Uses idempotent INSERT (skips if nombre + categoria_id already exists).
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'g1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NUEVOS_SERVICIOS = [
    # ── Mecánica General ──
    ("Cambio de bujías", "Mecánica General"),
    ("Cambio de filtro de aire", "Mecánica General"),
    ("Cambio de filtro de combustible", "Mecánica General"),
    ("Lavado de motor", "Mecánica General"),
    ("Cambio de mangueras del radiador", "Mecánica General"),
    # ── Electricidad ──
    ("Instalación de alarma", "Electricidad"),
    ("Instalación de radio y estéreo", "Electricidad"),
    ("Instalación de faros LED", "Electricidad"),
    # ── Electrónica ──
    ("Calibración de sensores", "Electrónica"),
    ("Actualización de software ECU", "Electrónica"),
    ("Reparación de módulo ABS", "Electrónica"),
    # ── Chapería y Pintura ──
    ("Pulido y encerado", "Chapería y Pintura"),
    ("Polarizado de vidrios", "Chapería y Pintura"),
    ("Reparación de parabrisas", "Chapería y Pintura"),
    ("Cambio de parabrisas", "Chapería y Pintura"),
    # ── Llantas / Vulcanización ──
    ("Rotación de llantas", "Llantas / Vulcanización"),
    ("Venta de llantas nuevas", "Llantas / Vulcanización"),
    # ── Batería ──
    ("Venta e instalación de batería", "Batería"),
    # ── Motor ──
    ("Cambio de banda de accesorios", "Motor"),
    ("Limpieza de inyectores", "Motor"),
    ("Cambio de bomba de agua", "Motor"),
    ("Reparación de sistema de escape", "Motor"),
    # ── Frenos ──
    ("Rectificado de discos de freno", "Frenos"),
    ("Cambio de bomba de freno", "Frenos"),
    # ── Suspensión y Dirección ──
    ("Cambio de resortes", "Suspensión y Dirección"),
    ("Cambio de bujes de suspensión", "Suspensión y Dirección"),
    ("Cambio de bieletas", "Suspensión y Dirección"),
    # ── Aire Acondicionado ──
    ("Cambio de filtro de cabina", "Aire Acondicionado"),
    ("Cambio de evaporador de AC", "Aire Acondicionado"),
    # ── Otros ──
    ("Lavado exterior", "Otros"),
    ("Lavado interior", "Otros"),
    ("Desinfección con ozono", "Otros"),
    ("Revisión pre-compra", "Otros"),
    ("Peritaje vehicular", "Otros"),
    ("Gestión de SOAT", "Otros"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Obtener IDs de categorías por nombre
    cat_rows = conn.execute(
        sa.text("SELECT id, nombre FROM categorias")
    ).fetchall()
    cat_map = {row[1]: row[0] for row in cat_rows}

    # Obtener servicios existentes (nombre, categoria_id)
    existing = conn.execute(
        sa.text("SELECT nombre, categoria_id FROM servicios")
    ).fetchall()
    existing_set = {(row[0], row[1]) for row in existing}

    inserted = 0
    skipped = 0
    for nombre, cat_nombre in NUEVOS_SERVICIOS:
        cid = cat_map.get(cat_nombre)
        if cid is None:
            skipped += 1
            continue
        if (nombre, cid) in existing_set:
            skipped += 1
            continue

        conn.execute(
            sa.text(
                "INSERT INTO servicios (nombre, categoria_id) VALUES (:nombre, :categoria_id)"
            ),
            {"nombre": nombre, "categoria_id": cid},
        )
        existing_set.add((nombre, cid))
        inserted += 1

    print(f"  Servicios insertados: {inserted}, omitidos (ya existen): {skipped}")


def downgrade() -> None:
    conn = op.get_bind()
    nombres = [s[0] for s in NUEVOS_SERVICIOS]
    conn.execute(
        sa.text(
            "DELETE FROM servicios WHERE nombre = ANY(:nombres)"
        ),
        {"nombres": nombres},
    )
