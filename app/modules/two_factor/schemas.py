"""
Schemas for two-factor authentication operations.
"""
from pydantic import BaseModel, Field

from ...shared.schemas.base import BaseSchema


class Enable2FARequest(BaseModel):
    """Request to enable 2FA."""
    email: str = Field(..., description="User email address")


class Enable2FAResponse(BaseSchema):
    """Response for 2FA enable request."""
    message: str
    email: str


class VerifyOTPRequest(BaseModel):
    """Request to verify OTP code."""
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")


class VerifyOTPResponse(BaseSchema):
    """Response for OTP verification."""
    message: str
    two_factor_enabled: bool


class Disable2FARequest(BaseModel):
    """Request to disable 2FA."""
    password: str = Field(..., description="Current password for verification")


class Disable2FAResponse(BaseSchema):
    """Response for 2FA disable."""
    message: str
    two_factor_enabled: bool


class ResendOTPRequest(BaseModel):
    """Request to resend OTP code."""
    email: str = Field(..., description="User email address")


class ResendOTPResponse(BaseSchema):
    """Response for OTP resend."""
    message: str
    email: str


class TwoFactorStatus(BaseSchema):
    """Two-factor authentication status."""
    enabled: bool
    backup_codes_count: int = 0  # For future implementation