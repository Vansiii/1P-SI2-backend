from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ProductReviewCreate(BaseModel):
    listing_id: int
    order_id: int
    rating: int = Field(..., ge=1, le=5)
    title: Optional[str] = Field(None, max_length=200)
    comment: Optional[str] = None


class ProductReviewResponse(BaseModel):
    id: int
    listing_id: int
    client_id: int
    order_id: int
    tenant_id: int
    rating: int
    title: Optional[str] = None
    comment: Optional[str] = None
    is_verified: bool
    is_visible: bool
    created_at: datetime
    updated_at: datetime
    
    # Client name snapshot
    client_name: str

    class Config:
        from_attributes = True
