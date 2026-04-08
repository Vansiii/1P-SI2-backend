"""
Password management endpoints (consolidated).
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session, get_logger
from ...core.responses import create_success_response
from .schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ForgotPasswordMobileRequest,
    ForgotPasswordMobileResponse,
    VerifyPasswordOTPRequest,
    VerifyPasswordOTPResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
)
from .service import PasswordService
from ...shared.dependencies.auth import get_current_user
from ...models.user import User

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/forgot",
    response_model=ForgotPasswordResponse,
    summary="Request password reset",
    description="Request password reset via email",
)
async def forgot_password(
    request: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Request password reset via email."""
    password_service = PasswordService(session)
    message = await password_service.forgot_password(request.email)
    
    return create_success_response(
        data={"message": message},
        message=message,
    )


@router.post(
    "/forgot-mobile",
    response_model=ForgotPasswordMobileResponse,
    summary="Request password reset for mobile (OTP)",
    description="Request password reset via OTP code for mobile app",
)
async def forgot_password_mobile(
    request: ForgotPasswordMobileRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Request password reset via OTP for mobile."""
    password_service = PasswordService(session)
    message = await password_service.forgot_password_mobile(request.email)
    
    return create_success_response(
        data={"message": message},
        message=message,
    )


@router.post(
    "/verify-otp",
    response_model=VerifyPasswordOTPResponse,
    summary="Verify password reset OTP",
    description="Verify OTP code and get reset token for mobile",
)
async def verify_password_otp(
    request: VerifyPasswordOTPRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Verify OTP code and get reset token."""
    password_service = PasswordService(session)
    reset_token = await password_service.verify_password_otp(
        request.email, 
        request.otp_code
    )
    
    return create_success_response(
        data={
            "message": "Código verificado exitosamente",
            "reset_token": reset_token,
        },
        message="Código verificado exitosamente",
    )


@router.post(
    "/reset",
    response_model=ResetPasswordResponse,
    summary="Reset password with token",
    description="Reset password using recovery token",
)
async def reset_password(
    request: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Reset password using recovery token."""
    password_service = PasswordService(session)
    message = await password_service.reset_password(request.token, request.new_password)
    
    return create_success_response(
        data={"message": message},
        message=message,
    )


@router.post(
    "/change",
    response_model=ChangePasswordResponse,
    summary="Change password",
    description="Change password from authenticated profile",
)
async def change_password(
    request: ChangePasswordRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Change password from authenticated profile."""
    password_service = PasswordService(session)
    message = await password_service.change_password(
        current_user.id,
        request.current_password,
        request.new_password,
    )
    
    return create_success_response(
        data={"message": message},
        message=message,
    )
