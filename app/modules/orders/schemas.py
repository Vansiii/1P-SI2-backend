from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class OrderItemResponse(BaseModel):
    id: int
    listing_id: int
    product_id: int
    quantity: int
    unit_price: float
    total_price: float
    product_name: str
    product_sku: Optional[str] = None
    product_brand: Optional[str] = None


class OrderResponse(BaseModel):
    id: int
    order_number: str
    client_id: int
    tenant_id: int
    subtotal: float
    shipping_cost: float
    discount_amount: float
    total: float
    platform_commission: float
    status: str
    stripe_payment_intent_id: Optional[str] = None
    payment_status: str
    paid_at: Optional[datetime] = None
    delivery_type: str
    delivery_address: Optional[str] = None
    delivery_notes: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    ready_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    # Joined info
    workshop_name: str
    client_name: str
    items: List[OrderItemResponse]

    class Config:
        from_attributes = True


class OrderCheckout(BaseModel):
    delivery_type: str = Field(default="pickup")  # pickup, shipping
    delivery_address: Optional[str] = None
    delivery_notes: Optional[str] = None


class OrderCancelRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)
