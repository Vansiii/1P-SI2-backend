"""
Consolidated authentication router with improved organization.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, Request, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session, get_logger
from ...core.responses import create_success_response
from ...core.permissions import Permission
from ...core.dependencies import require_permission, CurrentUser
from ...core.exceptions import (
    EmailAlreadyExistsException,
    UserNotFoundException,
    WeakPasswordException,
)
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
                "latitude": float(workshop.latitude) if workshop.latitude else None,
                "longitude": float(workshop.longitude) if workshop.longitude else None,
                "coverage_radius_km": float(workshop.coverage_radius_km) if workshop.coverage_radius_km else None,
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
    try:
        registration_service = RegistrationService(session)
        technician, token_response = await registration_service.register_technician(request)
        
        return create_success_response(
            data={
                "user": {
                    "id": technician.id,
                    "email": technician.email,
                    "first_name": technician.first_name,
                    "last_name": technician.last_name,
                    "phone": technician.phone,
                    "user_type": technician.user_type,
                    "workshop_id": technician.workshop_id,
                    "current_latitude": technician.current_latitude,
                    "current_longitude": technician.current_longitude,
                    "is_available": technician.is_available,
                    "is_active": technician.is_active,
                },
                "tokens": token_response.model_dump(),
            },
            message="Técnico registrado exitosamente",
            status_code=status.HTTP_201_CREATED,
        )
    except UserNotFoundException as e:
        logger.error("Workshop not found during technician registration", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except EmailAlreadyExistsException as e:
        logger.error("Email already exists during technician registration", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El email {e.email} ya está registrado"
        )
    except WeakPasswordException as e:
        logger.error("Weak password during technician registration", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Contraseña débil: {e.message}"
        )
    except ValueError as e:
        logger.error("Validation error during technician registration", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Unexpected error during technician registration", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno del servidor al registrar técnico"
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


@router.post(
    "/validate/technician",
    summary="Validate technician registration data",
    description="Validate technician registration data before actual registration",
)
async def validate_technician_registration(
    request: TechnicianRegistrationRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """Validate technician registration data without creating the user."""
    try:
        registration_service = RegistrationService(session)
        
        # Check if email already exists
        if await registration_service.user_repo.email_exists(request.email):
            return create_success_response(
                data={"valid": False, "errors": [f"El email {request.email} ya está registrado"]},
                message="Datos de validación procesados",
            )
        
        # Verify workshop exists and is active
        workshop = await registration_service.workshop_repo.find_by_id(request.workshop_id)
        if not workshop:
            return create_success_response(
                data={"valid": False, "errors": [f"Taller con ID {request.workshop_id} no encontrado"]},
                message="Datos de validación procesados",
            )
        
        if not workshop.is_active:
            return create_success_response(
                data={"valid": False, "errors": [f"El taller {workshop.business_name} no está activo"]},
                message="Datos de validación procesados",
            )
        
        # Verify specialties exist if provided
        errors = []
        if request.specialty_ids:
            from sqlalchemy import select
            from ...models.especialidad import Especialidad
            
            existing_specialties = await session.scalars(
                select(Especialidad.id).where(Especialidad.id.in_(request.specialty_ids))
            )
            existing_ids = set(existing_specialties.all())
            missing_ids = set(request.specialty_ids) - existing_ids
            
            if missing_ids:
                errors.append(f"Especialidades no encontradas: {list(missing_ids)}")
        
        if errors:
            return create_success_response(
                data={"valid": False, "errors": errors},
                message="Datos de validación procesados",
            )
        
        return create_success_response(
            data={
                "valid": True, 
                "workshop_name": workshop.business_name,
                "message": "Todos los datos son válidos para el registro"
            },
            message="Validación exitosa",
        )
        
    except Exception as e:
        logger.error("Error during technician validation", error=str(e))
        return create_success_response(
            data={"valid": False, "errors": [f"Error de validación: {str(e)}"]},
            message="Error en validación",
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
    client_ip = raw_request.client.host if raw_request.client else "unknown"
    user_agent = raw_request.headers.get("user-agent")
    
    # Use AuthService for proper login handling with failed attempts tracking
    auth_service = AuthService(session)
    user, token_response = await auth_service.login(
        login_request,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    
    # Check if 2FA is required
    if token_response.requires_2fa:
        return create_success_response(
            data={
                "requires_2fa": True,
                "user_type": user.user_type,
                "email": user.email,
                "message": "Se requiere autenticación de dos factores",
            },
            message="2FA requerido",
        )
    
    # Return successful login response
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
    dependencies=[Depends(require_permission(Permission.PROFILE_VIEW_OWN))],
)
async def get_profile(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get current user profile - optimized with single query using polymorphic loading."""
    from sqlalchemy import select
    from ...models.client import Client
    from ...models.workshop import Workshop
    from ...models.technician import Technician
    from ...models.administrator import Administrator
    
    # Build base user data
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
    
    # Load type-specific data based on user type
    try:
        if current_user.user_type == "client":
            result = await session.execute(
                select(Client).where(Client.id == current_user.id)
            )
            client = result.scalar_one_or_none()
            if client:
                user_data.update({
                    "direccion": client.direccion,
                    "ci": client.ci,
                    "fecha_nacimiento": client.fecha_nacimiento.isoformat() if client.fecha_nacimiento else None,
                })
                
        elif current_user.user_type == "workshop":
            result = await session.execute(
                select(Workshop).where(Workshop.id == current_user.id)
            )
            workshop = result.scalar_one_or_none()
            if workshop:
                user_data.update({
                    "workshop_name": workshop.workshop_name,
                    "owner_name": workshop.owner_name,
                    "address": workshop.address,
                    "direccion": workshop.address,  # Alias para compatibilidad
                    "workshop_phone": workshop.workshop_phone,
                    "latitude": float(workshop.latitude) if workshop.latitude else None,
                    "longitude": float(workshop.longitude) if workshop.longitude else None,
                    "coverage_radius_km": float(workshop.coverage_radius_km) if workshop.coverage_radius_km else None,
                })
                
        elif current_user.user_type == "technician":
            result = await session.execute(
                select(Technician).where(Technician.id == current_user.id)
            )
            technician = result.scalar_one_or_none()
            if technician:
                # Obtener el nombre del taller si existe
                workshop_name = None
                if technician.workshop_id:
                    workshop_result = await session.execute(
                        select(Workshop).where(Workshop.id == technician.workshop_id)
                    )
                    workshop = workshop_result.scalar_one_or_none()
                    if workshop:
                        workshop_name = workshop.workshop_name
                
                user_data.update({
                    "workshop_id": technician.workshop_id,
                    "workshop_name": workshop_name,
                    "current_latitude": float(technician.current_latitude) if technician.current_latitude else None,
                    "current_longitude": float(technician.current_longitude) if technician.current_longitude else None,
                    "location_updated_at": technician.location_updated_at.isoformat() if technician.location_updated_at else None,
                    "location_accuracy": float(technician.location_accuracy) if technician.location_accuracy else None,
                    "is_available": technician.is_available,
                    "is_on_duty": technician.is_on_duty,
                    "is_online": technician.is_online,
                    "last_seen_at": technician.last_seen_at.isoformat() if technician.last_seen_at else None,
                })
                
        elif current_user.user_type == "admin":
            result = await session.execute(
                select(Administrator).where(Administrator.id == current_user.id)
            )
            admin = result.scalar_one_or_none()
            if admin:
                # Access role_level while still in session
                role_level = admin.role_level
                user_data.update({
                    "role_level": role_level,
                })
            
    except Exception as e:
        logger.error(f"Error loading user type-specific data: {str(e)}", user_id=current_user.id, user_type=current_user.user_type)
        # Continue with base user data
    
    return create_success_response(
        data=user_data,
        message="Perfil obtenido exitosamente",
    )


@router.patch(
    "/me",
    summary="Update current user profile",
    description="Update the current authenticated user's profile",
    dependencies=[Depends(require_permission(Permission.PROFILE_UPDATE_OWN))],
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
    dependencies=[Depends(require_permission(Permission.PROFILE_DELETE_OWN))],
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