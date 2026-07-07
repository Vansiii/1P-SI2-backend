from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class MarketplaceListingCreate(BaseModel):
    product_id: int
    public_price: float = Field(..., gt=0)
    compare_at_price: Optional[float] = Field(None, ge=0)
    is_visible: Optional[bool] = True
    is_featured: Optional[bool] = False
    title: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    shipping_available: Optional[bool] = False
    shipping_cost: Optional[float] = Field(0.0, ge=0)
    pickup_only: Optional[bool] = True
    compatibility_override: Optional[dict] = None


class MarketplaceListingUpdate(BaseModel):
    public_price: Optional[float] = Field(None, gt=0)
    compare_at_price: Optional[float] = Field(None, ge=0)
    is_visible: Optional[bool] = None
    is_featured: Optional[bool] = None
    title: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    shipping_available: Optional[bool] = None
    shipping_cost: Optional[float] = Field(None, ge=0)
    pickup_only: Optional[bool] = None
    compatibility_override: Optional[dict] = None
    status: Optional[str] = Field(None, max_length=20)


class MarketplaceListingResponse(BaseModel):
    id: int
    tenant_id: int
    product_id: int
    public_price: float
    compare_at_price: Optional[float] = None
    is_visible: bool
    is_featured: bool
    title: Optional[str] = None
    description: Optional[str] = None
    slug: Optional[str] = None
    tags: Optional[List[str]] = None
    view_count: int
    sale_count: int
    avg_rating: float
    review_count: int
    shipping_available: bool
    shipping_cost: float
    pickup_only: bool
    compatibility_override: Optional[dict] = None
    status: str
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Product details snapshot
    product_name: str
    product_sku: Optional[str] = None
    product_brand: Optional[str] = None
    product_part_number: Optional[str] = None
    product_image_url: Optional[str] = None
    current_stock: int
    universal: bool
    compatible_brands: Optional[List[str]] = None
    compatible_models: Optional[List[str]] = None
    compatible_years: Optional[dict] = None

    # Workshop details
    workshop_name: str
    workshop_address: Optional[str] = None
    workshop_city: Optional[str] = None
    workshop_phone: Optional[str] = None

    class Config:
        from_attributes = True


class ListingCompareRequest(BaseModel):
    listing_ids: List[int]
