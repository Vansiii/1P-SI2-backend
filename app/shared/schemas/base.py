"""
Base schemas for common patterns.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    
    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        arbitrary_types_allowed=False,
        str_strip_whitespace=True,
    )


class TimestampMixin(BaseModel):
    """Mixin for schemas with timestamp fields."""
    
    created_at: datetime = Field(..., description="Fecha de creación")
    updated_at: datetime = Field(..., description="Fecha de última actualización")


class IDMixin(BaseModel):
    """Mixin for schemas with ID field."""
    
    id: int = Field(..., description="Identificador único")


class BaseCreateSchema(BaseSchema):
    """Base schema for create operations."""
    pass


class BaseUpdateSchema(BaseSchema):
    """Base schema for update operations."""
    pass


class BaseResponseSchema(BaseSchema, IDMixin, TimestampMixin):
    """Base schema for response objects with ID and timestamps."""
    pass


class BasePublicSchema(BaseSchema, IDMixin):
    """Base schema for public response objects (without timestamps)."""
    pass