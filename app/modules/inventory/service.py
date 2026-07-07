import json
from typing import Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.inventory_category import InventoryCategory
from app.models.supplier import Supplier
from app.models.inventory_product import InventoryProduct
from app.models.inventory_movement import InventoryMovement
from app.models.stock_alert import StockAlert
from app.models.tenant import Tenant
from app.models.audit_log import AuditLog

logger = get_logger(__name__)


class InventoryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_workshop_id(self, tenant_id: int) -> int:
        tenant = await self.session.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError("Tenant no encontrado")
        return tenant.workshop_id

    async def list_products(self, tenant_id: int, filters: dict) -> Tuple[list[dict], int]:
        query = select(InventoryProduct).where(
            InventoryProduct.tenant_id == tenant_id,
            InventoryProduct.deleted_at == None
        )

        if filters.get("search"):
            search_pattern = f"%{filters['search']}%"
            query = query.where(
                or_(
                    InventoryProduct.name.ilike(search_pattern),
                    InventoryProduct.brand.ilike(search_pattern),
                    InventoryProduct.sku.ilike(search_pattern),
                    InventoryProduct.part_number.ilike(search_pattern)
                )
            )

        if filters.get("category_id"):
            query = query.where(InventoryProduct.category_id == filters["category_id"])

        if filters.get("supplier_id"):
            query = query.where(InventoryProduct.supplier_id == filters["supplier_id"])

        if filters.get("low_stock"):
            query = query.where(InventoryProduct.current_stock <= InventoryProduct.min_stock)

        if filters.get("out_of_stock"):
            query = query.where(InventoryProduct.current_stock == 0)

        if filters.get("is_published") is not None:
            query = query.where(InventoryProduct.is_published == filters["is_published"])

        if filters.get("is_active") is not None:
            query = query.where(InventoryProduct.is_active == filters["is_active"])

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginated results
        page = filters.get("page", 1)
        size = filters.get("size", 20)
        query = query.order_by(InventoryProduct.name.asc()).offset((page - 1) * size).limit(size)
        query = query.options(
            selectinload(InventoryProduct.category),
            selectinload(InventoryProduct.supplier)
        )
        
        result = await self.session.execute(query)
        products = result.scalars().all()

        return [self._to_product_response(p) for p in products], total

    async def get_product(self, tenant_id: int, product_id: int) -> Optional[dict]:
        result = await self.session.execute(
            select(InventoryProduct)
            .where(
                InventoryProduct.id == product_id,
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.deleted_at == None
            )
            .options(
                selectinload(InventoryProduct.category),
                selectinload(InventoryProduct.supplier)
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            return None
        return self._to_product_response(product)

    async def create_product(self, tenant_id: int, user_id: int, data: dict) -> dict:
        # Check SKU uniqueness if provided
        if data.get("sku"):
            existing = await self.session.execute(
                select(InventoryProduct).where(
                    InventoryProduct.tenant_id == tenant_id,
                    InventoryProduct.sku == data["sku"],
                    InventoryProduct.deleted_at == None
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Ya existe un producto con el SKU '{data['sku']}'")

        category_id = data.get("category_id")
        if category_id:
            category = await self.session.get(InventoryCategory, category_id)
            if not category or category.tenant_id != tenant_id:
                raise ValueError("Categoría inválida")

        supplier_id = data.get("supplier_id")
        if supplier_id:
            supplier = await self.session.get(Supplier, supplier_id)
            if not supplier or supplier.tenant_id != tenant_id:
                raise ValueError("Proveedor inválido")

        product = InventoryProduct(
            tenant_id=tenant_id,
            category_id=category_id,
            supplier_id=supplier_id,
            sku=data.get("sku"),
            barcode=data.get("barcode"),
            name=data["name"],
            description=data.get("description"),
            brand=data.get("brand"),
            part_number=data.get("part_number"),
            current_stock=data.get("current_stock", 0),
            min_stock=data.get("min_stock", 0),
            max_stock=data.get("max_stock"),
            unit=data.get("unit", "unidad"),
            location=data.get("location"),
            cost_price=data.get("cost_price", 0.0),
            avg_cost_price=data.get("cost_price", 0.0),
            compatible_brands=data.get("compatible_brands", []),
            compatible_models=data.get("compatible_models", []),
            compatible_years=data.get("compatible_years"),
            universal=data.get("universal", False),
            image_url=data.get("image_url"),
            images=data.get("images", []),
            is_active=True,
            is_published=False
        )

        self.session.add(product)
        await self.session.flush()
        await self.session.refresh(product)

        # AuditLog
        self.session.add(AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="inventory_product_created",
            resource_type="inventory_product",
            resource_id=product.id,
            ip_address="system",
            details=json.dumps({"name": product.name, "sku": product.sku, "initial_stock": product.current_stock}, default=str)
        ))

        # Registrar movimiento inicial si hay stock
        if product.current_stock > 0:
            movement = InventoryMovement(
                tenant_id=tenant_id,
                product_id=product.id,
                type="entrada",
                quantity=product.current_stock,
                unit_cost=product.cost_price,
                total_cost=product.current_stock * product.cost_price,
                reference_type="registro_inicial",
                stock_before=0,
                stock_after=product.current_stock,
                notes="Registro inicial de stock al crear producto",
                created_by=user_id
            )
            self.session.add(movement)

            # Validar alertas de bajo stock
            if product.current_stock <= product.min_stock:
                alert = StockAlert(
                    tenant_id=tenant_id,
                    product_id=product.id,
                    alert_type="low_stock" if product.current_stock > 0 else "out_of_stock",
                    current_stock=product.current_stock,
                    threshold=product.min_stock,
                    is_read=False,
                    is_resolved=False
                )
                self.session.add(alert)

            await self.session.flush()

        # Refresh to get relations
        result = await self.session.execute(
            select(InventoryProduct)
            .where(InventoryProduct.id == product.id)
            .options(
                selectinload(InventoryProduct.category),
                selectinload(InventoryProduct.supplier)
            )
        )
        return self._to_product_response(result.scalar_one())

    async def update_product(self, tenant_id: int, product_id: int, user_id: int, data: dict) -> dict:
        result = await self.session.execute(
            select(InventoryProduct).where(
                InventoryProduct.id == product_id,
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.deleted_at == None
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise ValueError("Producto no encontrado")

        if data.get("sku") and data["sku"] != product.sku:
            existing = await self.session.execute(
                select(InventoryProduct).where(
                    InventoryProduct.tenant_id == tenant_id,
                    InventoryProduct.sku == data["sku"],
                    InventoryProduct.deleted_at == None,
                    InventoryProduct.id != product_id
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Ya existe otro producto con el SKU '{data['sku']}'")

        category_id = data.get("category_id")
        if category_id:
            category = await self.session.get(InventoryCategory, category_id)
            if not category or category.tenant_id != tenant_id:
                raise ValueError("Categoría inválida")

        supplier_id = data.get("supplier_id")
        if supplier_id:
            supplier = await self.session.get(Supplier, supplier_id)
            if not supplier or supplier.tenant_id != tenant_id:
                raise ValueError("Proveedor inválido")

        changed = {}
        for field in ("name", "description", "sku", "barcode", "brand", "part_number", "category_id", "supplier_id", "min_stock", "max_stock", "unit", "location", "cost_price", "compatible_brands", "compatible_models", "compatible_years", "universal", "image_url", "images"):
            if field in data and data[field] is not None:
                setattr(product, field, data[field])
                changed[field] = data[field]

        if changed:
            await self.session.flush()
            self.session.add(AuditLog(
                user_id=user_id,
                tenant_id=tenant_id,
                action="inventory_product_updated",
                resource_type="inventory_product",
                resource_id=product.id,
                ip_address="system",
                details=json.dumps(changed, default=str)
            ))

        # Check if min_stock was updated, recheck low stock alert
        if "min_stock" in data:
            if product.current_stock <= product.min_stock:
                # Buscar si ya existe una alerta activa para evitar duplicados
                alert_exists = await self.session.execute(
                    select(StockAlert).where(
                        StockAlert.product_id == product.id,
                        StockAlert.tenant_id == tenant_id,
                        StockAlert.is_resolved == False
                    )
                )
                if not alert_exists.scalar_one_or_none():
                    alert = StockAlert(
                        tenant_id=tenant_id,
                        product_id=product.id,
                        alert_type="low_stock" if product.current_stock > 0 else "out_of_stock",
                        current_stock=product.current_stock,
                        threshold=product.min_stock,
                        is_read=False,
                        is_resolved=False
                    )
                    self.session.add(alert)
            else:
                # Resolver alertas activas
                await self.session.execute(
                    func.update(StockAlert)
                    .where(
                        StockAlert.product_id == product.id,
                        StockAlert.tenant_id == tenant_id,
                        StockAlert.is_resolved == False
                    )
                    .values(is_resolved=True, resolved_at=datetime.now(timezone.utc))
                )

        # Refresh
        result = await self.session.execute(
            select(InventoryProduct)
            .where(InventoryProduct.id == product.id)
            .options(
                selectinload(InventoryProduct.category),
                selectinload(InventoryProduct.supplier)
            )
        )
        return self._to_product_response(result.scalar_one())

    async def delete_product(self, tenant_id: int, product_id: int, user_id: int) -> None:
        result = await self.session.execute(
            select(InventoryProduct).where(
                InventoryProduct.id == product_id,
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.deleted_at == None
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise ValueError("Producto no encontrado")

        product.deleted_at = datetime.now(timezone.utc)
        self.session.add(AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="inventory_product_deleted",
            resource_type="inventory_product",
            resource_id=product_id,
            ip_address="system"
        ))

    async def create_movement(self, tenant_id: int, user_id: int, data: dict) -> dict:
        product_id = data["product_id"]
        result = await self.session.execute(
            select(InventoryProduct).where(
                InventoryProduct.id == product_id,
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.deleted_at == None
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise ValueError("Producto no encontrado")

        m_type = data["type"]
        qty = data["quantity"]
        stock_before = product.current_stock
        unit_cost = data.get("unit_cost")

        if m_type == "entrada":
            # Calcular costo promedio ponderado
            old_stock = product.current_stock
            old_avg_cost = float(product.avg_cost_price)
            new_qty = qty
            
            # Si el stock previo es <= 0, el nuevo costo promedio es el unit_cost
            if old_stock <= 0:
                new_avg_cost = float(unit_cost)
            else:
                new_avg_cost = ((old_stock * old_avg_cost) + (new_qty * float(unit_cost))) / (old_stock + new_qty)
            
            product.current_stock += qty
            product.avg_cost_price = new_avg_cost
            # Actualizar también costo actual
            product.cost_price = float(unit_cost)
            total_cost = float(unit_cost) * qty
        elif m_type in ("salida", "devolucion", "ajuste"):
            # En salida/devolucion/ajuste la cantidad puede reducir el stock.
            # En el schema, quantity viene positivo, por lo que determinamos si sumamos o restamos.
            # Si m_type es 'salida' -> restamos.
            # Si es ajuste, quantity puede restar stock. (Para este router, lo manejamos restando si es salida/ajuste)
            # Para simplificar: 'entrada' suma stock, 'salida' resta stock. 'devolucion' suma stock. 'ajuste' puede sumar o restar.
            # Definamos logicamente:
            if m_type == "salida":
                if product.current_stock < qty:
                    raise ValueError(f"Stock insuficiente. Stock actual: {product.current_stock}, Requerido: {qty}")
                product.current_stock -= qty
                qty_signed = -qty
            elif m_type == "devolucion":
                product.current_stock += qty
                qty_signed = qty
            elif m_type == "ajuste":
                # Para ajustes, interpretamos si el usuario indica entrada o salida.
                # En schemas.py definimos: InventoryMovementCreate.type, quantity (>0)
                # Como quantity es positivo, podemos asumir por defecto que un ajuste resta si no se especifica.
                # O podemos permitir que notes/reference aclare.
                # Asumamos que para ajuste, por simplicidad en schemas, resta stock.
                # Si quiere sumar, debería usar 'entrada'.
                if product.current_stock < qty:
                    raise ValueError(f"Stock insuficiente para ajuste. Stock actual: {product.current_stock}, Ajuste: {qty}")
                product.current_stock -= qty
                qty_signed = -qty
            
            unit_cost = float(product.avg_cost_price)
            total_cost = unit_cost * qty
            qty = qty_signed if m_type in ("salida", "ajuste") else qty
        else:
            raise ValueError("Tipo de movimiento inválido")

        stock_after = product.current_stock

        movement = InventoryMovement(
            tenant_id=tenant_id,
            product_id=product_id,
            type=m_type,
            quantity=qty,
            unit_cost=unit_cost,
            total_cost=total_cost,
            reference_type=data.get("reference_type"),
            reference_id=data.get("reference_id"),
            stock_before=stock_before,
            stock_after=stock_after,
            notes=data.get("notes"),
            created_by=user_id
        )

        self.session.add(movement)
        await self.session.flush()
        await self.session.refresh(movement)

        # Validar y crear alertas de stock
        if product.current_stock <= product.min_stock:
            # Buscar alerta activa
            alert_exists = await self.session.execute(
                select(StockAlert).where(
                    StockAlert.product_id == product.id,
                    StockAlert.tenant_id == tenant_id,
                    StockAlert.is_resolved == False
                )
            )
            if not alert_exists.scalar_one_or_none():
                alert = StockAlert(
                    tenant_id=tenant_id,
                    product_id=product.id,
                    alert_type="low_stock" if product.current_stock > 0 else "out_of_stock",
                    current_stock=product.current_stock,
                    threshold=product.min_stock,
                    is_read=False,
                    is_resolved=False
                )
                self.session.add(alert)
        else:
            # Si el stock subió, resolver alertas activas
            await self.session.execute(
                func.update(StockAlert)
                .where(
                    StockAlert.product_id == product.id,
                    StockAlert.tenant_id == tenant_id,
                    StockAlert.is_resolved == False
                )
                .values(is_resolved=True, resolved_at=datetime.now(timezone.utc))
            )

        # AuditLog
        self.session.add(AuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action="inventory_movement_created",
            resource_type="inventory_movement",
            resource_id=movement.id,
            ip_address="system",
            details=json.dumps({"product_id": product_id, "type": m_type, "quantity": qty, "stock_after": stock_after}, default=str)
        ))

        return self._to_movement_response(movement)

    async def list_movements(self, tenant_id: int, product_id: int | None = None, page: int = 1, size: int = 20) -> Tuple[list[dict], int]:
        query = select(InventoryMovement).where(InventoryMovement.tenant_id == tenant_id)
        if product_id:
            query = query.where(InventoryMovement.product_id == product_id)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(desc(InventoryMovement.created_at)).offset((page - 1) * size).limit(size)
        query = query.options(selectinload(InventoryMovement.product))
        result = await self.session.execute(query)
        movements = result.scalars().all()

        return [self._to_movement_response(m) for m in movements], total

    async def get_low_stock_products(self, tenant_id: int) -> list[dict]:
        result = await self.session.execute(
            select(InventoryProduct)
            .where(
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.current_stock <= InventoryProduct.min_stock,
                InventoryProduct.deleted_at == None,
                InventoryProduct.is_active == True
            )
            .options(
                selectinload(InventoryProduct.category),
                selectinload(InventoryProduct.supplier)
            )
        )
        return [self._to_product_response(p) for p in result.scalars().all()]

    async def get_out_of_stock_products(self, tenant_id: int) -> list[dict]:
        result = await self.session.execute(
            select(InventoryProduct)
            .where(
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.current_stock == 0,
                InventoryProduct.deleted_at == None,
                InventoryProduct.is_active == True
            )
            .options(
                selectinload(InventoryProduct.category),
                selectinload(InventoryProduct.supplier)
            )
        )
        return [self._to_product_response(p) for p in result.scalars().all()]

    async def get_dashboard(self, tenant_id: int) -> dict:
        # Total products count
        total_products_res = await self.session.execute(
            select(func.count(InventoryProduct.id)).where(
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.deleted_at == None
            )
        )
        total_products = total_products_res.scalar_one()

        # Low stock count
        low_stock_res = await self.session.execute(
            select(func.count(InventoryProduct.id)).where(
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.current_stock <= InventoryProduct.min_stock,
                InventoryProduct.deleted_at == None,
                InventoryProduct.is_active == True
            )
        )
        low_stock_count = low_stock_res.scalar_one()

        # Out of stock count
        out_of_stock_res = await self.session.execute(
            select(func.count(InventoryProduct.id)).where(
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.current_stock == 0,
                InventoryProduct.deleted_at == None,
                InventoryProduct.is_active == True
            )
        )
        out_of_stock_count = out_of_stock_res.scalar_one()

        # Total value (sum of current_stock * cost_price)
        total_value_res = await self.session.execute(
            select(func.sum(InventoryProduct.current_stock * InventoryProduct.cost_price)).where(
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.deleted_at == None
            )
        )
        total_value = float(total_value_res.scalar_one() or 0.0)

        # Categories count
        categories_res = await self.session.execute(
            select(func.count(InventoryCategory.id)).where(
                InventoryCategory.tenant_id == tenant_id,
                InventoryCategory.is_active == True
            )
        )
        categories_count = categories_res.scalar_one()

        # Recent movements (last 5)
        recent_movements_res = await self.session.execute(
            select(InventoryMovement)
            .where(InventoryMovement.tenant_id == tenant_id)
            .order_by(desc(InventoryMovement.created_at))
            .limit(5)
            .options(selectinload(InventoryMovement.product))
        )
        recent_movements = [self._to_movement_response(m) for m in recent_movements_res.scalars().all()]

        return {
            "total_products": total_products,
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,
            "total_value": total_value,
            "categories_count": categories_count,
            "recent_movements": recent_movements
        }

    async def list_categories(self, tenant_id: int) -> list[dict]:
        result = await self.session.execute(
            select(InventoryCategory)
            .where(InventoryCategory.tenant_id == tenant_id)
            .order_by(InventoryCategory.name.asc())
            .options(selectinload(InventoryCategory.parent))
        )
        categories = result.scalars().all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "icon": c.icon,
                "parent_id": c.parent_id,
                "parent_name": c.parent.name if c.parent else None,
                "is_active": c.is_active
            } for c in categories
        ]

    async def create_category(self, tenant_id: int, data: dict) -> dict:
        existing = await self.session.execute(
            select(InventoryCategory).where(
                InventoryCategory.tenant_id == tenant_id,
                InventoryCategory.name == data["name"],
                InventoryCategory.parent_id == data.get("parent_id")
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Ya existe una categoría '{data['name']}' bajo el mismo padre")

        parent_id = data.get("parent_id")
        if parent_id:
            parent = await self.session.get(InventoryCategory, parent_id)
            if not parent or parent.tenant_id != tenant_id:
                raise ValueError("Categoría padre inválida")

        category = InventoryCategory(
            tenant_id=tenant_id,
            name=data["name"],
            description=data.get("description"),
            icon=data.get("icon"),
            parent_id=parent_id,
            is_active=True
        )

        self.session.add(category)
        await self.session.flush()
        await self.session.refresh(category)

        return {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "icon": category.icon,
            "parent_id": category.parent_id,
            "is_active": category.is_active
        }

    async def update_category(self, tenant_id: int, category_id: int, data: dict) -> dict:
        category = await self.session.get(InventoryCategory, category_id)
        if not category or category.tenant_id != tenant_id:
            raise ValueError("Categoría no encontrada")

        if data.get("name") and (data["name"] != category.name or data.get("parent_id") != category.parent_id):
            existing = await self.session.execute(
                select(InventoryCategory).where(
                    InventoryCategory.tenant_id == tenant_id,
                    InventoryCategory.name == data["name"],
                    InventoryCategory.parent_id == data.get("parent_id", category.parent_id),
                    InventoryCategory.id != category_id
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Ya existe otra categoría '{data['name']}' bajo el mismo padre")

        parent_id = data.get("parent_id")
        if parent_id:
            if parent_id == category_id:
                raise ValueError("Una categoría no puede ser su propio padre")
            parent = await self.session.get(InventoryCategory, parent_id)
            if not parent or parent.tenant_id != tenant_id:
                raise ValueError("Categoría padre inválida")

        for field in ("name", "description", "icon", "parent_id", "is_active"):
            if field in data and data[field] is not None:
                setattr(category, field, data[field])

        await self.session.flush()
        await self.session.refresh(category)

        return {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "icon": category.icon,
            "parent_id": category.parent_id,
            "is_active": category.is_active
        }

    async def delete_category(self, tenant_id: int, category_id: int) -> None:
        category = await self.session.get(InventoryCategory, category_id)
        if not category or category.tenant_id != tenant_id:
            raise ValueError("Categoría no encontrada")

        # Verificar si hay subcategorías
        subcats = await self.session.execute(
            select(func.count(InventoryCategory.id)).where(
                InventoryCategory.parent_id == category_id,
                InventoryCategory.tenant_id == tenant_id
            )
        )
        if subcats.scalar_one() > 0:
            raise ValueError("No se puede eliminar la categoría porque tiene subcategorías asociadas")

        # Verificar si hay productos
        products = await self.session.execute(
            select(func.count(InventoryProduct.id)).where(
                InventoryProduct.category_id == category_id,
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.deleted_at == None
            )
        )
        if products.scalar_one() > 0:
            raise ValueError("No se puede eliminar la categoría porque tiene productos asociados")

        await self.session.delete(category)
        await self.session.flush()

    async def list_alerts(self, tenant_id: int, unread_only: bool = True) -> list[dict]:
        query = select(StockAlert).where(StockAlert.tenant_id == tenant_id)
        if unread_only:
            query = query.where(StockAlert.is_read == False)
        
        query = query.order_by(desc(StockAlert.created_at)).options(
            selectinload(StockAlert.product)
        )
        result = await self.session.execute(query)
        alerts = result.scalars().all()
        return [
            {
                "id": a.id,
                "product_id": a.product_id,
                "product_name": a.product.name if a.product else "",
                "product_sku": a.product.sku if a.product else "",
                "alert_type": a.alert_type,
                "current_stock": a.current_stock,
                "threshold": a.threshold,
                "is_read": a.is_read,
                "is_resolved": a.is_resolved,
                "created_at": a.created_at.isoformat() if a.created_at else None
            } for a in alerts
        ]

    async def mark_alert_read(self, tenant_id: int, alert_id: int) -> dict:
        alert = await self.session.get(StockAlert, alert_id)
        if not alert or alert.tenant_id != tenant_id:
            raise ValueError("Alerta no encontrada")
        
        alert.is_read = True
        await self.session.flush()
        return {
            "id": alert.id,
            "is_read": alert.is_read
        }

    async def mark_all_alerts_read(self, tenant_id: int) -> int:
        result = await self.session.execute(
            func.update(StockAlert)
            .where(
                StockAlert.tenant_id == tenant_id,
                StockAlert.is_read == False
            )
            .values(is_read=True)
        )
        return result.rowcount

    def _to_product_response(self, p: InventoryProduct) -> dict:
        return {
            "id": p.id,
            "tenant_id": p.tenant_id,
            "category_id": p.category_id,
            "category_name": p.category.name if p.category else None,
            "supplier_id": p.supplier_id,
            "supplier_name": p.supplier.name if p.supplier else None,
            "sku": p.sku,
            "barcode": p.barcode,
            "name": p.name,
            "description": p.description,
            "brand": p.brand,
            "part_number": p.part_number,
            "current_stock": p.current_stock,
            "min_stock": p.min_stock,
            "max_stock": p.max_stock,
            "unit": p.unit,
            "location": p.location,
            "cost_price": float(p.cost_price),
            "avg_cost_price": float(p.avg_cost_price),
            "compatible_brands": p.compatible_brands,
            "compatible_models": p.compatible_models,
            "compatible_years": p.compatible_years,
            "universal": p.universal,
            "is_active": p.is_active,
            "is_published": p.is_published,
            "image_url": p.image_url,
            "images": p.images,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None
        }

    def _to_movement_response(self, m: InventoryMovement) -> dict:
        return {
            "id": m.id,
            "tenant_id": m.tenant_id,
            "product_id": m.product_id,
            "product_name": m.product.name if m.product else "",
            "product_sku": m.product.sku if m.product else "",
            "type": m.type,
            "quantity": m.quantity,
            "unit_cost": float(m.unit_cost) if m.unit_cost else None,
            "total_cost": float(m.total_cost) if m.total_cost else None,
            "reference_type": m.reference_type,
            "reference_id": m.reference_id,
            "stock_before": m.stock_before,
            "stock_after": m.stock_after,
            "notes": m.notes,
            "created_by": m.created_by,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
