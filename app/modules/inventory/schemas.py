from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal
from datetime import datetime


# === Product Schemas ===

class InventoryProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    sku: Optional[str] = Field(None, max_length=50)
    barcode: Optional[str] = Field(None, max_length=50)
    brand: Optional[str] = Field(None, max_length=100)
    part_number: Optional[str] = Field(None, max_length=100)
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None
    current_stock: int = Field(default=0, ge=0)
    min_stock: int = Field(default=0, ge=0)
    max_stock: Optional[int] = Field(None, ge=0)
    unit: str = Field(default="unidad", max_length=20)
    location: Optional[str] = Field(None, max_length=100)
    cost_price: float = Field(default=0.0, ge=0.0)
    compatible_brands: Optional[list[str]] = None
    compatible_models: Optional[list[str]] = None
    compatible_years: Optional[dict] = None
    universal: bool = False
    image_url: Optional[str] = None
    images: Optional[list[str]] = None


class InventoryProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    sku: Optional[str] = Field(None, max_length=50)
    barcode: Optional[str] = Field(None, max_length=50)
    brand: Optional[str] = Field(None, max_length=100)
    part_number: Optional[str] = Field(None, max_length=100)
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None
    min_stock: Optional[int] = Field(None, ge=0)
    max_stock: Optional[int] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=20)
    location: Optional[str] = Field(None, max_length=100)
    cost_price: Optional[float] = Field(None, ge=0.0)
    compatible_brands: Optional[list[str]] = None
    compatible_models: Optional[list[str]] = None
    compatible_years: Optional[dict] = None
    universal: Optional[bool] = None
    image_url: Optional[str] = None
    images: Optional[list[str]] = None


class InventoryProductFilter(BaseModel):
    search: Optional[str] = None
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None
    low_stock: Optional[bool] = None
    out_of_stock: Optional[bool] = None
    is_published: Optional[bool] = None
    is_active: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


# === Movement Schemas ===

class InventoryMovementCreate(BaseModel):
    product_id: int
    type: Literal["entrada", "salida", "ajuste", "devolucion"]
    quantity: int = Field(..., gt=0)
    unit_cost: Optional[float] = Field(None, ge=0.0)
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_cost_for_entrada(self):
        if self.type == "entrada" and self.unit_cost is None:
            raise ValueError("unit_cost es requerido para entradas")
        return self


# === Category Schemas ===

class InventoryCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    parent_id: Optional[int] = None


class InventoryCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon: Optional[str] = Field(None, max_length=50)
    parent_id: Optional[int] = None
