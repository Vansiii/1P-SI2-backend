"""
Core response formatting module for consistent API responses.
"""
from datetime import datetime, UTC
from typing import Any, Generic, TypeVar
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Error detail model."""
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: dict[str, Any] = Field(...)
    request_id: str = Field(...)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success response model."""
    data: T
    message: str | None = None
    request_id: str = Field(...)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response model."""
    data: list[T]
    pagination: dict[str, Any]
    request_id: str = Field(...)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


def create_error_response(
    message: str,
    code: str,
    status_code: int = 500,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Create standardized error response."""
    error_data = {
        "code": code,
        "message": message,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    
    if details:
        error_data["details"] = details
    
    if request_id:
        error_data["request_id"] = request_id
    else:
        error_data["request_id"] = str(uuid4())
    
    return JSONResponse(
        status_code=status_code,
        content={"error": error_data},
        headers={
            "Content-Type": "application/json",
        },
    )


def create_success_response(
    data: Any,
    message: str | None = None,
    status_code: int = 200,
    request_id: str | None = None,
) -> JSONResponse:
    """Create standardized success response."""
    response_data = {
        "data": data,
        "timestamp": datetime.now(UTC).isoformat(),
        "request_id": request_id or str(uuid4()),
    }
    
    if message:
        response_data["message"] = message
    
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(response_data),
    )


def create_paginated_response(
    data: list[Any],
    total: int,
    page: int,
    size: int,
    request_id: str | None = None,
) -> JSONResponse:
    """Create standardized paginated response."""
    total_pages = (total + size - 1) // size  # Ceiling division
    
    pagination = {
        "total": total,
        "page": page,
        "size": size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }
    
    response_data = {
        "data": data,
        "pagination": pagination,
        "timestamp": datetime.now(UTC).isoformat(),
        "request_id": request_id or str(uuid4()),
    }
    
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(response_data),
    )


def get_request_id(request: Request) -> str:
    """Get request ID from request state or generate new one."""
    return getattr(request.state, "request_id", str(uuid4()))