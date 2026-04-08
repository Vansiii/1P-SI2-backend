"""
Schemas for password operations.
"""
from pydantic import BaseModel, Field

from ...shared.schemas.base import BaseSchema


class ForgotPasswordRequest(BaseModel):
    """Request to initiate password recovery."""
    email: str = Field(..., description="User email address")


class ForgotPasswordResponse(BaseSchema):
    """Response for password recovery request."""
    message: str


class ForgotPasswordMobileRequest(BaseModel):
    """Request to initiate password recovery for mobile (OTP)."""
    email: str = Field(..., description="User email address")


class ForgotPasswordMobileResponse(BaseSchema):
    """Response for mobile password recovery request."""
    message: str


class VerifyPasswordOTPRequest(BaseModel):
    """Request to verify password reset OTP code."""
    email: str = Field(..., description="User email address")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")


class VerifyPasswordOTPResponse(BaseSchema):
    """Response for OTP verification."""
    message: str
    reset_token: str = Field(..., description="Token to use for password reset")


class ResetPasswordRequest(BaseModel):
    """Request to reset password with token."""
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, description="New password")


class ResetPasswordResponse(BaseSchema):
    """Response for password reset."""
    message: str


class ChangePasswordRequest(BaseModel):
    """Request to change password from profile."""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")


class ChangePasswordResponse(BaseSchema):
    """Response for password change."""
    message: str