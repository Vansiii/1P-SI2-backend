"""
Script para poblar servicios_taller a todos los talleres activos.
Tambien crea servicios base si no existen.

Uso:
    cd 1P-SI2-backend
    .venv/Scripts/python.exe -m app.scripts.seed_workshop_services --dry-run
    .venv/Scripts/python.exe -m app.scripts.seed_workshop_services
"""

import asyncio
import sys
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session_factory, get_engine
from app.core.config import get_settings
from app.models.servicio import Servicio
from app.models.categoria import Categoria
from app.models.servicio_taller import ServicioTaller
from app.models.workshop import Workshop
from app.models.tenant import Tenant


SERVICIOS_BASE = [
    # Mecanica General
    ("Cambio de aceite y filtros", "Mecánica General", 80.00, 45, "taller"),
    ("Diagnóstico computarizado", "Mecánica General", 120.00, 60, "taller"),
    ("Revisión general del vehículo", "Mecánica General", 100.00, 60, "taller"),
    ("Cambio de correa de distribución", "Mecánica General", 350.00, 180, "taller"),
    ("Reparación de transmisión", "Mecánica General", 500.00, 240, "taller"),
    # Electricidad
    ("Diagnóstico de sistema eléctrico", "Electricidad", 80.00, 45, "taller"),
    ("Cambio de alternador", "Electricidad", 250.00, 90, "taller"),
    ("Reparación de arranque", "Electricidad", 200.00, 90, "taller"),
    ("Cambio de luces y faros", "Electricidad", 60.00, 30, "taller"),
    ("Reparación de cableado eléctrico", "Electricidad", 150.00, 120, "taller"),
    # Electrónica
    ("Diagnóstico de ECU", "Electrónica", 150.00, 60, "taller"),
    ("Reprogramación de computadora", "Electrónica", 300.00, 120, "taller"),
    ("Cambio de sensores electrónicos", "Electrónica", 200.00, 60, "taller"),
    ("Reparación de tablero digital", "Electrónica", 250.00, 90, "taller"),
    # Chapería y Pintura
    ("Enderezado de carrocería", "Chapería y Pintura", 400.00, 240, "taller"),
    ("Pintura parcial", "Chapería y Pintura", 350.00, 180, "taller"),
    ("Pintura completa", "Chapería y Pintura", 800.00, 480, "taller"),
    ("Reparación de abolladuras", "Chapería y Pintura", 250.00, 120, "taller"),
    # Remolque
    ("Servicio de grúa local", "Remolque", 100.00, 30, "domicilio"),
    ("Remolque interurbano", "Remolque", 200.00, 60, "domicilio"),
    ("Remolque de emergencia 24h", "Remolque", 150.00, 45, "domicilio"),
    # Llantas / Vulcanización
    ("Cambio de llantas", "Llantas / Vulcanización", 60.00, 20, "ambas"),
    ("Reparación de pinchazos", "Llantas / Vulcanización", 40.00, 20, "ambas"),
    ("Balanceo de llantas", "Llantas / Vulcanización", 50.00, 30, "taller"),
    ("Alineación de dirección", "Llantas / Vulcanización", 70.00, 45, "taller"),
    # Batería
    ("Cambio de batería", "Batería", 120.00, 20, "ambas"),
    ("Paso de corriente de emergencia", "Batería", 50.00, 15, "domicilio"),
    ("Diagnóstico de sistema de carga", "Batería", 60.00, 30, "taller"),
    # Motor
    ("Reparación mayor de motor", "Motor", 800.00, 480, "taller"),
    ("Reparación menor de motor", "Motor", 400.00, 240, "taller"),
    ("Cambio de empaque de culata", "Motor", 600.00, 360, "taller"),
    ("Afinación de motor", "Motor", 250.00, 120, "taller"),
    # Frenos
    ("Cambio de pastillas de freno", "Frenos", 120.00, 45, "taller"),
    ("Cambio de discos de freno", "Frenos", 200.00, 90, "taller"),
    ("Reparación de sistema de frenos", "Frenos", 180.00, 90, "taller"),
    ("Cambio de líquido de frenos", "Frenos", 60.00, 30, "taller"),
    # Suspensión y Dirección
    ("Cambio de amortiguadores", "Suspensión y Dirección", 250.00, 120, "taller"),
    ("Reparación de dirección", "Suspensión y Dirección", 200.00, 90, "taller"),
    ("Cambio de rótulas y terminales", "Suspensión y Dirección", 180.00, 90, "taller"),
    ("Alineación y balanceo", "Suspensión y Dirección", 80.00, 45, "taller"),
    # Aire Acondicionado
    ("Carga de gas de aire acondicionado", "Aire Acondicionado", 120.00, 60, "taller"),
    ("Reparación de compresor de AC", "Aire Acondicionado", 350.00, 180, "taller"),
    ("Diagnóstico de aire acondicionado", "Aire Acondicionado", 80.00, 45, "taller"),
]


async def seed(execute: bool = False):
    settings = get_settings()
    print(f"Conectando a: {settings.sqlalchemy_database_url[:60]}...")

    engine = get_engine()
    factory = get_session_factory()

    async with factory() as session:
        # --- Step 1: Seed categorias si no hay ---
        result = await session.execute(select(func.count(Categoria.id)))
        cat_count = result.scalar_one()
        if cat_count == 0:
            print("Creando categorias base...")
            cat_names = sorted({c[1] for c in SERVICIOS_BASE})
            for name in cat_names:
                session.add(Categoria(nombre=name))
            await session.flush()
            print(f"  Creadas {len(cat_names)} categorias.")

        # --- Step 2: Seed servicios si no hay ---
        result = await session.execute(select(func.count(Servicio.id)))
        svc_count = result.scalar_one()
        if svc_count == 0:
            print("Creando servicios base...")
            result = await session.execute(select(Categoria))
            cat_map = {c.nombre: c.id for c in result.scalars().all()}
            for nombre, cat_nombre, _, _, _ in SERVICIOS_BASE:
                cid = cat_map.get(cat_nombre)
                if cid:
                    session.add(Servicio(nombre=nombre, categoria_id=cid))
            await session.flush()
            print(f"  Creados {len(SERVICIOS_BASE)} servicios.")

        # --- Step 3: Obtener talleres ---
        result = await session.execute(
            select(Workshop)
            .join(Tenant, Workshop.tenant_id == Tenant.id)
            .where(Workshop.is_active == True, Tenant.status == "active")
            .options(selectinload(Workshop.tenant))
        )
        workshops = result.scalars().all()
        print(f"Talleres activos: {len(workshops)}")
        if not workshops:
            print("No hay talleres activos.")
            return

        # --- Step 4: Obtener servicios y categorias frescos ---
        result = await session.execute(
            select(Servicio, Categoria.nombre)
            .join(Categoria, Servicio.categoria_id == Categoria.id)
            .order_by(Categoria.nombre)
        )
        servicios = result.all()
        print(f"Servicios disponibles: {len(servicios)}")

        total_creados = 0
        total_existentes = 0

        for workshop in workshops:
            tid = workshop.tenant_id

            result = await session.execute(
                select(ServicioTaller.servicio_id)
                .where(ServicioTaller.taller_id == workshop.id)
            )
            existentes = {row[0] for row in result.all()}

            creados_taller = 0
            for svc, cat_nombre in servicios:
                if svc.id in existentes:
                    total_existentes += 1
                    continue

                data = next(
                    ((p, t, m) for n, cn, p, t, m in SERVICIOS_BASE if n == svc.nombre and cn == cat_nombre),
                    (100.0, 60, "taller"),
                )
                precio, tiempo, modalidad = data

                item = ServicioTaller(
                    taller_id=workshop.id,
                    servicio_id=svc.id,
                    tenant_id=tid,
                    precio=precio,
                    tiempo_estimado_min=tiempo,
                    modalidad=modalidad,
                    is_active=True,
                )
                if execute:
                    session.add(item)
                creados_taller += 1

            total_creados += creados_taller

            print(
                f"  {workshop.workshop_name}: "
                f"+{creados_taller} nuevos "
                f"(ya tenia {len(existentes)})"
            )

        if execute:
            await session.commit()
            print(f"\nCreados {total_creados} servicios_taller.")
            print(f"Ya existian {total_existentes}.")
        else:
            print(f"\n[DRY RUN] Se habrian creado {total_creados} servicios_taller.")
            print(f"[DRY RUN] Ya existen {total_existentes}.")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv or "--dry" in sys.argv
    asyncio.run(seed(execute=not dry))
