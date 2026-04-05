from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db_session
from ..dependencies.auth import get_current_token_payload, get_current_workshop_user
from ..models.workshop_user import WorkshopUser
from ..schemas.auth import (
    LogoutResponse,
    TokenPayload,
    TokenResponse,
    WorkshopLoginRequest,
    WorkshopPublic,
    WorkshopRegistrationRequest,
)
from ..services.auth_service import login_workshop, register_workshop, revoke_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["autenticacion"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_workshop_account(
    registration_request: WorkshopRegistrationRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    return await register_workshop(session, registration_request)


@router.post("/login", response_model=TokenResponse)
async def login_workshop_account(
    login_request: WorkshopLoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    return await login_workshop(session, login_request)


@router.post("/logout", response_model=LogoutResponse)
async def logout_workshop_account(
    token_payload: TokenPayload = Depends(get_current_token_payload),
    session: AsyncSession = Depends(get_db_session),
) -> LogoutResponse:
    await revoke_access_token(session, token_payload)
    return LogoutResponse(message="Sesion cerrada correctamente")


@router.get("/me", response_model=WorkshopPublic)
async def get_current_workshop_profile(
    workshop_user: WorkshopUser = Depends(get_current_workshop_user),
) -> WorkshopPublic:
    return WorkshopPublic.model_validate(workshop_user)
