import stripe
import random
from datetime import datetime, timezone
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.marketplace_order import MarketplaceOrder
from app.models.order_item import OrderItem
from app.models.cart_item import CartItem
from app.models.shopping_cart import ShoppingCart
from app.models.marketplace_listing import MarketplaceListing
from app.models.inventory_product import InventoryProduct
from app.models.inventory_movement import InventoryMovement
from app.models.stock_alert import StockAlert
from app.models.platform_commission import PlatformCommission
from app.models.workshop_balance import WorkshopBalance
from app.models.financial_movement import WorkshopFinancialMovement
from app.models.client import Client
from app.models.workshop import Workshop
from app.models.user import User
from app.models.audit_log import AuditLog
import json

logger = get_logger(__name__)
settings = get_settings()


class OrderService:
    def __init__(self, session: AsyncSession):
        self.session = session
        stripe.api_key = settings.stripe_secret_key

    async def _get_client_id(self, user_id: int) -> int:
        stmt = select(Client.id).where(Client.id == user_id)
        res = await self.session.execute(stmt)
        client_id = res.scalar_one_or_none()
        if not client_id:
            raise ValueError("Su cuenta no está registrada como cliente.")
        return client_id

    async def checkout_cart(self, user_id: int, delivery_type: str, delivery_address: str | None, delivery_notes: str | None) -> list[dict]:
        client_id = await self._get_client_id(user_id)
        
        # 1. Fetch shopping cart
        cart_stmt = select(ShoppingCart).where(
            and_(
                ShoppingCart.client_id == client_id,
                ShoppingCart.status == "active"
            )
        )
        cart_res = await self.session.execute(cart_stmt)
        cart = cart_res.scalar_one_or_none()
        if not cart:
            raise ValueError("No tiene un carrito de compras activo.")

        # 2. Get items in cart
        items_stmt = select(
            CartItem,
            MarketplaceListing,
            InventoryProduct
        ).join(
            MarketplaceListing, CartItem.listing_id == MarketplaceListing.id
        ).join(
            InventoryProduct, MarketplaceListing.product_id == InventoryProduct.id
        ).where(
            CartItem.cart_id == cart.id
        )
        items_res = await self.session.execute(items_stmt)
        cart_rows = items_res.all()

        if not cart_rows:
            raise ValueError("El carrito de compras está vacío.")

        # 3. Validate stock availability
        for c_item, listing, product in cart_rows:
            if product.current_stock < c_item.quantity:
                raise ValueError(f"Stock insuficiente para {listing.title or product.name}. Solo quedan {product.current_stock} unidades.")

        # 4. Group items by tenant_id (workshop owner) to split orders
        orders_by_tenant = {}
        for c_item, listing, product in cart_rows:
            tenant_id = listing.tenant_id
            if tenant_id not in orders_by_tenant:
                orders_by_tenant[tenant_id] = []
            orders_by_tenant[tenant_id].append((c_item, listing, product))

        created_orders = []

        # 5. Create an order for each tenant
        for tenant_id, group in orders_by_tenant.items():
            # Generate unique order number
            date_str = datetime.now().strftime("%Y%m%d")
            rand_code = random.randint(1000, 9999)
            order_number = f"MKT-{date_str}-{rand_code}"

            subtotal = 0.0
            shipping_cost = 0.0
            discount_amount = 0.0

            for c_item, listing, product in group:
                subtotal += float(c_item.quantity) * float(listing.public_price)
                if delivery_type == "shipping" and listing.shipping_available and not listing.pickup_only:
                    shipping_cost += float(listing.shipping_cost)

            total = subtotal + shipping_cost - discount_amount
            platform_commission = subtotal * 0.10  # 10% platform fee

            order = MarketplaceOrder(
                order_number=order_number,
                client_id=client_id,
                tenant_id=tenant_id,
                subtotal=subtotal,
                shipping_cost=shipping_cost,
                discount_amount=discount_amount,
                total=total,
                platform_commission=platform_commission,
                status="pending_payment",
                payment_status="pending",
                delivery_type=delivery_type,
                delivery_address=delivery_address,
                delivery_notes=delivery_notes
            )
            self.session.add(order)
            await self.session.flush()

            # Create Order Items and lock/reserve stock temporarily
            for c_item, listing, product in group:
                order_item = OrderItem(
                    order_id=order.id,
                    listing_id=listing.id,
                    product_id=product.id,
                    quantity=c_item.quantity,
                    unit_price=float(listing.public_price),
                    total_price=float(c_item.quantity) * float(listing.public_price),
                    product_name=listing.title or product.name,
                    product_sku=product.sku,
                    product_brand=product.brand
                )
                self.session.add(order_item)

            created_orders.append(order)

        # 6. Clear shopping cart items
        for c_item, _, _ in cart_rows:
            await self.session.delete(c_item)

        await self.session.flush()

        # Log audit action
        audit = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action="CHECKOUT_MARKETPLACE_CART",
            details=json.dumps({"order_ids": [o.id for o in created_orders]}, default=str),
            ip_address="127.0.0.1"
        )
        self.session.add(audit)

        return [await self.get_order(o.id) for o in created_orders]

    async def create_payment_intent(self, order_id: int, user_id: int) -> dict:
        client_id = await self._get_client_id(user_id)
        
        stmt = select(MarketplaceOrder).where(
            and_(
                MarketplaceOrder.id == order_id,
                MarketplaceOrder.client_id == client_id
            )
        )
        res = await self.session.execute(stmt)
        order = res.scalar_one_or_none()
        if not order:
            raise ValueError("La orden especificada no existe.")

        if order.status != "pending_payment":
            raise ValueError(f"Esta orden no está pendiente de pago. Estado actual: {order.status}")

        # Create Stripe PaymentIntent
        amount_cents = int(order.total * 100)
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="bob",  # Bolivianos
            metadata={
                "type": "marketplace_order",
                "order_id": str(order.id),
                "order_number": order.order_number,
                "tenant_id": str(order.tenant_id),
                "client_id": str(order.client_id)
            }
        )

        order.stripe_payment_intent_id = payment_intent.id
        await self.session.flush()

        return {
            "client_secret": payment_intent.client_secret,
            "order_id": order.id,
            "order_number": order.order_number,
            "total": float(order.total)
        }

    async def complete_payment(self, stripe_payment_intent_id: str) -> None:
        stmt = select(MarketplaceOrder).where(MarketplaceOrder.stripe_payment_intent_id == stripe_payment_intent_id)
        res = await self.session.execute(stmt)
        order = res.scalar_one_or_none()
        if not order:
            logger.error(f"Order not found for Stripe PaymentIntent {stripe_payment_intent_id}")
            return

        if order.status != "pending_payment":
            logger.info(f"Order {order.order_number} already processed. Status: {order.status}")
            return

        # 1. Update order status
        order.status = "paid"
        order.payment_status = "paid"
        order.paid_at = datetime.now(timezone.utc)

        # 2. Retrieve order items to deduct inventory stock
        item_stmt = select(OrderItem, InventoryProduct).join(
            InventoryProduct, OrderItem.product_id == InventoryProduct.id
        ).where(
            OrderItem.order_id == order.id
        )
        items_res = await self.session.execute(item_stmt)
        rows = items_res.all()

        for o_item, product in rows:
            stock_before = product.current_stock
            product.current_stock -= o_item.quantity
            stock_after = product.current_stock

            # Validate stock doesn't go below 0 (redundant check)
            if product.current_stock < 0:
                product.current_stock = 0
                stock_after = 0

            # Insert Kardex movement
            movement = InventoryMovement(
                tenant_id=order.tenant_id,
                product_id=product.id,
                type="salida",
                quantity=-o_item.quantity,
                unit_cost=float(product.cost_price),
                total_cost=float(o_item.quantity) * float(product.cost_price),
                reference_type="orden_marketplace",
                reference_id=order.id,
                stock_before=stock_before,
                stock_after=stock_after,
                notes=f"Venta en Marketplace. Orden: {order.order_number}",
                created_by=order.client_id  # client triggers this
            )
            self.session.add(movement)

            # Generate Stock Alert if needed
            if product.current_stock == 0:
                alert = StockAlert(
                    tenant_id=order.tenant_id,
                    product_id=product.id,
                    alert_type="out_of_stock",
                    current_stock=0,
                    threshold=product.min_stock
                )
                self.session.add(alert)
            elif product.current_stock <= product.min_stock:
                alert = StockAlert(
                    tenant_id=order.tenant_id,
                    product_id=product.id,
                    alert_type="low_stock",
                    current_stock=product.current_stock,
                    threshold=product.min_stock
                )
                self.session.add(alert)

        # 3. Financial calculations
        # Add platforms commission (10% of subtotal)
        platform_commission_amount = float(order.platform_commission)
        commission = PlatformCommission(
            tenant_id=order.tenant_id,
            amount=platform_commission_amount,
            reference_type="marketplace_order",
            reference_id=order.id
        )
        self.session.add(commission)

        # Add earnings to workshop balance
        net_earning = float(order.total) - platform_commission_amount
        
        balance_stmt = select(WorkshopBalance).where(WorkshopBalance.tenant_id == order.tenant_id)
        balance_res = await self.session.execute(balance_stmt)
        balance = balance_res.scalar_one_or_none()

        if not balance:
            balance = WorkshopBalance(
                tenant_id=order.tenant_id,
                current_balance=net_earning,
                total_earned=net_earning,
                total_withdrawn=0
            )
            self.session.add(balance)
        else:
            balance.current_balance += net_earning
            balance.total_earned += net_earning

        # Register financial movement
        financial_mov = WorkshopFinancialMovement(
            tenant_id=order.tenant_id,
            amount=net_earning,
            type="credit",
            description=f"Pago por orden de marketplace {order.order_number}",
            reference_type="marketplace_order",
            reference_id=order.id
        )
        self.session.add(financial_mov)

        # Save changes
        await self.session.flush()
        logger.info(f"Payment completed successfully for marketplace order {order.order_number}")

    async def get_order(self, order_id: int) -> dict:
        stmt = select(
            MarketplaceOrder,
            Workshop,
            User,
            Client
        ).join(
            Workshop, MarketplaceOrder.tenant_id == Workshop.tenant_id
        ).join(
            User, Workshop.id == User.id
        ).join(
            Client, MarketplaceOrder.client_id == Client.id
        ).where(
            MarketplaceOrder.id == order_id
        )

        res = await self.session.execute(stmt)
        row = res.one_or_none()
        if not row:
            raise ValueError("La orden especificada no existe.")

        order, workshop, user_workshop, client = row

        # Get items
        items_stmt = select(OrderItem).where(OrderItem.order_id == order.id)
        items_res = await self.session.execute(items_stmt)
        items = items_res.scalars().all()

        client_user_stmt = select(User).where(User.id == client.id)
        client_user_res = await self.session.execute(client_user_stmt)
        client_user = client_user_res.scalar_one()

        items_list = []
        for it in items:
            items_list.append({
                "id": it.id,
                "listing_id": it.listing_id,
                "product_id": it.product_id,
                "quantity": it.quantity,
                "unit_price": float(it.unit_price),
                "total_price": float(it.total_price),
                "product_name": it.product_name,
                "product_sku": it.product_sku,
                "product_brand": it.product_brand
            })

        return {
            "id": order.id,
            "order_number": order.order_number,
            "client_id": order.client_id,
            "tenant_id": order.tenant_id,
            "subtotal": float(order.subtotal),
            "shipping_cost": float(order.shipping_cost),
            "discount_amount": float(order.discount_amount),
            "total": float(order.total),
            "platform_commission": float(order.platform_commission),
            "status": order.status,
            "stripe_payment_intent_id": order.stripe_payment_intent_id,
            "payment_status": order.payment_status,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "delivery_type": order.delivery_type,
            "delivery_address": order.delivery_address,
            "delivery_notes": order.delivery_notes,
            "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
            "ready_at": order.ready_at.isoformat() if order.ready_at else None,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "completed_at": order.completed_at.isoformat() if order.completed_at else None,
            "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
            "cancellation_reason": order.cancellation_reason,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            
            # Additional details
            "workshop_name": user_workshop.display_name or workshop.legal_name,
            "client_name": client_user.display_name or "Cliente",
            "items": items_list
        }

    async def list_client_orders(self, user_id: int) -> list[dict]:
        client_id = await self._get_client_id(user_id)
        stmt = select(MarketplaceOrder.id).where(MarketplaceOrder.client_id == client_id).order_by(desc(MarketplaceOrder.created_at))
        res = await self.session.execute(stmt)
        ids = res.scalars().all()
        return [await self.get_order(oid) for oid in ids]

    async def list_workshop_orders(self, tenant_id: int) -> list[dict]:
        stmt = select(MarketplaceOrder.id).where(MarketplaceOrder.tenant_id == tenant_id).order_by(desc(MarketplaceOrder.created_at))
        res = await self.session.execute(stmt)
        ids = res.scalars().all()
        return [await self.get_order(oid) for oid in ids]

    async def update_order_status(self, tenant_id: int, order_id: int, action: str, reason: str | None = None) -> dict:
        stmt = select(MarketplaceOrder).where(
            and_(
                MarketplaceOrder.id == order_id,
                MarketplaceOrder.tenant_id == tenant_id
            )
        )
        res = await self.session.execute(stmt)
        order = res.scalar_one_or_none()
        if not order:
            raise ValueError("La orden especificada no existe.")

        # States transitions
        # pending_payment, paid, confirmed, preparing, ready_pickup, shipped, delivered, completed, cancelled, refunded
        if action == "confirm":
            if order.status != "paid":
                raise ValueError("Solo puede confirmar órdenes que ya han sido pagadas.")
            order.status = "confirmed"
            order.confirmed_at = datetime.now(timezone.utc)
        elif action == "prepare":
            if order.status != "confirmed":
                raise ValueError("Solo puede preparar órdenes previamente confirmadas.")
            order.status = "preparing"
        elif action == "ready":
            if order.status != "preparing":
                raise ValueError("Solo puede marcar lista para entrega una orden en preparación.")
            order.status = "ready_pickup"
            order.ready_at = datetime.now(timezone.utc)
        elif action == "ship":
            if order.status != "ready_pickup":
                raise ValueError("Solo puede despachar una orden que esté lista para entrega.")
            order.status = "shipped"
        elif action == "deliver":
            if order.status not in ["ready_pickup", "shipped"]:
                raise ValueError("Solo puede marcar como entregada una orden despachada o lista para retiro.")
            order.status = "delivered"
            order.delivered_at = datetime.now(timezone.utc)
        elif action == "complete":
            if order.status != "delivered":
                raise ValueError("Solo puede completar órdenes previamente entregadas.")
            order.status = "completed"
            order.completed_at = datetime.now(timezone.utc)
        elif action == "cancel":
            if order.status in ["completed", "cancelled", "delivered"]:
                raise ValueError("No se puede cancelar una orden completada, entregada o ya cancelada.")
            order.status = "cancelled"
            order.cancelled_at = datetime.now(timezone.utc)
            order.cancellation_reason = reason or "Cancelación por el taller."

            # Return stock to inventory if order was paid
            if order.payment_status == "paid":
                order.payment_status = "refunded"
                item_stmt = select(OrderItem, InventoryProduct).join(
                    InventoryProduct, OrderItem.product_id == InventoryProduct.id
                ).where(OrderItem.order_id == order.id)
                items_res = await self.session.execute(item_stmt)
                rows = items_res.all()

                for o_item, product in rows:
                    stock_before = product.current_stock
                    product.current_stock += o_item.quantity
                    stock_after = product.current_stock

                    # Insert Kardex movement
                    movement = InventoryMovement(
                        tenant_id=order.tenant_id,
                        product_id=product.id,
                        type="entrada",
                        quantity=o_item.quantity,
                        unit_cost=float(product.cost_price),
                        total_cost=float(o_item.quantity) * float(product.cost_price),
                        reference_type="devolucion",
                        reference_id=order.id,
                        stock_before=stock_before,
                        stock_after=stock_after,
                        notes=f"Devolución por cancelación de Orden: {order.order_number}",
                        created_by=order.tenant_id
                    )
                    self.session.add(movement)

        await self.session.flush()
        return await self.get_order(order.id)
