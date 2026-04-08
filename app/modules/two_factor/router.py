"""
Two-factor authentication endpoints.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session, get_logger
from ...core.responses import create_success_response
from .schemas import (
    Enable2FARequest,
    Enable2FAResponse,
    VerifyOTPRequest,
    VerifyOTPResponse,
    Disable2FARequest,
    Disable2FAResponse,
    ResendOTPRequest,
    ResendOTPResponse,
    TwoFactorStatus,
)
from .service import TwoFactorService
from ...shared.dependencies.auth import get_current_user
from ...models.user import User

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/status",
    response_model=TwoFactorStatus,
    summary="Get 2FA status",
    description="Get current two-factor authentication status",
)
async def get_2fa_status(
    current_user: User = Depends(get_current_user),
):
    """Get current 2FA status."""
    return create_success_response(
        data={
            "enabled": current_user.two_factor_enabled,
            "backup_codes_count": 0,  # For future implementation
        },
        message="Estado de 2FA obtenido exitosamente",
    )


@router.post(
    "/enable",
    response_model=Enable2FAResponse,
    summary="Enable 2FA",
    description="Start the process to enable two-factor authentication",
)
async def enable_2fa(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Enable two-factor authentication."""
    two_factor_service = TwoFactorService(session)
    result = await two_factor_service.enable_2fa(current_user.email)
    
    return create_success_response(
        data=result,
        message=result["message"],
    )


@router.post(
    "/verify",
    response_model=VerifyOTPResponse,
    summary="Verify OTP code",
    description="Verify OTP code to complete 2FA activation",
)
async def verify_otp(
    request: VerifyOTPRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Verify OTP code to complete 2FA activation."""
    two_factor_service = TwoFactorService(session)
    result = await two_factor_service.verify_otp_code(current_user.email, request.otp)
    
    return create_success_response(
        data=result,
        message=result["message"],
    )


@router.post(
    "/disable",
    response_model=Disable2FAResponse,
    summary="Disable 2FA",
    description="Disable two-factor authentication",
)
async def disable_2fa(
    request: Disable2FARequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Disable two-factor authentication."""
    two_factor_service = TwoFactorService(session)
    result = await two_factor_service.disable_2fa(current_user, request.password)
    
    return create_success_response(
        data=result,
        message=result["message"],
    )


@router.post(
    "/resend",
    response_model=ResendOTPResponse,
    summary="Resend OTP code",
    description="Resend OTP verification code",
)
async def resend_otp(
    request: ResendOTPRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Resend OTP verification code."""
    two_factor_service = TwoFactorService(session)
    result = await two_factor_service.resend_otp(request.email)
    
    return create_success_response(
        data=result,
        message=result["message"],
    )
