import stripe
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import get_logger, get_settings
from app.models.subscription_plan import SubscriptionPlan
from app.models.tenant_subscription import TenantSubscription
from app.models.tenant import Tenant
from app.models.workshop import Workshop

logger = get_logger(__name__)
settings = get_settings()


class StripeSubscriptionService:
    def __init__(self, session: AsyncSession):
        self.session = session
        stripe.api_key = settings.stripe_secret_key

    async def create_checkout_session(
        self, tenant: Tenant, plan: SubscriptionPlan, user_email: str
    ) -> str:
        if not plan.stripe_price_id:
            product = stripe.Product.create(
                name=plan.name,
                description=plan.description or "",
                metadata={"plan_code": plan.code},
            )
            price = stripe.Price.create(
                product=product.id,
                unit_amount=int(plan.price * 100),
                currency="usd",
                recurring={"interval": "month"},
            )
            plan.stripe_price_id = price.id
            plan.stripe_product_id = product.id
            await self.session.commit()

        result = await self.session.execute(
            __import__("sqlalchemy").select(TenantSubscription).where(
                TenantSubscription.tenant_id == tenant.id
            ).order_by(TenantSubscription.created_at.desc()).limit(1)
        )
        existing = result.scalar_one_or_none()
        customer_id = existing.provider_customer_id if existing and existing.provider_customer_id else None

        if not customer_id:
            customer = stripe.Customer.create(
                email=user_email,
                metadata={"tenant_id": str(tenant.id), "workshop_id": str(tenant.workshop_id)},
            )
            customer_id = customer.id

        session_obj = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{settings.frontend_url}/workshop/subscription?success=true&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.frontend_url}/workshop/subscription?canceled=true",
            metadata={"tenant_id": str(tenant.id), "plan_id": str(plan.id)},
        )

        if existing:
            existing.provider_customer_id = customer_id
            await self.session.commit()

        return session_obj.url

    async def change_stripe_subscription(
        self, current: TenantSubscription, new_plan: SubscriptionPlan
    ) -> dict:
        if not current.provider_subscription_id:
            return {"url": None, "message": "Plan cambiado a " + new_plan.name}

        if not new_plan.stripe_price_id:
            product = stripe.Product.create(
                name=new_plan.name,
                description=new_plan.description or "",
            )
            price_item = stripe.Price.create(
                product=product.id,
                unit_amount=int(new_plan.price * 100),
                currency="usd",
                recurring={"interval": "month"},
            )
            new_plan.stripe_price_id = price_item.id
            new_plan.stripe_product_id = product.id
            await self.session.commit()

        sub = stripe.Subscription.retrieve(current.provider_subscription_id)
        items = sub["items"]["data"]
        stripe.Subscription.modify(
            current.provider_subscription_id,
            items=[{
                "id": items[0]["id"],
                "price": new_plan.stripe_price_id,
            }],
            proration_behavior="always_invoice",
            metadata={"plan_id": str(new_plan.id)},
        )

        current.plan_id = new_plan.id
        await self.session.commit()

        return {"url": None, "message": "Plan actualizado a " + new_plan.name}

    def cancel_stripe_subscription(self, provider_subscription_id: str) -> None:
        stripe.Subscription.modify(
            provider_subscription_id,
            cancel_at_period_end=True,
        )

    def reactivate_stripe_subscription(self, provider_subscription_id: str) -> None:
        stripe.Subscription.modify(
            provider_subscription_id,
            cancel_at_period_end=False,
        )
