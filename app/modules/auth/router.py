"""
Consolidated authentication router with improved organization.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session, get_logger
from ...core.responses import create_success_response
from ...shared.dependencies.auth import get_current_user
from ...models.user import User
from .schemas import (
    AdministratorRegistrationRequest,
    ClientRegistrationRequest,
    DeleteAccountRequest,
    Login2FARequest,
    LoginRequest,
    TechnicianRegistrationRequest,
    UpdateProfileRequest,
    WorkshopRegistrationRequest,
)
from .services import AuthService, ProfileService, RegistrationService

logger = get_logger(__name__)

router = APIRouter(tags=["Authentication"])


# Registration endpoints
@router.post(
    "/register/client",
    status_code=status.HTTP_201_CREATED,
    summary="Register new client",
    description="Register a new client user account",
)
async def register_client(
    request: ClientRegistrationRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Register a new client user."""
    registration_service = RegistrationService(session)
    client, token_response = await registration_service.register_client(request)
    
    return create_success_response(
        data={
            "user": {
                "id": client.id,
                "email": client.email,
                "user_type": client.user_type,
                "direccion": client.direccion,
                "ci": client.ci,
                "fecha_nacimiento": client.fecha_nacimiento.isoformat(),
            },
            "tokens": token_response.model_dump(),
        },
        message="Cliente registrado exitosamente",
        status_code=status.HTTP_201_CREATED,
    )


@router.post(
    "/register/workshop",
    status_code=status.HTTP_201_CREATED,
    summary="Register new workshop",
    description="Register a new workshop user account",
)
async def register_workshop(
    request: WorkshopRegistrationRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Register a new workshop user."""
    registration_service = RegistrationService(session)
    workshop, token_response = await registration_service.register_workshop(request)
    
    return create_success_response(
        data={
            "user": {
                "id": workshop.id,
                "email": workshop.email,
                "user_type": workshop.user_type,
                "workshop_name": workshop.workshop_name,
                "owner_name": workshop.owner_name,
                "latitude": workshop.latitude,
                "longitude": workshop.longitude,
                "coverage_radius_km": workshop.coverage_radius_km,
            },
            "tokens": token_response.model_dump(),
        },
        message="Taller registrado exitosamente",
        status_code=status.HTTP_201_CREATED,
    )


@router.post(
    "/register/technician",
    status_code=status.HTTP_201_CREATED,
    summary="Register new technician",
    description="Register a new technician user account",
)
async def register_technician(
    request: TechnicianRegistrationRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Register a new technician user."""
    registration_service = RegistrationService(session)
    technician, token_response = await registration_service.register_technician(request)
    
    return create_success_response(
        data={
            "user": {
                "id": technician.id,
                "email": technician.email,
                "user_type": technician.user_type,
                "workshop_id": technician.workshop_id,
                "current_latitude": technician.current_latitude,
                "current_longitude": technician.current_longitude,
                "is_available": technician.is_available,
            },
            "tokens": token_response.model_dump(),
        },
        message="Técnico registrado exitosamente",
        status_code=status.HTTP_201_CREATED,
    )


@router.post(
    "/register/administrator",
    status_code=status.HTTP_201_CREATED,
    summary="Register new administrator",
    description="Register a new administrator user account",
)
async def register_administrator(
    request: AdministratorRegistrationRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Register a new administrator user."""
    registration_service = RegistrationService(session)
    admin, token_response = await registration_service.register_administrator(request)
    
    return create_success_response(
        data={
            "user": {
                "id": admin.id,
                "email": admin.email,
                "user_type": admin.user_type,
                "role_level": admin.role_level,
            },
            "tokens": token_response.model_dump(),
        },
        message="Administrador registrado exitosamente",
        status_code=status.HTTP_201_CREATED,
    )


# Authentication endpoints
@router.post(
    "/login",
    summary="User login",
    description="Authenticate user and return access tokens",
)
async def login(
    login_request: LoginRequest,
    raw_request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """Authenticate user and return tokens."""
    from ...core import InvalidCredentialsException
    from ...core.constants import UserType
    from ...modules.auth.repository import UserRepository
    from ...core.security import verify_password, create_access_token, create_refresh_token
    from ...models.refresh_token import RefreshToken
    from datetime import timedelta, UTC
    
    client_ip = raw_request.client.host if raw_request.client else "unknown"
    user_agent = raw_request.headers.get("user-agent")
    
    email = login_request.email.strip().lower()
    
    # Find user by email
    user_repo = UserRepository(session)
    user = await user_repo.find_active_by_email(email)
    
    if not user:
        logger.warning("Login attempt with non-existent email", email=email)
        raise InvalidCredentialsException("Email o contraseña incorrectos")
    
    # Verify password
    if not verify_password(login_request.password, user.password_hash):
        logger.warning("Login attempt with invalid password", user_id=user.id, email=email)
        raise InvalidCredentialsException("Email o contraseña incorrectos")
    
    # Check if 2FA is enabled
    if user.two_factor_enabled:
        from ...modules.two_factor.service import TwoFactorService
        two_factor_service = TwoFactorService(session)
        await two_factor_service.generate_login_otp(user.email)
        
        return create_success_response(
            data={
                "requires_2fa": True,
                "user_type": user.user_type,
                "message": "Se requiere autenticación de dos factores",
            },
            message="2FA requerido",
        )
    
    # Generate tokens
    access_token, expires_at, jti = create_access_token(
        subject=str(user.id),
        email=user.email,
        user_type=user.user_type,
    )
    
    refresh_token, refresh_token_hash = create_refresh_token()
    
    # Save refresh token
    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=refresh_token_hash,
        jti=jti,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    
    session.add(refresh_token_record)
    await session.commit()
    
    # Update last login
    await user_repo.update_last_login(user.id)
    
    logger.info("User logged in successfully", user_id=user.id, email=email, user_type=user.user_type)
    
    return create_success_response(
        data={
            "user": {
                "id": user.id,
                "email": user.email,
                "user_type": user.user_type,
            },
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": 30 * 60,  # 30 minutes
            },
        },
        message="Login exitoso",
    )


@router.post(
    "/login/verify-2fa",
    summary="Verify 2FA code for login",
    description="Verify OTP code and complete login with 2FA",
)
async def verify_2fa_login(
    request: Login2FARequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Verify 2FA code and complete login."""
    from ...modules.two_factor.service import TwoFactorService
    
    # Verify OTP code
    two_factor_service = TwoFactorService(session)
    await two_factor_service.verify_login_otp(request.email, request.otp_code)
    
    # Generate tokens after successful verification
    auth_service = AuthService(session)
    user, token_response = await auth_service.complete_2fa_login(request.email)
    
    return create_success_response(
        data={
            "user": {
                "id": user.id,
                "email": user.email,
                "user_type": user.user_type,
            },
            "tokens": {
                "access_token": token_response.access_token,
                "refresh_token": token_response.refresh_token,
                "token_type": token_response.token_type,
                "expires_in": token_response.expires_in,
            },
        },
        message="Login exitoso",
    )


@router.post(
    "/logout",
    summary="User logout",
    description="Logout user and revoke tokens",
)
async def logout(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Logout user and revoke tokens."""
    auth_service = AuthService(session)
    await auth_service.logout(current_user.id)
    
    return create_success_response(
        data={"message": "Logout exitoso"},
        message="Sesión cerrada correctamente",
    )


# Profile endpoints
@router.get(
    "/me",
    summary="Get current user profile",
    description="Get the current authenticated user's profile",
)
async def get_profile(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get current user profile."""
    from sqlalchemy import select
    from ...models.client import Client
    from ...models.workshop import Workshop
    from ...models.technician import Technician
    from ...models.administrator import Administrator
    
    # Build response based on user type
    user_data = {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "phone": current_user.phone,
        "user_type": current_user.user_type,
        "is_active": current_user.is_active,
        "two_factor_enabled": current_user.two_factor_enabled,
        "created_at": current_user.created_at.isoformat(),
        "updated_at": current_user.updated_at.isoformat(),
    }
    
    # Load type-specific data
    if current_user.user_type == "client":
        result = await session.execute(select(Client).where(Client.id == current_user.id))
        client = result.scalar_one_or_none()
        if client:
            user_data.update({
                "direccion": client.direccion,
                "ci": client.ci,
                "fecha_nacimiento": client.fecha_nacimiento.isoformat() if client.fecha_nacimiento else None,
            })
    elif current_user.user_type == "workshop":
        result = await session.execute(select(Workshop).where(Workshop.id == current_user.id))
        workshop = result.scalar_one_or_none()
        if workshop:
            user_data.update({
                "workshop_name": workshop.workshop_name,
                "owner_name": workshop.owner_name,
                "address": workshop.address,
                "direccion": workshop.address,  # Alias para compatibilidad con frontend
                "workshop_phone": workshop.workshop_phone,
                "latitude": float(workshop.latitude) if workshop.latitude else None,
                "longitude": float(workshop.longitude) if workshop.longitude else None,
                "coverage_radius_km": float(workshop.coverage_radius_km) if workshop.coverage_radius_km else None,
            })
    elif current_user.user_type == "technician":
        result = await session.execute(select(Technician).where(Technician.id == current_user.id))
        technician = result.scalar_one_or_none()
        if technician:
            user_data.update({
                "workshop_id": technician.workshop_id,
                "current_latitude": float(technician.current_latitude) if technician.current_latitude else None,
                "current_longitude": float(technician.current_longitude) if technician.current_longitude else None,
                "is_available": technician.is_available,
            })
    elif current_user.user_type == "admin":
        result = await session.execute(select(Administrator).where(Administrator.id == current_user.id))
        admin = result.scalar_one_or_none()
        if admin:
            user_data.update({
                "role_level": admin.role_level,
            })
    
    return create_success_response(
        data=user_data,
        message="Perfil obtenido exitosamente",
    )


@router.patch(
    "/me",
    summary="Update current user profile",
    description="Update the current authenticated user's profile",
)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Update current user profile."""
    profile_service = ProfileService(session)
    updated_user = await profile_service.update_profile(current_user.id, request)
    
    return create_success_response(
        data={
            "id": updated_user.id,
            "email": updated_user.email,
            "user_type": updated_user.user_type,
            "updated_at": updated_user.updated_at.isoformat(),
        },
        message="Perfil actualizado exitosamente",
    )


@router.delete(
    "/me",
    summary="Delete current user account",
    description="Delete the current authenticated user's account",
)
async def delete_account(
    request: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Delete current user account."""
    profile_service = ProfileService(session)
    await profile_service.delete_account(current_user.id, request.password)
    
    return create_success_response(
        data={
            "deleted_at": datetime.now().isoformat(),
            "message": "Cuenta eliminada exitosamente",
        },
        message="Cuenta eliminada correctamente",
    )