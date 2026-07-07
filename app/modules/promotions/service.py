from datetime import datetime, timezone
from sqlalchemy import select, and_, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.promotion import Promotion
from app.models.audit_log import AuditLog
import json


class PromotionService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_promotion(self, tenant_id: int, user_id: int, data: dict) -> dict:
        promo = Promotion(
            tenant_id=tenant_id,
            name=data["name"],
            description=data.get("description"),
            type=data["type"],
            value=data["value"],
            applies_to=data.get("applies_to", "all"),
            target_ids=data.get("target_ids") or [],
            starts_at=data["starts_at"],
            ends_at=data["ends_at"],
            max_uses=data.get("max_uses"),
            current_uses=0,
            min_purchase=data.get("min_purchase") or 0.0,
            is_active=True
        )

        self.session.add(promo)
        await self.session.flush()

        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="CREATE_PROMOTION",
            details=json.dumps({"promotion_id": promo.id, "name": promo.name}, default=str),
            ip_address="127.0.0.1"
        )
        self.session.add(audit)

        await self.session.refresh(promo)
        return self._to_response(promo)

    async def update_promotion(self, tenant_id: int, promotion_id: int, user_id: int, data: dict) -> dict:
        stmt = select(Promotion).where(
            and_(
                Promotion.id == promotion_id,
                Promotion.tenant_id == tenant_id
            )
        )
        res = await self.session.execute(stmt)
        promo = res.scalar_one_or_none()
        if not promo:
            raise ValueError("La promoción especificada no existe.")

        for key, value in data.items():
            if value is not None and hasattr(promo, key):
                setattr(promo, key, value)

        await self.session.flush()

        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="UPDATE_PROMOTION",
            details=json.dumps({"promotion_id": promotion_id, "updated_fields": list(data.keys())}, default=str),
            ip_address="127.0.0.1"
        )
        self.session.add(audit)

        return self._to_response(promo)

    async def delete_promotion(self, tenant_id: int, promotion_id: int, user_id: int) -> None:
        stmt = select(Promotion).where(
            and_(
                Promotion.id == promotion_id,
                Promotion.tenant_id == tenant_id
            )
        )
        res = await self.session.execute(stmt)
        promo = res.scalar_one_or_none()
        if not promo:
            raise ValueError("La promoción especificada no existe.")

        await self.session.delete(promo)
        await self.session.flush()

        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="DELETE_PROMOTION",
            details=json.dumps({"promotion_id": promotion_id}, default=str),
            ip_address="127.0.0.1"
        )
        self.session.add(audit)

    async def get_promotion(self, tenant_id: int, promotion_id: int) -> dict:
        stmt = select(Promotion).where(
            and_(
                Promotion.id == promotion_id,
                Promotion.tenant_id == tenant_id
            )
        )
        res = await self.session.execute(stmt)
        promo = res.scalar_one_or_none()
        if not promo:
            raise ValueError("La promoción especificada no existe.")
        return self._to_response(promo)

    async def list_promotions(self, tenant_id: int) -> list[dict]:
        stmt = select(Promotion).where(Promotion.tenant_id == tenant_id).order_by(desc(Promotion.created_at))
        res = await self.session.execute(stmt)
        promos = res.scalars().all()
        return [self._to_response(p) for p in promos]

    async def list_active_promotions_for_listing(self, tenant_id: int, listing_id: int, category_id: int | None = None, product_id: int | None = None) -> list[dict]:
        now = datetime.now(timezone.utc)
        
        # Build query matching:
        # 1. applies_to == 'all'
        # 2. applies_to == 'listing' and contains listing_id
        # 3. applies_to == 'product' and contains product_id
        # 4. applies_to == 'category' and contains category_id
        stmt = select(Promotion).where(
            and_(
                Promotion.tenant_id == tenant_id,
                Promotion.is_active == True,
                Promotion.starts_at <= now,
                Promotion.ends_at >= now,
                or_(
                    Promotion.applies_to == "all",
                    and_(Promotion.applies_to == "listing", Promotion.target_ids.contains([listing_id])),
                    and_(Promotion.applies_to == "product", Promotion.target_ids.contains([product_id])) if product_id is not None else False,
                    and_(Promotion.applies_to == "category", Promotion.target_ids.contains([category_id])) if category_id is not None else False
                )
            )
        )

        res = await self.session.execute(stmt)
        promos = res.scalars().all()
        return [self._to_response(p) for p in promos]

    def _to_response(self, promo: Promotion) -> dict:
        return {
            "id": promo.id,
            "tenant_id": promo.tenant_id,
            "name": promo.name,
            "description": promo.description,
            "type": promo.type,
            "value": float(promo.value),
            "applies_to": promo.applies_to,
            "target_ids": promo.target_ids or [],
            "starts_at": promo.starts_at.isoformat(),
            "ends_at": promo.ends_at.isoformat(),
            "max_uses": promo.max_uses,
            "current_uses": promo.current_uses,
            "min_purchase": float(promo.min_purchase),
            "is_active": promo.is_active,
            "created_at": promo.created_at.isoformat(),
            "updated_at": promo.updated_at.isoformat()
        }
