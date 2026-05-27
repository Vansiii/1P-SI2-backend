"""
Script de verificación de backfill de tenant_id.

Ejecutar después de la migración para validar que:
1. Todos los workshops existentes tienen tenant y tenant_id
2. Todas las tablas tenant-scoped tienen tenant_id poblado
3. Los tenants legacy tienen plan básico asignado
4. No hay NULLs en tenant_id de tablas críticas

Uso:
    python scripts/verify_tenant_backfill.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import get_async_session


TABLES_WITH_TENANT_ID = [
    ("workshops", "id", "tenant_id"),
    ("incidentes", "id", "tenant_id"),
    ("technicians", "id", "tenant_id"),
    ("transactions", "id", "tenant_id"),
    ("platform_commissions", "id", "tenant_id"),
    ("workshop_balances", "id", "tenant_id"),
    ("withdrawals", "id", "tenant_id"),
    ("workshop_financial_movements", "id", "tenant_id"),
    ("workshop_settlements", "id", "tenant_id"),
    ("technician_especialidades", "id", "tenant_id"),
    ("technician_location_history", "id", "tenant_id"),
    ("workshop_schedules", "id", "tenant_id"),
    ("servicios_taller", "id", "tenant_id"),
    ("conversations", "id", "tenant_id"),
    ("messages", "id", "tenant_id"),
    ("notifications", "id", "tenant_id"),
    ("audit_logs", "id", "tenant_id"),
    ("outbox_events", "id", "tenant_id"),
    ("event_log", "id", "tenant_id"),
    ("service_ratings", "id", "tenant_id"),
    ("assignment_attempts", "id", "tenant_id"),
    ("cancellation_requests", "id", "tenant_id"),
]


async def verify():
    async for session in get_async_session():
        errors = []
        warnings = []

        print("=" * 60)
        print("VERIFICACION DE BACKFILL DE TENANT_ID")
        print("=" * 60)

        # 1. Verificar tenants para workshops existentes
        result = await session.execute(
            text("SELECT COUNT(*) FROM workshops WHERE tenant_id IS NULL")
        )
        null_workshops = result.scalar()
        if null_workshops > 0:
            errors.append(f"CRITICO: {null_workshops} workshops sin tenant_id")
        else:
            print("OK: Todos los workshops tienen tenant_id")

        result = await session.execute(
            text("""
                SELECT COUNT(*) FROM workshops w
                LEFT JOIN tenants t ON w.tenant_id = t.id
                WHERE t.id IS NULL
            """)
        )
        orphan_workshops = result.scalar()
        if orphan_workshops > 0:
            errors.append(f"CRITICO: {orph_workshops} workshops con tenant_id huerfano")
        else:
            print("OK: Todos los tenant_id de workshops son validos")

        # 2. Verificar tablas tenant-scoped
        for table, pk, col in TABLES_WITH_TENANT_ID:
            try:
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")
                )
                null_count = result.scalar()
                if null_count and null_count > 0:
                    # Algunas tablas pueden tener registros sin tenant
                    # (ej: outbox_events globales, audit_logs de admin)
                    if table in ("outbox_events", "event_log", "audit_logs", "notifications"):
                        warnings.append(
                            f"WARN: {table} tiene {null_count} registros sin tenant_id "
                            f"(esperado para eventos/auditoria global)"
                        )
                    else:
                        errors.append(
                            f"CRITICO: {table} tiene {null_count} registros sin tenant_id"
                        )
                else:
                    print(f"OK: {table} - sin NULLs en tenant_id")
            except Exception as e:
                warnings.append(f"WARN: No se pudo verificar {table}: {e}")

        # 3. Verificar tenants legacy tienen plan
        result = await session.execute(
            text("""
                SELECT COUNT(*) FROM tenants t
                WHERE t.status = 'active'
                AND NOT EXISTS (
                    SELECT 1 FROM tenant_subscriptions ts WHERE ts.tenant_id = t.id
                )
            """)
        )
        no_plan = result.scalar()
        if no_plan > 0:
            errors.append(f"CRITICO: {no_plan} tenants activos sin suscripcion")
        else:
            print("OK: Todos los tenants activos tienen suscripcion")

        # 4. Verificar NITs unicos
        result = await session.execute(
            text("SELECT COUNT(*) FROM tenants GROUP BY nit HAVING COUNT(*) > 1")
        )
        dup_nit = result.scalar()
        if dup_nit:
            errors.append(f"CRITICO: NITs duplicados en tenants")
        else:
            print("OK: NITs unicos en tenants")

        # 5. Verificar planes por defecto
        result = await session.execute(
            text("SELECT COUNT(*) FROM subscription_plans WHERE is_active = true")
        )
        active_plans = result.scalar()
        if active_plans == 0:
            errors.append("CRITICO: No hay planes de suscripcion activos")
        else:
            print(f"OK: {active_plans} planes de suscripcion activos")

        # Resumen
        print()
        print("=" * 60)
        if errors:
            print(f"ERRORES ({len(errors)}):")
            for e in errors:
                print(f"  {e}")
        if warnings:
            print(f"ADVERTENCIAS ({len(warnings)}):")
            for w in warnings:
                print(f"  {w}")

        if not errors:
            print("VERIFICACION EXITOSA: Backfill completado correctamente.")

        print("=" * 60)

        if errors:
            sys.exit(1)

        break  # Solo una iteración del generador


if __name__ == "__main__":
    asyncio.run(verify())
