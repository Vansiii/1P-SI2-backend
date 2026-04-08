"""
Enhanced authentication dependencies with better error handling.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import (
    AccountLockedException,
    AuthenticationException,
    AuthorizationException,
    InvalidTokenException,
    UserNotFoundException,
    decode_access_token,
    get_db_session,
    get_logger,
)
from ...core.constants import ErrorCode, ErrorMessage, UserType
from ...models.administrator import Administrator
from ...models.client import Client
from ...models.revoked_token import RevokedToken
from ...models.technician import Technician
from ...models.user import User
from ...models.workshop import Workshop
from ...modules.auth.schemas import TokenPayload

logger = get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_token_payload(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> TokenPayload:
    """
    Validate JWT token and return payload.
    
    Raises:
        InvalidTokenException: If token is invalid or malformed
        AuthenticationException: If token is revoked
    """
    try:
        token_data = decode_access_token(token)
        token_payload = TokenPayload.model_validate(token_data)
    except ValidationError as exc:
        logger.warning("Invalid token payload", token_preview=token[:20], error=str(exc))
        raise InvalidTokenException() from exc
    except HTTPException as exc:
        # Re-raise HTTPException from decode_access_token as our custom exception
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            raise InvalidTokenException() from exc
        raise

    # Check if token is revoked
    try:
        revoked_token = await session.scalar(
            select(RevokedToken).where(RevokedToken.jti == token_payload.jti)
        )
        if revoked_token is not None:
            logger.info("Revoked token used", jti=token_payload.jti, user_id=token_payload.sub)
            raise AuthenticationException(
                message="Token revocado. Inicia sesión nuevamente",
                code=ErrorCode.INVALID_TOKEN,
            )
    except Exception as exc:
        if isinstance(exc, AuthenticationException):
            raise
        logger.error("Error checking token revocation", jti=token_payload.jti, error=str(exc))
        raise AuthenticationException(
            message="Error validating token",
            code=ErrorCode.INVALID_TOKEN,
        ) from exc

    return token_payload


async def get_current_user(
    token_payload: TokenPayload = Depends(get_current_token_payload),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """
    Get current user (any type).
    Useful for endpoints that accept any authenticated user.
    
    Raises:
        UserNotFoundException: If user doesn't exist
        AccountLockedException: If user account is inactive
    """
    try:
        user_id = int(token_payload.sub)
    except ValueError as exc:
        logger.warning("Invalid user ID in token", sub=token_payload.sub)
        raise InvalidTokenException() from exc

    try:
        user = await session.scalar(select(User).where(User.id == user_id))
        if user is None:
            logger.warning("User not found", user_id=user_id)
            raise UserNotFoundException(user_id)

        if not user.is_active:
            logger.info("Inactive user attempted access", user_id=user_id, email=user.email)
            raise AccountLockedException()

        # Adjuntar el JTI al usuario para uso en endpoints de sesiones
        setattr(user, "_current_jti", token_payload.jti)

        return user
        
    except Exception as exc:
        if isinstance(exc, (UserNotFoundException, AccountLockedException)):
            raise
        logger.error("Error fetching user", user_id=user_id, error=str(exc))
        raise AuthenticationException(
            message="Error validating user",
            code=ErrorCode.INVALID_TOKEN,
        ) from exc


async def get_current_client(
    token_payload: TokenPayload = Depends(get_current_token_payload),
    session: AsyncSession = Depends(get_db_session),
) -> Client:
    """
    Get current client user.
    
    Raises:
        AuthorizationException: If user is not a client
        UserNotFoundException: If client doesn't exist
        AccountLockedException: If client account is inactive
    """
    if token_payload.user_type != UserType.CLIENT:
        logger.warning(
            "Non-client user attempted client access",
            user_id=token_payload.sub,
            user_type=token_payload.user_type,
        )
        raise AuthorizationException(
            message="Solo clientes pueden acceder a este recurso",
            required_permission="client_access",
        )

    try:
        user_id = int(token_payload.sub)
    except ValueError as exc:
        raise InvalidTokenException() from exc

    try:
        client = await session.scalar(select(Client).where(Client.id == user_id))
        if client is None:
            logger.warning("Client not found", user_id=user_id)
            raise UserNotFoundException(user_id)

        if not client.is_active:
            logger.info("Inactive client attempted access", user_id=user_id, email=client.email)
            raise AccountLockedException()

        return client
        
    except Exception as exc:
        if isinstance(exc, (UserNotFoundException, AccountLockedException, AuthorizationException)):
            raise
        logger.error("Error fetching client", user_id=user_id, error=str(exc))
        raise AuthenticationException(
            message="Error validating client",
            code=ErrorCode.INVALID_TOKEN,
        ) from exc


async def get_current_workshop_user(
    token_payload: TokenPayload = Depends(get_current_token_payload),
    session: AsyncSession = Depends(get_db_session),
) -> Workshop:
    """
    Get current workshop user.
    
    Raises:
        AuthorizationException: If user is not a workshop
        UserNotFoundException: If workshop doesn't exist
        AccountLockedException: If workshop account is inactive
    """
    if token_payload.user_type != UserType.WORKSHOP:
        logger.warning(
            "Non-workshop user attempted workshop access",
            user_id=token_payload.sub,
            user_type=token_payload.user_type,
        )
        raise AuthorizationException(
            message="Solo talleres pueden acceder a este recurso",
            required_permission="workshop_access",
        )

    try:
        user_id = int(token_payload.sub)
    except ValueError as exc:
        raise InvalidTokenException() from exc

    try:
        workshop = await session.scalar(select(Workshop).where(Workshop.id == user_id))
        if workshop is None:
            logger.warning("Workshop not found", user_id=user_id)
            raise UserNotFoundException(user_id)

        if not workshop.is_active:
            logger.info("Inactive workshop attempted access", user_id=user_id, email=workshop.email)
            raise AccountLockedException()

        return workshop
        
    except Exception as exc:
        if isinstance(exc, (UserNotFoundException, AccountLockedException, AuthorizationException)):
            raise
        logger.error("Error fetching workshop", user_id=user_id, error=str(exc))
        raise AuthenticationException(
            message="Error validating workshop",
            code=ErrorCode.INVALID_TOKEN,
        ) from exc


async def get_current_technician(
    token_payload: TokenPayload = Depends(get_current_token_payload),
    session: AsyncSession = Depends(get_db_session),
) -> Technician:
    """
    Get current technician user.
    
    Raises:
        AuthorizationException: If user is not a technician
        UserNotFoundException: If technician doesn't exist
        AccountLockedException: If technician account is inactive
    """
    if token_payload.user_type != UserType.TECHNICIAN:
        logger.warning(
            "Non-technician user attempted technician access",
            user_id=token_payload.sub,
            user_type=token_payload.user_type,
        )
        raise AuthorizationException(
            message="Solo técnicos pueden acceder a este recurso",
            required_permission="technician_access",
        )

    try:
        user_id = int(token_payload.sub)
    except ValueError as exc:
        raise InvalidTokenException() from exc

    try:
        technician = await session.scalar(select(Technician).where(Technician.id == user_id))
        if technician is None:
            logger.warning("Technician not found", user_id=user_id)
            raise UserNotFoundException(user_id)

        if not technician.is_active:
            logger.info("Inactive technician attempted access", user_id=user_id, email=technician.email)
            raise AccountLockedException()

        return technician
        
    except Exception as exc:
        if isinstance(exc, (UserNotFoundException, AccountLockedException, AuthorizationException)):
            raise
        logger.error("Error fetching technician", user_id=user_id, error=str(exc))
        raise AuthenticationException(
            message="Error validating technician",
            code=ErrorCode.INVALID_TOKEN,
        ) from exc


async def get_current_admin(
    token_payload: TokenPayload = Depends(get_current_token_payload),
    session: AsyncSession = Depends(get_db_session),
) -> Administrator:
    """
    Get current administrator user.
    
    Raises:
        AuthorizationException: If user is not an administrator
        UserNotFoundException: If administrator doesn't exist
        AccountLockedException: If administrator account is inactive
    """
    if token_payload.user_type != UserType.ADMINISTRATOR:
        logger.warning(
            "Non-admin user attempted admin access",
            user_id=token_payload.sub,
            user_type=token_payload.user_type,
        )
        raise AuthorizationException(
            message="Solo administradores pueden acceder a este recurso",
            required_permission="admin_access",
        )

    try:
        user_id = int(token_payload.sub)
    except ValueError as exc:
        raise InvalidTokenException() from exc

    try:
        admin = await session.scalar(select(Administrator).where(Administrator.id == user_id))
        if admin is None:
            logger.warning("Administrator not found", user_id=user_id)
            raise UserNotFoundException(user_id)

        if not admin.is_active:
            logger.info("Inactive admin attempted access", user_id=user_id, email=admin.email)
            raise AccountLockedException()

        return admin
        
    except Exception as exc:
        if isinstance(exc, (UserNotFoundException, AccountLockedException, AuthorizationException)):
            raise
        logger.error("Error fetching administrator", user_id=user_id, error=str(exc))
        raise AuthenticationException(
            message="Error validating administrator",
            code=ErrorCode.INVALID_TOKEN,
        ) from exc