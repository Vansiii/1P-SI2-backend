from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.revoked_token import RevokedToken
from ..models.workshop_user import WorkshopUser
from ..schemas.auth import (
    TokenPayload,
    TokenResponse,
    WorkshopLoginRequest,
    WorkshopPublic,
    WorkshopRegistrationRequest,
)
from ..security import create_access_token, hash_password, verify_password


def _build_token_response(user: WorkshopUser) -> TokenResponse:
    access_token, expires_at = create_access_token(
        subject=str(user.id),
        email=user.email,
        role=user.role,
    )
    expires_in_seconds = max(int((expires_at - datetime.now(UTC)).total_seconds()), 1)

    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in_seconds,
        user=WorkshopPublic.model_validate(user),
    )


async def register_workshop(
    session: AsyncSession,
    registration_request: WorkshopRegistrationRequest,
) -> TokenResponse:
    existing_user = await session.scalar(
        select(WorkshopUser).where(WorkshopUser.email == registration_request.email)
    )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un taller registrado con este correo",
        )

    workshop_user = WorkshopUser(
        workshop_name=registration_request.workshop_name,
        owner_name=registration_request.owner_name,
        email=registration_request.email,
        phone=registration_request.phone,
        password_hash=hash_password(registration_request.password),
        role="workshop",
        is_active=True,
    )
    session.add(workshop_user)
    await session.commit()
    await session.refresh(workshop_user)

    return _build_token_response(workshop_user)


async def login_workshop(
    session: AsyncSession,
    login_request: WorkshopLoginRequest,
) -> TokenResponse:
    workshop_user = await session.scalar(select(WorkshopUser).where(WorkshopUser.email == login_request.email))
    if workshop_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas",
        )

    if not verify_password(login_request.password, workshop_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas",
        )

    if not workshop_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El taller esta inactivo. Contacta al administrador",
        )

    return _build_token_response(workshop_user)


async def revoke_access_token(session: AsyncSession, token_payload: TokenPayload) -> None:
    already_revoked = await session.scalar(select(RevokedToken).where(RevokedToken.jti == token_payload.jti))
    if already_revoked is not None:
        return

    revoked_token = RevokedToken(
        jti=token_payload.jti,
        expires_at=datetime.fromtimestamp(token_payload.exp, tz=UTC),
    )
    session.add(revoked_token)
    await session.commit()
