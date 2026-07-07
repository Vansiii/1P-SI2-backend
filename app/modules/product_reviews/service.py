from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product_review import ProductReview
from app.models.marketplace_listing import MarketplaceListing
from app.models.marketplace_order import MarketplaceOrder
from app.models.order_item import OrderItem
from app.models.client import Client
from app.models.user import User
from app.models.audit_log import AuditLog
import json


class ProductReviewService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_client_id(self, user_id: int) -> int:
        stmt = select(Client.id).where(Client.id == user_id)
        res = await self.session.execute(stmt)
        client_id = res.scalar_one_or_none()
        if not client_id:
            raise ValueError("Solo los clientes registrados pueden publicar reseñas.")
        return client_id

    async def create_review(self, user_id: int, data: dict) -> dict:
        client_id = await self._get_client_id(user_id)
        listing_id = data["listing_id"]
        order_id = data["order_id"]

        # 1. Verify that the order exists, belongs to the client and is paid/delivered/completed
        order_stmt = select(MarketplaceOrder).where(
            and_(
                MarketplaceOrder.id == order_id,
                MarketplaceOrder.client_id == client_id
            )
        )
        order_res = await self.session.execute(order_stmt)
        order = order_res.scalar_one_or_none()
        if not order:
            raise ValueError("La orden especificada no existe o no le pertenece.")
        
        if order.status not in ["paid", "confirmed", "preparing", "ready_pickup", "shipped", "delivered", "completed"]:
            raise ValueError("Solo puede reseñar productos de órdenes que ya hayan sido pagadas o completadas.")

        # 2. Verify that the listing was actually part of this order
        item_stmt = select(OrderItem).where(
            and_(
                OrderItem.order_id == order_id,
                OrderItem.listing_id == listing_id
            )
        )
        item_res = await self.session.execute(item_stmt)
        order_item = item_res.scalar_one_or_none()
        if not order_item:
            raise ValueError("Este producto no formó parte de la orden de compra especificada.")

        # 3. Check duplicate review
        dup_stmt = select(ProductReview).where(
            and_(
                ProductReview.listing_id == listing_id,
                ProductReview.client_id == client_id,
                ProductReview.order_id == order_id
            )
        )
        dup_res = await self.session.execute(dup_stmt)
        if dup_res.scalar_one_or_none():
            raise ValueError("Usted ya ha enviado una reseña para este producto en esta orden.")

        # 4. Create review
        review = ProductReview(
            listing_id=listing_id,
            client_id=client_id,
            order_id=order_id,
            tenant_id=order.tenant_id,
            rating=data["rating"],
            title=data.get("title"),
            comment=data.get("comment"),
            is_verified=True,
            is_visible=True
        )
        self.session.add(review)
        await self.session.flush()

        # 5. Recalculate average rating & review count for listing
        stats_stmt = select(
            func.count(ProductReview.id),
            func.coalesce(func.avg(ProductReview.rating), 0.0)
        ).where(
            and_(
                ProductReview.listing_id == listing_id,
                ProductReview.is_visible == True
            )
        )
        stats_res = await self.session.execute(stats_stmt)
        rev_count, avg_score = stats_res.one()

        listing_stmt = select(MarketplaceListing).where(MarketplaceListing.id == listing_id)
        listing_res = await self.session.execute(listing_stmt)
        listing = listing_res.scalar_one()

        listing.review_count = rev_count
        listing.avg_rating = avg_score
        await self.session.flush()

        # Audit
        audit = AuditLog(
            tenant_id=order.tenant_id,
            user_id=user_id,
            action="CREATE_PRODUCT_REVIEW",
            details=json.dumps({"review_id": review.id, "listing_id": listing_id, "rating": review.rating}, default=str),
            ip_address="127.0.0.1"
        )
        self.session.add(audit)

        await self.session.refresh(review)
        return await self.get_review(review.id)

    async def get_review(self, review_id: int) -> dict:
        stmt = select(ProductReview, User).join(
            User, ProductReview.client_id == User.id
        ).where(
            ProductReview.id == review_id
        )
        res = await self.session.execute(stmt)
        row = res.one_or_none()
        if not row:
            raise ValueError("La reseña especificada no existe.")
        
        review, user = row
        return self._to_response(review, user)

    async def list_reviews_for_listing(self, listing_id: int) -> list[dict]:
        stmt = select(ProductReview, User).join(
            User, ProductReview.client_id == User.id
        ).where(
            and_(
                ProductReview.listing_id == listing_id,
                ProductReview.is_visible == True
            )
        ).order_by(ProductReview.created_at.desc())

        res = await self.session.execute(stmt)
        rows = res.all()
        return [self._to_response(r[0], r[1]) for r in rows]

    def _to_response(self, review: ProductReview, user: User) -> dict:
        return {
            "id": review.id,
            "listing_id": review.listing_id,
            "client_id": review.client_id,
            "order_id": review.order_id,
            "tenant_id": review.tenant_id,
            "rating": review.rating,
            "title": review.title,
            "comment": review.comment,
            "is_verified": review.is_verified,
            "is_visible": review.is_visible,
            "created_at": review.created_at.isoformat(),
            "updated_at": review.updated_at.isoformat(),
            "client_name": user.display_name or "Cliente verificado"
        }
