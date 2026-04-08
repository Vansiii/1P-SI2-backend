"""
Schemas for token operations.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from ...shared.schemas.base import BaseSchema


class TokenPair(BaseSchema):
    """Token pair response schema."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token."""
    refresh_token: str


class TokenResponse(BaseSchema):
    """Standard token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenInfo(BaseSchema):
    """Token information response."""
    user_id: int
    email: str
    user_type: str
    expires_at: datetime
    is_active: bool


class RevokeTokenRequest(BaseModel):
    """Request to revoke a token."""
    refresh_token: Optional[str] = None
    revoke_all: bool = False