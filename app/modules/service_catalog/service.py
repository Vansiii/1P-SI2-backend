import json
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.servicio_taller import ServicioTaller
from app.models.servicio import Servicio
from app.models.categoria import Categoria
from app.models.workshop import Workshop
from app.models.tenant import Tenant
from app.models.tenant_subscription import TenantSubscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.audit_log import AuditLog

logger = get_logger(__name__)


class ServiceCatalogService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_workshop_id(self, tenant_id: int) -> int:
        tenant = await self.session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError("Tenant no encontrado")
        return tenant.workshop_id

    async def _get_plan_limit(self, tenant_id: int) -> int:
        result = await self.session.execute(
            select(SubscriptionPlan.max_services)
            .join(TenantSubscription, TenantSubscription.plan_id == SubscriptionPlan.id)
            .where(
                TenantSubscription.tenant_id == tenant_id,
                TenantSubscription.status.in_([
                    "active", "trialing", "past_due",
                    "pending_downgrade", "pending_cancellation",
                ]),
            )
        )
        return result.scalar_one_or_none() or 10

    async def _count_active_items(self, tenant_id: int) -> int:
        result = await self.session.execute(
            select(func.count(ServicioTaller.id))
            .where(
                ServicioTaller.tenant_id == tenant_id,
                ServicioTaller.is_active == True,
                ServicioTaller.deleted_at == None,
            )
        )
        return result.scalar_one()

    async def get_catalog(self, tenant_id: int) -> list[dict]:
        workshop_id = await self._get_workshop_id(tenant_id)

        result = await self.session.execute(
            select(ServicioTaller)
            .where(
                ServicioTaller.tenant_id == tenant_id,
                ServicioTaller.deleted_at == None,
            )
            .options(
                selectinload(ServicioTaller.servicio).selectinload(Servicio.categoria)
            )
            .order_by(ServicioTaller.is_active.desc(), ServicioTaller.id.asc())
        )
        items = result.scalars().all()
        return [self._to_item_response(item) for item in items]

    async def get_item(self, tenant_id: int, item_id: int) -> Optional[dict]:
        result = await self.session.execute(
            select(ServicioTaller)
            .where(
                ServicioTaller.id == item_id,
                ServicioTaller.tenant_id == tenant_id,
                ServicioTaller.deleted_at == None,
            )
            .options(
                selectinload(ServicioTaller.servicio).selectinload(Servicio.categoria)
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            return None
        return self._to_item_response(item)

    async def create_item(
        self, tenant_id: int, user_id: int, data: dict
    ) -> dict:
        workshop_id = await self._get_workshop_id(tenant_id)

        existing = await self.session.execute(
            select(ServicioTaller).where(
                ServicioTaller.tenant_id == tenant_id,
                ServicioTaller.servicio_id == data["servicio_id"],
                ServicioTaller.deleted_at == None,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Ya tienes este servicio en tu catalogo")

        plan_limit = await self._get_plan_limit(tenant_id)
        active_count = await self._count_active_items(tenant_id)
        if active_count >= plan_limit:
            raise ValueError(
                f"Has alcanzado el limite de {plan_limit} servicios de tu plan. "
                "Actualiza tu plan para agregar mas."
            )

        servicio = await self.session.get(Servicio, data["servicio_id"])
        if not servicio:
            raise ValueError("Servicio no encontrado")

        item = ServicioTaller(
            taller_id=workshop_id,
            servicio_id=data["servicio_id"],
            tenant_id=tenant_id,
            modalidad=data.get("modalidad", "taller"),
            tiempo_estimado_min=data.get("tiempo_estimado_min"),
            precio=data.get("precio"),
            descripcion=data.get("descripcion"),
            is_active=bool(data.get("is_active", True)),
        )
        self.session.add(item)

        self.session.add(AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="catalog_item_created",
            resource_type="service_catalog",
            resource_id=item.id,
            ip_address="system",
            details=json.dumps({
                "servicio_id": data["servicio_id"],
                "modalidad": data.get("modalidad"),
                "precio": data.get("precio"),
            }, default=str),
        ))

        await self.session.flush()
        await self.session.refresh(item)

        result = await self.session.execute(
            select(ServicioTaller)
            .where(ServicioTaller.id == item.id)
            .options(
                selectinload(ServicioTaller.servicio).selectinload(Servicio.categoria)
            )
        )
        return self._to_item_response(result.scalar_one())

    async def update_item(
        self, tenant_id: int, item_id: int, user_id: int, data: dict
    ) -> dict:
        result = await self.session.execute(
            select(ServicioTaller)
            .where(
                ServicioTaller.id == item_id,
                ServicioTaller.tenant_id == tenant_id,
                ServicioTaller.deleted_at == None,
            )
            .options(
                selectinload(ServicioTaller.servicio).selectinload(Servicio.categoria)
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise ValueError("Servicio no encontrado en tu catalogo")

        changed = {}
        for field in ("modalidad", "tiempo_estimado_min", "precio", "descripcion"):
            if field in data and data[field] is not None:
                setattr(item, field, data[field])
                changed[field] = data[field]

        if changed:
            self.session.add(AuditLog(
                user_id=user_id,
                tenant_id=tenant_id,
                action="catalog_item_updated",
                resource_type="service_catalog",
                resource_id=item.id,
                ip_address="system",
                details=json.dumps(changed, default=str),
            ))

        await self.session.flush()
        await self.session.refresh(item)
        return self._to_item_response(item)

    async def toggle_item(
        self, tenant_id: int, item_id: int, user_id: int
    ) -> dict:
        result = await self.session.execute(
            select(ServicioTaller)
            .where(
                ServicioTaller.id == item_id,
                ServicioTaller.tenant_id == tenant_id,
                ServicioTaller.deleted_at == None,
            )
            .options(
                selectinload(ServicioTaller.servicio).selectinload(Servicio.categoria)
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise ValueError("Servicio no encontrado en tu catalogo")

        new_state = not item.is_active
        if not new_state:
            active_count = await self.session.execute(
                select(func.count(ServicioTaller.id))
                .where(
                    ServicioTaller.tenant_id == tenant_id,
                    ServicioTaller.is_active == True,
                    ServicioTaller.deleted_at == None,
                    ServicioTaller.id != item_id,
                )
            )
            if active_count.scalar_one() == 0:
                raise ValueError(
                    "No puedes desactivar tu unico servicio activo. "
                    "Debes tener al menos un servicio activo en tu catalogo."
                )

        item.is_active = new_state

        self.session.add(AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="catalog_item_toggled",
            resource_type="service_catalog",
            resource_id=item.id,
            ip_address="system",
            details=json.dumps({"is_active": new_state}),
        ))

        await self.session.flush()
        await self.session.refresh(item)
        return self._to_item_response(item)

    async def delete_item(
        self, tenant_id: int, item_id: int, user_id: int
    ) -> None:
        result = await self.session.execute(
            select(ServicioTaller)
            .where(
                ServicioTaller.id == item_id,
                ServicioTaller.tenant_id == tenant_id,
                ServicioTaller.deleted_at == None,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise ValueError("Servicio no encontrado en tu catalogo")

        from app.models.incidente import Incidente
        from datetime import datetime, timezone

        active_incidents = await self.session.execute(
            select(func.count(Incidente.id))
            .where(
                Incidente.taller_id == item.taller_id,
                Incidente.estado_actual.in_([
                    "pendiente", "asignado", "en_proceso",
                ]),
            )
        )
        if active_incidents.scalar_one() > 0:
            raise ValueError(
                "No puedes eliminar este servicio porque tienes incidentes activos. "
                "Te sugerimos desactivarlo en su lugar."
            )

        item.deleted_at = datetime.now(timezone.utc)

        self.session.add(AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="catalog_item_deleted",
            resource_type="service_catalog",
            resource_id=item.id,
            ip_address="system",
        ))

        await self.session.flush()

    @staticmethod
    def _to_item_response(item: ServicioTaller) -> dict:
        servicio = item.servicio
        categoria = servicio.categoria if servicio else None
        return {
            "id": item.id,
            "servicio_id": item.servicio_id,
            "servicio_nombre": servicio.nombre if servicio else "",
            "categoria_id": categoria.id if categoria else 0,
            "categoria_nombre": categoria.nombre if categoria else "",
            "modalidad": item.modalidad,
            "tiempo_estimado_min": item.tiempo_estimado_min,
            "precio": float(item.precio) if item.precio else None,
            "descripcion": item.descripcion,
            "is_active": item.is_active,
        }

    async def get_categories(self) -> list[dict]:
        result = await self.session.execute(
            select(Categoria).order_by(Categoria.nombre)
        )
        categorias = result.scalars().all()
        return [
            {
                "id": c.id,
                "nombre": c.nombre,
                "descripcion": c.descripcion,
                "icon": c.icon,
            }
            for c in categorias
        ]

    async def get_base_services(self) -> list[dict]:
        result = await self.session.execute(
            select(Servicio, Categoria.nombre)
            .join(Categoria, Servicio.categoria_id == Categoria.id)
            .order_by(Categoria.nombre, Servicio.nombre)
        )
        rows = result.all()
        return [
            {
                "id": s.id,
                "nombre": s.nombre,
                "descripcion": s.descripcion,
                "categoria_id": s.categoria_id,
                "categoria_nombre": cat_nombre,
            }
            for s, cat_nombre in rows
        ]
