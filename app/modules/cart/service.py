from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.shopping_cart import ShoppingCart
from app.models.cart_item import CartItem
from app.models.marketplace_listing import MarketplaceListing
from app.models.inventory_product import InventoryProduct
from app.models.workshop import Workshop
from app.models.client import Client


class CartService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_client_id(self, user_id: int) -> int:
        stmt = select(Client.id).where(Client.id == user_id)
        res = await self.session.execute(stmt)
        client_id = res.scalar_one_or_none()
        if not client_id:
            raise ValueError("Su cuenta no está registrada como cliente para comprar repuestos.")
        return client_id

    async def _get_or_create_cart(self, client_id: int) -> ShoppingCart:
        stmt = select(ShoppingCart).where(
            and_(
                ShoppingCart.client_id == client_id,
                ShoppingCart.status == "active"
            )
        )
        res = await self.session.execute(stmt)
        cart = res.scalar_one_or_none()

        if not cart:
            cart = ShoppingCart(client_id=client_id, status="active")
            self.session.add(cart)
            await self.session.flush()

        return cart

    async def add_item(self, user_id: int, listing_id: int, quantity: int) -> dict:
        client_id = await self._get_client_id(user_id)
        cart = await self._get_or_create_cart(client_id)

        # Retrieve listing and inventory details
        lst_stmt = select(MarketplaceListing, InventoryProduct).join(
            InventoryProduct, MarketplaceListing.product_id == InventoryProduct.id
        ).where(
            and_(
                MarketplaceListing.id == listing_id,
                MarketplaceListing.status == "active",
                InventoryProduct.deleted_at == None
            )
        )
        lst_res = await self.session.execute(lst_stmt)
        row = lst_res.one_or_none()
        if not row:
            raise ValueError("El repuesto publicado no existe o ha sido pausado.")

        listing, product = row

        # Verify stock
        if product.current_stock < quantity:
            raise ValueError(f"Stock insuficiente. Solo quedan {product.current_stock} unidades disponibles.")

        # Check if item already in cart
        item_stmt = select(CartItem).where(
            and_(
                CartItem.cart_id == cart.id,
                CartItem.listing_id == listing_id
            )
        )
        item_res = await self.session.execute(item_stmt)
        cart_item = item_res.scalar_one_or_none()

        if cart_item:
            new_qty = cart_item.quantity + quantity
            if product.current_stock < new_qty:
                raise ValueError(f"No puede agregar esa cantidad. Su carrito sumaría {new_qty} unidades pero solo quedan {product.current_stock}.")
            cart_item.quantity = new_qty
            cart_item.unit_price = float(listing.public_price)
        else:
            cart_item = CartItem(
                cart_id=cart.id,
                listing_id=listing_id,
                quantity=quantity,
                unit_price=float(listing.public_price)
            )
            self.session.add(cart_item)

        await self.session.flush()
        return await self.get_cart_summary(user_id)

    async def update_item(self, user_id: int, item_id: int, quantity: int) -> dict:
        client_id = await self._get_client_id(user_id)
        cart = await self._get_or_create_cart(client_id)

        stmt = select(CartItem, MarketplaceListing, InventoryProduct).join(
            MarketplaceListing, CartItem.listing_id == MarketplaceListing.id
        ).join(
            InventoryProduct, MarketplaceListing.product_id == InventoryProduct.id
        ).where(
            and_(
                CartItem.id == item_id,
                CartItem.cart_id == cart.id
            )
        )
        res = await self.session.execute(stmt)
        row = res.one_or_none()
        if not row:
            raise ValueError("El ítem de carrito especificado no existe.")

        cart_item, listing, product = row

        if product.current_stock < quantity:
            raise ValueError(f"Stock insuficiente. Solo quedan {product.current_stock} unidades de este repuesto.")

        cart_item.quantity = quantity
        cart_item.unit_price = float(listing.public_price)
        await self.session.flush()

        return await self.get_cart_summary(user_id)

    async def remove_item(self, user_id: int, item_id: int) -> dict:
        client_id = await self._get_client_id(user_id)
        cart = await self._get_or_create_cart(client_id)

        stmt = delete(CartItem).where(
            and_(
                CartItem.id == item_id,
                CartItem.cart_id == cart.id
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

        return await self.get_cart_summary(user_id)

    async def clear_cart(self, user_id: int) -> None:
        client_id = await self._get_client_id(user_id)
        cart = await self._get_or_create_cart(client_id)

        stmt = delete(CartItem).where(CartItem.cart_id == cart.id)
        await self.session.execute(stmt)
        await self.session.flush()

    async def get_cart_summary(self, user_id: int) -> dict:
        client_id = await self._get_client_id(user_id)
        cart = await self._get_or_create_cart(client_id)

        # Retrieve items in cart with listing, product and workshop info
        stmt = select(
            CartItem,
            MarketplaceListing,
            InventoryProduct,
            Workshop
        ).join(
            MarketplaceListing, CartItem.listing_id == MarketplaceListing.id
        ).join(
            InventoryProduct, MarketplaceListing.product_id == InventoryProduct.id
        ).join(
            Workshop, MarketplaceListing.tenant_id == Workshop.tenant_id
        ).where(
            CartItem.cart_id == cart.id
        )

        res = await self.session.execute(stmt)
        rows = res.all()

        items_res = []
        subtotal_price = 0.0
        shipping_total = 0.0
        total_items = 0

        for row in rows:
            c_item, listing, product, workshop = row
            sub = float(c_item.quantity) * float(listing.public_price)
            subtotal_price += sub
            total_items += c_item.quantity
            
            # shipping cost calculation if applicable
            if listing.shipping_available and not listing.pickup_only:
                shipping_total += float(listing.shipping_cost)

            items_res.append({
                "id": c_item.id,
                "listing_id": c_item.listing_id,
                "quantity": c_item.quantity,
                "unit_price": float(listing.public_price),
                "subtotal": sub,
                
                # Snapshot details
                "title": listing.title or product.name,
                "brand": product.brand,
                "image_url": product.image_url,
                "current_stock": product.current_stock,

                # Workshop
                "tenant_id": listing.tenant_id,
                "workshop_name": workshop.workshop_name or f"{workshop.first_name} {workshop.last_name}".strip()
            })

        total_price = subtotal_price + shipping_total

        return {
            "id": cart.id,
            "client_id": cart.client_id,
            "status": cart.status,
            "total_items": total_items,
            "subtotal_price": subtotal_price,
            "shipping_total": shipping_total,
            "total_price": total_price,
            "items": items_res
        }

    async def validate_cart_stock(self, user_id: int) -> dict:
        client_id = await self._get_client_id(user_id)
        cart = await self._get_or_create_cart(client_id)

        stmt = select(CartItem, MarketplaceListing, InventoryProduct).join(
            MarketplaceListing, CartItem.listing_id == MarketplaceListing.id
        ).join(
            InventoryProduct, MarketplaceListing.product_id == InventoryProduct.id
        ).where(
            CartItem.cart_id == cart.id
        )

        res = await self.session.execute(stmt)
        rows = res.all()

        warnings = []
        is_valid = True

        for c_item, listing, product in rows:
            if product.current_stock == 0:
                is_valid = False
                warnings.append({
                    "item_id": c_item.id,
                    "title": listing.title or product.name,
                    "error": "El producto se encuentra completamente agotado.",
                    "type": "out_of_stock"
                })
            elif product.current_stock < c_item.quantity:
                is_valid = False
                warnings.append({
                    "item_id": c_item.id,
                    "title": listing.title or product.name,
                    "error": f"Stock insuficiente. Solo quedan {product.current_stock} unidades.",
                    "type": "low_stock",
                    "available_stock": product.current_stock
                })

        return {
            "is_valid": is_valid,
            "warnings": warnings
        }
