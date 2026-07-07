import pytest
from pydantic import ValidationError
from datetime import datetime, timezone
from app.models.marketplace_listing import MarketplaceListing
from app.models.shopping_cart import ShoppingCart
from app.models.marketplace_order import MarketplaceOrder
from app.models.promotion import Promotion
from app.models.product_review import ProductReview
from app.modules.marketplace.schemas import MarketplaceListingCreate
from app.modules.cart.schemas import CartItemCreate
from app.modules.orders.schemas import OrderCheckout


class TestMarketplaceListingModel:
    def test_listing_creation_defaults(self):
        listing = MarketplaceListing(
            tenant_id=1,
            product_id=1,
            public_price=99.99,
            compare_at_price=120.0,
            title="Kit de embrague Toyota Corolla",
            is_visible=True,
            is_featured=False
        )
        assert listing.tenant_id == 1
        assert listing.product_id == 1
        assert float(listing.public_price) == 99.99
        assert float(listing.compare_at_price) == 120.0
        assert listing.title == "Kit de embrague Toyota Corolla"
        assert listing.is_visible is True
        assert listing.is_featured is False


class TestShoppingCartModel:
    def test_cart_creation_defaults(self):
        cart = ShoppingCart(
            client_id=2,
            status="active"
        )
        assert cart.client_id == 2
        assert cart.status == "active"


class TestMarketplaceOrderModel:
    def test_order_creation_defaults(self):
        order = MarketplaceOrder(
            order_number="MKT-20260705-1234",
            client_id=2,
            tenant_id=1,
            subtotal=150.00,
            shipping_cost=15.00,
            discount_amount=0.00,
            total=165.00,
            platform_commission=15.00,
            status="pending_payment"
        )
        assert order.order_number == "MKT-20260705-1234"
        assert order.client_id == 2
        assert order.tenant_id == 1
        assert float(order.total) == 165.00
        assert float(order.platform_commission) == 15.00
        assert order.status == "pending_payment"


class TestPromotionModel:
    def test_promotion_creation_defaults(self):
        now = datetime.now(timezone.utc)
        promo = Promotion(
            tenant_id=1,
            name="Descuento Pastillas",
            type="percentage",
            value=10.0,
            applies_to="category",
            starts_at=now,
            ends_at=now,
            is_active=True
        )
        assert promo.tenant_id == 1
        assert promo.name == "Descuento Pastillas"
        assert promo.type == "percentage"
        assert float(promo.value) == 10.0
        assert promo.applies_to == "category"
        assert promo.is_active is True


class TestProductReviewModel:
    def test_review_creation_defaults(self):
        review = ProductReview(
            listing_id=1,
            client_id=2,
            order_id=5,
            tenant_id=1,
            rating=5,
            title="Excelente producto",
            comment="Muy buen repuesto original.",
            is_verified=True
        )
        assert review.listing_id == 1
        assert review.client_id == 2
        assert review.rating == 5
        assert review.title == "Excelente producto"
        assert review.is_verified is True


class TestMarketplaceSchemas:
    def test_listing_create_schema_validation(self):
        # Valid data
        data = {
            "product_id": 1,
            "public_price": 50.0,
            "title": "Batería Toyo"
        }
        lst = MarketplaceListingCreate.model_validate(data)
        assert lst.product_id == 1
        assert lst.public_price == 50.0
        assert lst.title == "Batería Toyo"

        # Invalid price (zero or negative)
        with pytest.raises(ValidationError):
            MarketplaceListingCreate.model_validate({**data, "public_price": 0})
        with pytest.raises(ValidationError):
            MarketplaceListingCreate.model_validate({**data, "public_price": -5.0})

    def test_cart_item_schema_validation(self):
        data = {
            "listing_id": 1,
            "quantity": 3
        }
        item = CartItemCreate.model_validate(data)
        assert item.listing_id == 1
        assert item.quantity == 3

        # Invalid quantity (negative or zero)
        with pytest.raises(ValidationError):
            CartItemCreate.model_validate({**data, "quantity": 0})
        with pytest.raises(ValidationError):
            CartItemCreate.model_validate({**data, "quantity": -2})
