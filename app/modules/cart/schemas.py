from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class CartItemCreate(BaseModel):
    listing_id: int
    quantity: int = Field(default=1, gt=0)


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., gt=0)


class CartItemResponse(BaseModel):
    id: int
    listing_id: int
    quantity: int
    unit_price: float
    subtotal: float
    
    # Product snapshot
    title: str
    brand: Optional[str] = None
    image_url: Optional[str] = None
    current_stock: int
    
    # Workshop owner
    tenant_id: int
    workshop_name: str


class CartSummaryResponse(BaseModel):
    id: int
    client_id: int
    status: str
    total_items: int
    subtotal_price: float
    shipping_total: float
    total_price: float
    items: List[CartItemResponse]
