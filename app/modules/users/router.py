"""
User management endpoints.
"""
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session, get_logger
from ...core.responses import create_success_response, create_paginated_response
from .schemas import (
    UserResponse,
    ClientResponse,
    WorkshopResponse,
    TechnicianResponse,
    AdministratorResponse,
    UpdateClientRequest,
    UpdateWorkshopRequest,
    UpdateTechnicianRequest,
    LocationRequest,
)
from .service import (
    UserService,
    ClientService,
    WorkshopService,
    TechnicianService,
    AdministratorService,
)
from ...core.permissions import Permission, UserRole
from ...core.dependencies import require_permission, require_role, AdminUser
from ...shared.dependencies.auth import get_current_user
from ...shared.schemas.pagination import PaginationParams
from ...models.user import User

logger = get_logger(__name__)

router = APIRouter()


# General user endpoints
@router.get(
    "",
    response_model=List[UserResponse],
    summary="List users",
    description="Get list of users with optional filtering by type",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANAGE_USERS))],
)
async def list_users(
    user_type: str = Query(None, description="Filter by user type"),
    active_only: bool = Query(True, description="Show only active users"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Number of records to return"),
    session: AsyncSession = Depends(get_db_session),
    admin: AdminUser = None,  # Verificación de admin ya hecha por dependency
):
    """List users with optional filtering and pagination."""
    user_service = UserService(session)
    
    if user_type:
        all_users = await user_service.get_users_by_type(user_type, active_only)
    else:
        # This would need to be implemented in the service
        all_users = []
    
    # Apply pagination
    total = len(all_users)
    paginated_users = all_users[skip:skip + limit]
    
    # Convert SQLAlchemy models to dicts for JSON serialization
    users_data = []
    for user in paginated_users:
        try:
            user_dict = {
                "id": user.id,
                "email": user.email,
                "user_type": user.user_type,
                "is_active": user.is_active,
                "two_factor_enabled": user.two_factor_enabled,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            }
            
            # Add type-specific fields - attributes are already loaded since we queried the specific model
            if user_type == "workshop":
                lat = user.latitude
                lon = user.longitude
                radius = user.coverage_radius_km
                user_dict.update({
                    "workshop_name": user.workshop_name,
                    "owner_name": user.owner_name,
                    "latitude": float(lat) if lat is not None else None,
                    "longitude": float(lon) if lon is not None else None,
                    "coverage_radius_km": float(radius) if radius is not None else None,
                })
            elif user_type == "client":
                fecha = user.fecha_nacimiento
                user_dict.update({
                    "direccion": user.direccion,
                    "ci": user.ci,
                    "fecha_nacimiento": fecha.isoformat() if fecha else None,
                })
            elif user_type == "technician":
                clat = user.current_latitude
                clon = user.current_longitude
                user_dict.update({
                    "workshop_id": user.workshop_id,
                    "current_latitude": float(clat) if clat is not None else None,
                    "current_longitude": float(clon) if clon is not None else None,
                    "is_available": user.is_available,
                })
            elif user_type == "administrator":
                user_dict.update({
                    "role_level": user.role_level,
                })
            
            users_data.append(user_dict)
        except Exception as e:
            logger.error(f"Error serializing user {user.id}: {str(e)}", exc_info=True)
            continue
    
    # Calculate pagination metadata
    total_pages = (total + limit - 1) // limit if limit > 0 else 1
    current_page = (skip // limit) + 1 if limit > 0 else 1
    
    # Return in consistent paginated format
    return create_success_response(
        data={
            "users": users_data,
            "total": total,
            "page": current_page,
            "page_size": limit,
            "total_pages": total_pages,
        },
        status_code=200,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
    description="Get user details by ID",
)
async def get_user(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Get user by ID."""
    user_service = UserService(session)
    user = await user_service.get_user_by_id(user_id)
    
    return create_success_response(
        data=user,
        message="Usuario obtenido exitosamente",
    )


@router.patch(
    "/{user_id}/activate",
    summary="Activate user",
    description="Activate a user account",
)
async def activate_user(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Activate a user account."""
    user_service = UserService(session)
    await user_service.activate_user(user_id)
    
    return create_success_response(
        data={"user_id": user_id, "is_active": True},
        message="Usuario activado exitosamente",
    )


@router.patch(
    "/{user_id}/deactivate",
    summary="Deactivate user",
    description="Deactivate a user account",
)
async def deactivate_user(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Deactivate a user account."""
    user_service = UserService(session)
    await user_service.deactivate_user(user_id)
    
    return create_success_response(
        data={"user_id": user_id, "is_active": False},
        message="Usuario desactivado exitosamente",
    )


# Client-specific endpoints
@router.get(
    "/clients/{client_id}",
    response_model=ClientResponse,
    summary="Get client by ID",
    description="Get client details by ID",
)
async def get_client(
    client_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Get client by ID."""
    client_service = ClientService(session)
    client = await client_service.get_client_by_id(client_id)
    
    return create_success_response(
        data=client,
        message="Cliente obtenido exitosamente",
    )


@router.patch(
    "/clients/{client_id}",
    response_model=ClientResponse,
    summary="Update client",
    description="Update client information",
)
async def update_client(
    client_id: int,
    request: UpdateClientRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Update client information."""
    client_service = ClientService(session)
    
    if request.direccion is not None:
        client = await client_service.update_client_address(client_id, request.direccion)
    else:
        client = await client_service.get_client_by_id(client_id)
    
    return create_success_response(
        data=client,
        message="Cliente actualizado exitosamente",
    )


# Workshop-specific endpoints
@router.get(
    "/workshops/{workshop_id}",
    response_model=WorkshopResponse,
    summary="Get workshop by ID",
    description="Get workshop details by ID",
)
async def get_workshop(
    workshop_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Get workshop by ID."""
    workshop_service = WorkshopService(session)
    workshop = await workshop_service.get_workshop_by_id(workshop_id)
    
    return create_success_response(
        data=workshop,
        message="Taller obtenido exitosamente",
    )


@router.post(
    "/workshops/nearby",
    response_model=List[WorkshopResponse],
    summary="Find nearby workshops",
    description="Find workshops near a location",
)
async def find_nearby_workshops(
    location: LocationRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Find workshops near a location."""
    workshop_service = WorkshopService(session)
    workshops = await workshop_service.find_nearby_workshops(
        location.latitude,
        location.longitude,
        location.radius_km,
    )
    
    return create_success_response(
        data=workshops,
        message=f"Encontrados {len(workshops)} talleres cercanos",
    )


@router.patch(
    "/workshops/{workshop_id}",
    response_model=WorkshopResponse,
    summary="Update workshop",
    description="Update workshop information",
)
async def update_workshop(
    workshop_id: int,
    request: UpdateWorkshopRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Update workshop information."""
    workshop_service = WorkshopService(session)
    
    if request.latitude is not None and request.longitude is not None:
        workshop = await workshop_service.update_workshop_location(
            workshop_id, request.latitude, request.longitude
        )
    else:
        workshop = await workshop_service.get_workshop_by_id(workshop_id)
    
    return create_success_response(
        data=workshop,
        message="Taller actualizado exitosamente",
    )


# Technician-specific endpoints
@router.get(
    "/technicians/{technician_id}",
    response_model=TechnicianResponse,
    summary="Get technician by ID",
    description="Get technician details by ID",
)
async def get_technician(
    technician_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Get technician by ID."""
    technician_service = TechnicianService(session)
    technician = await technician_service.get_technician_by_id(technician_id)
    
    return create_success_response(
        data=technician,
        message="Técnico obtenido exitosamente",
    )


@router.get(
    "/workshops/{workshop_id}/technicians",
    response_model=List[TechnicianResponse],
    summary="Get workshop technicians",
    description="Get all technicians for a workshop",
)
async def get_workshop_technicians(
    workshop_id: int,
    available_only: bool = Query(False, description="Show only available technicians"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Get technicians for a workshop."""
    technician_service = TechnicianService(session)
    
    if available_only:
        technicians = await technician_service.get_available_technicians(workshop_id)
    else:
        technicians = await technician_service.get_workshop_technicians(workshop_id)
    
    return create_success_response(
        data=technicians,
        message=f"Encontrados {len(technicians)} técnicos",
    )


@router.patch(
    "/technicians/{technician_id}",
    response_model=TechnicianResponse,
    summary="Update technician",
    description="Update technician information",
)
async def update_technician(
    technician_id: int,
    request: UpdateTechnicianRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    """Update technician information."""
    technician_service = TechnicianService(session)
    
    if request.is_available is not None:
        technician = await technician_service.update_technician_availability(
            technician_id, request.is_available
        )
    elif request.current_latitude is not None and request.current_longitude is not None:
        technician = await technician_service.update_technician_location(
            technician_id, request.current_latitude, request.current_longitude
        )
    else:
        technician = await technician_service.get_technician_by_id(technician_id)
    
    return create_success_response(
        data=technician,
        message="Técnico actualizado exitosamente",
    )
