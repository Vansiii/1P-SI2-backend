from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class PromotionCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    type: str = Field(..., description="percentage, fixed_amount")
    value: float = Field(..., gt=0)
    applies_to: str = Field(default="all", description="all, category, product, listing")
    target_ids: Optional[List[int]] = None
    starts_at: datetime
    ends_at: datetime
    max_uses: Optional[int] = Field(None, gt=0)
    min_purchase: Optional[float] = Field(0.0, ge=0)


class PromotionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    value: Optional[float] = Field(None, gt=0)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    max_uses: Optional[int] = Field(None, gt=0)
    min_purchase: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None


class PromotionResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    description: Optional[str] = None
    type: str
    value: float
    applies_to: str
    target_ids: Optional[List[int]] = None
    starts_at: datetime
    ends_at: datetime
    max_uses: Optional[int] = None
    current_uses: int
    min_purchase: float
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
