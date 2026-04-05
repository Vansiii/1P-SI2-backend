from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db_session
from ..models.revoked_token import RevokedToken
from ..models.workshop_user import WorkshopUser
from ..schemas.auth import TokenPayload
from ..security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_token_payload(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> TokenPayload:
    token_data = decode_access_token(token)

    try:
        token_payload = TokenPayload.model_validate(token_data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido",
        ) from exc

    revoked_token = await session.scalar(select(RevokedToken).where(RevokedToken.jti == token_payload.jti))
    if revoked_token is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revocado. Inicia sesion nuevamente",
        )

    return token_payload


async def get_current_workshop_user(
    token_payload: TokenPayload = Depends(get_current_token_payload),
    session: AsyncSession = Depends(get_db_session),
) -> WorkshopUser:
    if token_payload.role != "workshop":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para esta operacion",
        )

    try:
        user_id = int(token_payload.sub)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido",
        ) from exc

    workshop_user = await session.scalar(select(WorkshopUser).where(WorkshopUser.id == user_id))
    if workshop_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )

    if not workshop_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El taller esta inactivo",
        )

    return workshop_user
