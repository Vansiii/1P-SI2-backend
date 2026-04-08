"""
Token management endpoints.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session, get_logger
from ...core.responses import create_success_response
from .schemas import (
    RefreshTokenRequest,
    TokenResponse,
    RevokeTokenRequest,
)
from .service import TokenService
from ...shared.dependencies.auth import get_current_user
from ...models.user import User

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Refresh access token using refresh token",
)
async def refresh_token(
    request: RefreshTokenRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Refresh access token using refresh token."""
    token_service = TokenService(session)
    
    access_token, refresh_token, access_expires_at, refresh_expires_at = (
        await token_service.rotate_refresh_token(request.refresh_token)
    )
    
    # Calculate expires_in (seconds until access token expires)
    from datetime import datetime, UTC
    expires_in = int((access_expires_at - datetime.now(UTC)).total_seconds())
    
    return create_success_response(
        data={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": expires_in,
        },
        message="Token renovado exitosamente",
    )


@router.post(
    "/revoke",
    summary="Revoke tokens",
    description="Revoke refresh token or all user tokens",
)
async def revoke_tokens(
    request: RevokeTokenRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Revoke refresh token or all user tokens."""
    token_service = TokenService(session)
    
    if request.revoke_all:
        # Revoke all user tokens
        count = await token_service.revoke_all_user_tokens(current_user.id)
        message = f"Se revocaron {count} tokens"
    elif request.refresh_token:
        # Revoke specific refresh token
        success = await token_service.revoke_refresh_token(request.refresh_token)
        message = "Token revocado exitosamente" if success else "Token no encontrado"
    else:
        message = "No se especificó qué revocar"
    
    return create_success_response(
        data={"revoked": True},
        message=message,
    )


@router.post(
    "/cleanup",
    summary="Cleanup expired tokens",
    description="Clean up expired tokens (admin only)",
)
async def cleanup_expired_tokens(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Clean up expired tokens."""
    # TODO: Add admin authorization check
    token_service = TokenService(session)
    count = await token_service.cleanup_expired_tokens()
    
    return create_success_response(
        data={"deleted_count": count},
        message=f"Se eliminaron {count} tokens expirados",
    )
