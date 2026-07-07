import json
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import get_logger
from app.models.supplier import Supplier
from app.models.inventory_product import InventoryProduct
from app.models.audit_log import AuditLog

logger = get_logger(__name__)


class SupplierService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_suppliers(self, tenant_id: int) -> list[dict]:
        result = await self.session.execute(
            select(Supplier)
            .where(Supplier.tenant_id == tenant_id)
            .order_by(Supplier.name.asc())
        )
        suppliers = result.scalars().all()
        return [self._to_supplier_response(s) for s in suppliers]

    async def get_supplier(self, tenant_id: int, supplier_id: int) -> Optional[dict]:
        result = await self.session.execute(
            select(Supplier).where(
                Supplier.id == supplier_id,
                Supplier.tenant_id == tenant_id
            )
        )
        supplier = result.scalar_one_or_none()
        if not supplier:
            return None
        return self._to_supplier_response(supplier)

    async def create_supplier(self, tenant_id: int, user_id: int, data: dict) -> dict:
        # Validar unicidad del nombre por tenant
        existing = await self.session.execute(
            select(Supplier).where(
                Supplier.tenant_id == tenant_id,
                Supplier.name == data["name"]
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Ya existe un proveedor con el nombre '{data['name']}'")

        supplier = Supplier(
            tenant_id=tenant_id,
            name=data["name"],
            contact_name=data.get("contact_name"),
            email=data.get("email"),
            phone=data.get("phone"),
            address=data.get("address"),
            city=data.get("city"),
            country=data.get("country", "Bolivia"),
            tax_id=data.get("tax_id"),
            notes=data.get("notes"),
            is_active=True
        )
        self.session.add(supplier)
        await self.session.flush()
        await self.session.refresh(supplier)

        # AuditLog
        self.session.add(AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="supplier_created",
            resource_type="supplier",
            resource_id=supplier.id,
            ip_address="system",
            details=json.dumps({"name": supplier.name}, default=str)
        ))

        return self._to_supplier_response(supplier)

    async def update_supplier(self, tenant_id: int, supplier_id: int, user_id: int, data: dict) -> dict:
        result = await self.session.execute(
            select(Supplier).where(
                Supplier.id == supplier_id,
                Supplier.tenant_id == tenant_id
            )
        )
        supplier = result.scalar_one_or_none()
        if not supplier:
            raise ValueError("Proveedor no encontrado")

        if "name" in data and data["name"] != supplier.name:
            existing = await self.session.execute(
                select(Supplier).where(
                    Supplier.tenant_id == tenant_id,
                    Supplier.name == data["name"],
                    Supplier.id != supplier_id
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Ya existe otro proveedor con el nombre '{data['name']}'")

        changed = {}
        for field in ("name", "contact_name", "email", "phone", "address", "city", "country", "tax_id", "notes", "is_active"):
            if field in data and data[field] is not None:
                setattr(supplier, field, data[field])
                changed[field] = data[field]

        if changed:
            await self.session.flush()
            self.session.add(AuditLog(
                user_id=user_id,
                tenant_id=tenant_id,
                action="supplier_updated",
                resource_type="supplier",
                resource_id=supplier.id,
                ip_address="system",
                details=json.dumps(changed, default=str)
            ))

        return self._to_supplier_response(supplier)

    async def delete_supplier(self, tenant_id: int, supplier_id: int, user_id: int) -> None:
        result = await self.session.execute(
            select(Supplier).where(
                Supplier.id == supplier_id,
                Supplier.tenant_id == tenant_id
            )
        )
        supplier = result.scalar_one_or_none()
        if not supplier:
            raise ValueError("Proveedor no encontrado")

        # Verificar si hay productos que lo usan
        products_count = await self.session.execute(
            select(func.count(InventoryProduct.id)).where(
                InventoryProduct.supplier_id == supplier_id,
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.deleted_at == None
            )
        )
        if products_count.scalar_one() > 0:
            raise ValueError("No se puede eliminar el proveedor porque tiene productos asociados. Desactívelo en su lugar.")

        await self.session.delete(supplier)
        await self.session.flush()

        self.session.add(AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="supplier_deleted",
            resource_type="supplier",
            resource_id=supplier_id,
            ip_address="system"
        ))

    async def get_supplier_products(self, tenant_id: int, supplier_id: int) -> list[dict]:
        result = await self.session.execute(
            select(InventoryProduct).where(
                InventoryProduct.supplier_id == supplier_id,
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.deleted_at == None
            )
        )
        products = result.scalars().all()
        return [
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "brand": p.brand,
                "current_stock": p.current_stock,
                "cost_price": float(p.cost_price)
            } for p in products
        ]

    def _to_supplier_response(self, s: Supplier) -> dict:
        return {
            "id": s.id,
            "tenant_id": s.tenant_id,
            "name": s.name,
            "contact_name": s.contact_name,
            "email": s.email,
            "phone": s.phone,
            "address": s.address,
            "city": s.city,
            "country": s.country,
            "tax_id": s.tax_id,
            "notes": s.notes,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None
        }
