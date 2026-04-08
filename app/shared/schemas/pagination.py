"""
Pagination schemas for consistent API responses.
"""
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from .base import BaseSchema

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Simple pagination parameters."""
    
    limit: int = Field(default=50, ge=1, le=200, description="Maximum number of items to return")
    offset: int = Field(default=0, ge=0, description="Number of items to skip")


class PaginationMeta(BaseModel):
    """Pagination metadata."""
    
    total: int = Field(..., ge=0, description="Total de elementos")
    limit: int = Field(..., ge=1, description="Límite de elementos")
    offset: int = Field(..., ge=0, description="Elementos omitidos")
    has_more: bool = Field(..., description="Hay más elementos")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""
    
    data: list[T] = Field(..., description="Lista de elementos")
    pagination: PaginationMeta = Field(..., description="Metadatos de paginación")
    
    @classmethod
    def create(
        cls,
        data: list[T],
        total: int,
        limit: int,
        offset: int,
    ) -> "PaginatedResponse[T]":
        """Create paginated response with calculated metadata."""
        has_more = offset + len(data) < total
        
        pagination = PaginationMeta(
            total=total,
            limit=limit,
            offset=offset,
            has_more=has_more,
        )
        
        return cls(data=data, pagination=pagination)