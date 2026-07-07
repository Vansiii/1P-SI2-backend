import re
from datetime import datetime, timezone
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.marketplace_listing import MarketplaceListing
from app.models.marketplace_listing_image import MarketplaceListingImage
from app.models.inventory_product import InventoryProduct
from app.models.workshop import Workshop
from app.models.audit_log import AuditLog
from app.core.logging import get_logger
import json

logger = get_logger(__name__)

_ACCENTED_CHARS = "áéíóúÁÉÍÓÚñÑ"
_PLAIN_CHARS = "aeiouAEIOUnN"
_UNACCENT_TABLE = str.maketrans(_ACCENTED_CHARS, _PLAIN_CHARS)


def _unaccent_column(column):
    """Quita tildes/ñ de una columna en SQL usando translate() nativo (sin extensiones)."""
    return func.translate(column, _ACCENTED_CHARS, _PLAIN_CHARS)


def _unaccent_value(value: str) -> str:
    """Quita tildes/ñ de un valor en Python, con la misma tabla usada en SQL."""
    return value.translate(_UNACCENT_TABLE)


class MarketplaceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_listing(self, tenant_id: int, user_id: int, data: dict) -> dict:
        # Validate that the product exists and belongs to the tenant
        product_id = data["product_id"]
        prod_stmt = select(InventoryProduct).where(
            and_(
                InventoryProduct.id == product_id,
                InventoryProduct.tenant_id == tenant_id,
                InventoryProduct.deleted_at == None
            )
        )
        prod_res = await self.session.execute(prod_stmt)
        product = prod_res.scalar_one_or_none()
        if not product:
            raise ValueError("El producto de inventario especificado no existe o no pertenece a su taller.")

        # Check if already published
        dup_stmt = select(MarketplaceListing).where(
            and_(
                MarketplaceListing.tenant_id == tenant_id,
                MarketplaceListing.product_id == product_id
            )
        )
        dup_res = await self.session.execute(dup_stmt)
        if dup_res.scalar_one_or_none():
            raise ValueError("Este producto ya ha sido publicado en el marketplace.")

        # Auto generate title, description and slug if not provided
        title = data.get("title") or product.name
        description = data.get("description") or product.description
        slug = self._slugify(title)

        listing = MarketplaceListing(
            tenant_id=tenant_id,
            product_id=product_id,
            public_price=data["public_price"],
            compare_at_price=data.get("compare_at_price"),
            is_visible=data.get("is_visible", True),
            is_featured=data.get("is_featured", False),
            title=title,
            description=description,
            slug=slug,
            tags=data.get("tags") or [],
            shipping_available=data.get("shipping_available", False),
            shipping_cost=data.get("shipping_cost", 0),
            pickup_only=data.get("pickup_only", True),
            compatibility_override=data.get("compatibility_override"),
            status="active" if data.get("is_visible", True) else "draft",
            published_at=datetime.now(timezone.utc)
        )

        self.session.add(listing)
        await self.session.flush()

        # Update product published flag
        product.is_published = True

        # Log audit action
        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="CREATE_MARKETPLACE_LISTING",
            details=json.dumps({"listing_id": listing.id, "product_id": product_id, "title": title}, default=str),
            ip_address="127.0.0.1"
        )
        self.session.add(audit)

        # Build response
        await self.session.refresh(listing)
        return await self.get_listing(listing.id)

    async def update_listing(self, tenant_id: int, listing_id: int, user_id: int, data: dict) -> dict:
        stmt = select(MarketplaceListing).where(
            and_(
                MarketplaceListing.id == listing_id,
                MarketplaceListing.tenant_id == tenant_id
            )
        )
        res = await self.session.execute(stmt)
        listing = res.scalar_one_or_none()
        if not listing:
            raise ValueError("La publicación especificada no existe.")

        for key, value in data.items():
            if value is not None and hasattr(listing, key):
                setattr(listing, key, value)

        if "title" in data and data["title"]:
            listing.slug = self._slugify(data["title"])

        # Sync visibility with status
        if "is_visible" in data:
            listing.status = "active" if data["is_visible"] else "paused"

        await self.session.flush()

        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="UPDATE_MARKETPLACE_LISTING",
            details=json.dumps({"listing_id": listing_id, "fields_updated": list(data.keys())}, default=str),
            ip_address="127.0.0.1"
        )
        self.session.add(audit)

        return await self.get_listing(listing_id)

    async def delete_listing(self, tenant_id: int, listing_id: int, user_id: int) -> None:
        stmt = select(MarketplaceListing).where(
            and_(
                MarketplaceListing.id == listing_id,
                MarketplaceListing.tenant_id == tenant_id
            )
        )
        res = await self.session.execute(stmt)
        listing = res.scalar_one_or_none()
        if not listing:
            raise ValueError("La publicación especificada no existe.")

        # Update product published flag
        prod_stmt = select(InventoryProduct).where(InventoryProduct.id == listing.product_id)
        prod_res = await self.session.execute(prod_stmt)
        product = prod_res.scalar_one_or_none()
        if product:
            product.is_published = False

        await self.session.delete(listing)
        await self.session.flush()

        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="DELETE_MARKETPLACE_LISTING",
            details=json.dumps({"listing_id": listing_id}, default=str),
            ip_address="127.0.0.1"
        )
        self.session.add(audit)

    async def delete_listing_by_product(self, tenant_id: int, product_id: int, user_id: int) -> None:
        stmt = select(MarketplaceListing).where(
            and_(
                MarketplaceListing.tenant_id == tenant_id,
                MarketplaceListing.product_id == product_id
            )
        )
        res = await self.session.execute(stmt)
        listing = res.scalar_one_or_none()
        if not listing:
            raise ValueError("Este producto no tiene una publicación activa en el marketplace.")
        await self.delete_listing(tenant_id, listing.id, user_id)

    async def get_listing(self, listing_id: int, increment_view: bool = False) -> dict:
        stmt = select(
            MarketplaceListing,
            InventoryProduct,
            Workshop,
        ).join(
            InventoryProduct, MarketplaceListing.product_id == InventoryProduct.id
        ).join(
            Workshop, MarketplaceListing.tenant_id == Workshop.tenant_id
        ).where(
            MarketplaceListing.id == listing_id
        )

        res = await self.session.execute(stmt)
        row = res.one_or_none()
        if not row:
            raise ValueError("La publicación especificada no existe.")

        listing, product, workshop = row

        if increment_view:
            listing.view_count += 1
            await self.session.flush()
            # `updated_at` tiene onupdate=func.now(): tras el flush queda "expired"
            # y SQLAlchemy intentaría recargarlo con una query perezosa la primera
            # vez que se lee el atributo. Como _to_listing_response() es síncrono,
            # esa recarga perezosa revienta con MissingGreenlet fuera del contexto
            # async. Se refresca explícitamente aquí, dentro del contexto async.
            await self.session.refresh(listing)

        return self._to_listing_response(listing, product, workshop)

    async def list_listings(self, filters: dict) -> tuple[list[dict], int]:
        # Build query
        stmt = select(
            MarketplaceListing,
            InventoryProduct,
            Workshop,
        ).join(
            InventoryProduct, MarketplaceListing.product_id == InventoryProduct.id
        ).join(
            Workshop, MarketplaceListing.tenant_id == Workshop.tenant_id
        ).where(
            and_(
                MarketplaceListing.status == "active",
                MarketplaceListing.is_visible == True,
                InventoryProduct.deleted_at == None
            )
        )

        # Filters
        if filters.get("search"):
            search = f"%{_unaccent_value(filters['search'].lower())}%"
            stmt = stmt.where(
                or_(
                    _unaccent_column(func.lower(MarketplaceListing.title)).like(search),
                    _unaccent_column(func.lower(InventoryProduct.brand)).like(search),
                    _unaccent_column(func.lower(InventoryProduct.part_number)).like(search)
                )
            )

        if filters.get("category_id"):
            stmt = stmt.where(InventoryProduct.category_id == filters["category_id"])

        if filters.get("min_price"):
            stmt = stmt.where(MarketplaceListing.public_price >= filters["min_price"])

        if filters.get("max_price"):
            stmt = stmt.where(MarketplaceListing.public_price <= filters["max_price"])

        # Compatibilidad vehicular
        if filters.get("vehicle_brand"):
            stmt = stmt.where(
                or_(
                    InventoryProduct.universal == True,
                    InventoryProduct.compatible_brands.contains([filters["vehicle_brand"]])
                )
            )
        if filters.get("vehicle_model"):
            stmt = stmt.where(
                or_(
                    InventoryProduct.universal == True,
                    InventoryProduct.compatible_models.contains([filters["vehicle_model"]])
                )
            )

        if filters.get("workshop_id"):
            stmt = stmt.where(Workshop.id == filters["workshop_id"])

        # Count total
        count_stmt = select(func.count(MarketplaceListing.id)).join(
            InventoryProduct, MarketplaceListing.product_id == InventoryProduct.id
        ).where(
            and_(
                MarketplaceListing.status == "active",
                MarketplaceListing.is_visible == True,
                InventoryProduct.deleted_at == None
            )
        )
        if filters.get("workshop_id"):
            count_stmt = count_stmt.join(
                Workshop, MarketplaceListing.tenant_id == Workshop.tenant_id
            ).where(Workshop.id == filters["workshop_id"])

        # Apply same filters to count
        if filters.get("search"):
            search = f"%{_unaccent_value(filters['search'].lower())}%"
            count_stmt = count_stmt.where(
                or_(
                    _unaccent_column(func.lower(MarketplaceListing.title)).like(search),
                    _unaccent_column(func.lower(InventoryProduct.brand)).like(search),
                    _unaccent_column(func.lower(InventoryProduct.part_number)).like(search)
                )
            )
        if filters.get("category_id"):
            count_stmt = count_stmt.where(InventoryProduct.category_id == filters["category_id"])
        if filters.get("min_price"):
            count_stmt = count_stmt.where(MarketplaceListing.public_price >= filters["min_price"])
        if filters.get("max_price"):
            count_stmt = count_stmt.where(MarketplaceListing.public_price <= filters["max_price"])
        if filters.get("vehicle_brand"):
            count_stmt = count_stmt.where(
                or_(
                    InventoryProduct.universal == True,
                    InventoryProduct.compatible_brands.contains([filters["vehicle_brand"]])
                )
            )
        if filters.get("vehicle_model"):
            count_stmt = count_stmt.where(
                or_(
                    InventoryProduct.universal == True,
                    InventoryProduct.compatible_models.contains([filters["vehicle_model"]])
                )
            )

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar() or 0

        # Sort and pagination
        sort_by = filters.get("sort_by") or "newest"
        if sort_by == "price_asc":
            stmt = stmt.order_by(MarketplaceListing.public_price.asc())
        elif sort_by == "price_desc":
            stmt = stmt.order_by(MarketplaceListing.public_price.desc())
        elif sort_by == "rating":
            stmt = stmt.order_by(desc(MarketplaceListing.avg_rating))
        else:  # newest
            stmt = stmt.order_by(desc(MarketplaceListing.created_at))

        page = filters.get("page") or 1
        size = filters.get("size") or 20
        stmt = stmt.offset((page - 1) * size).limit(size)

        res = await self.session.execute(stmt)
        rows = res.all()

        items = [self._to_listing_response(r[0], r[1], r[2]) for r in rows]
        return items, total

    async def list_my_listings(self, tenant_id: int) -> list[dict]:
        stmt = select(
            MarketplaceListing,
            InventoryProduct,
            Workshop,
        ).join(
            InventoryProduct, MarketplaceListing.product_id == InventoryProduct.id
        ).join(
            Workshop, MarketplaceListing.tenant_id == Workshop.tenant_id
        ).where(
            and_(
                MarketplaceListing.tenant_id == tenant_id,
                InventoryProduct.deleted_at == None
            )
        ).order_by(desc(MarketplaceListing.created_at))

        res = await self.session.execute(stmt)
        rows = res.all()
        return [self._to_listing_response(r[0], r[1], r[2]) for r in rows]

    async def get_my_stats(self, tenant_id: int) -> dict:
        stmt = select(
            func.count(MarketplaceListing.id),
            func.coalesce(func.sum(MarketplaceListing.view_count), 0),
            func.coalesce(func.sum(MarketplaceListing.sale_count), 0),
            func.count(func.nullif(MarketplaceListing.is_featured, False))
        ).where(MarketplaceListing.tenant_id == tenant_id)

        res = await self.session.execute(stmt)
        row = res.one()
        return {
            "total_listings": row[0],
            "total_views": row[1],
            "total_sales": row[2],
            "featured_listings": row[3]
        }

    async def compare_listings(self, listing_ids: list[int]) -> list[dict]:
        if not listing_ids:
            return []
        stmt = select(
            MarketplaceListing,
            InventoryProduct,
            Workshop,
        ).join(
            InventoryProduct, MarketplaceListing.product_id == InventoryProduct.id
        ).join(
            Workshop, MarketplaceListing.tenant_id == Workshop.tenant_id
        ).where(
            MarketplaceListing.id.in_(listing_ids)
        )

        res = await self.session.execute(stmt)
        rows = res.all()
        return [self._to_listing_response(r[0], r[1], r[2]) for r in rows]

    async def list_workshops_with_listings(self) -> list[dict]:
        stmt = select(
            Workshop.id,
            Workshop.workshop_name,
            Workshop.description,
            Workshop.address,
            Workshop.workshop_phone,
            func.count(MarketplaceListing.id).label("listings_count"),
            func.coalesce(func.avg(MarketplaceListing.avg_rating), 0).label("avg_rating"),
            func.coalesce(func.sum(MarketplaceListing.review_count), 0).label("review_count"),
        ).join(
            MarketplaceListing, MarketplaceListing.tenant_id == Workshop.tenant_id
        ).join(
            InventoryProduct, MarketplaceListing.product_id == InventoryProduct.id
        ).where(
            and_(
                MarketplaceListing.status == "active",
                MarketplaceListing.is_visible == True,
                InventoryProduct.deleted_at == None
            )
        ).group_by(
            Workshop.id, Workshop.workshop_name, Workshop.description,
            Workshop.address, Workshop.workshop_phone
        ).order_by(desc(func.count(MarketplaceListing.id)))

        res = await self.session.execute(stmt)
        rows = res.all()
        return [
            {
                "workshop_id": r.id,
                "workshop_name": r.workshop_name,
                "description": r.description,
                "address": r.address,
                "phone": r.workshop_phone,
                "listings_count": r.listings_count,
                "avg_rating": round(float(r.avg_rating), 2),
                "review_count": r.review_count,
            }
            for r in rows
        ]

    def _slugify(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r'[^a-z0-9\s-]', '', text)
        text = re.sub(r'[\s-]+', '-', text)
        return text

    def _to_listing_response(self, listing: MarketplaceListing, product: InventoryProduct, workshop: Workshop) -> dict:
        return {
            "id": listing.id,
            "tenant_id": listing.tenant_id,
            "product_id": listing.product_id,
            "public_price": float(listing.public_price),
            "compare_at_price": float(listing.compare_at_price) if listing.compare_at_price else None,
            "is_visible": listing.is_visible,
            "is_featured": listing.is_featured,
            "title": listing.title,
            "description": listing.description,
            "slug": listing.slug,
            "tags": listing.tags or [],
            "view_count": listing.view_count,
            "sale_count": listing.sale_count,
            "avg_rating": float(listing.avg_rating),
            "review_count": listing.review_count,
            "shipping_available": listing.shipping_available,
            "shipping_cost": float(listing.shipping_cost),
            "pickup_only": listing.pickup_only,
            "compatibility_override": listing.compatibility_override,
            "status": listing.status,
            "published_at": listing.published_at.isoformat() if listing.published_at else None,
            "created_at": listing.created_at.isoformat(),
            "updated_at": listing.updated_at.isoformat(),
            
            # Product details snapshot
            "product_name": product.name,
            "product_sku": product.sku,
            "product_brand": product.brand,
            "product_part_number": product.part_number,
            "product_image_url": product.image_url,
            "current_stock": product.current_stock,
            "universal": product.universal,
            "compatible_brands": product.compatible_brands or [],
            "compatible_models": product.compatible_models or [],
            "compatible_years": product.compatible_years,

            # Workshop details (Workshop hereda de User por tabla conjunta)
            "workshop_name": workshop.workshop_name or f"{workshop.first_name} {workshop.last_name}".strip(),
            "workshop_address": workshop.address,
            "workshop_city": None,
            "workshop_phone": workshop.phone
        }
