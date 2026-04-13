"""
Router para gestión de vehículos.
"""
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session, get_logger
from ...core.responses import create_success_response
from ...core.permissions import Permission
from ...core.dependencies import require_permission
from ...shared.dependencies.auth import get_current_user
from ...models.user import User
from ...models.client import Client
from .schemas import VehiculoCreateRequest, VehiculoUpdateRequest, VehiculoResponse
from .service import VehiculoService

logger = get_logger(__name__)

router = APIRouter(prefix="/vehiculos", tags=["Vehículos"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=VehiculoResponse,
    summary="Crear vehículo",
    description="Registrar un nuevo vehículo para el cliente autenticado",
    dependencies=[Depends(require_permission(Permission.VEHICLE_CREATE))],
)
async def create_vehiculo(
    request: VehiculoCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Crear un nuevo vehículo."""
    # Verificar que el usuario es un cliente
    if current_user.user_type != "client":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes pueden registrar vehículos")
    
    service = VehiculoService(session)
    vehiculo = await service.create_vehiculo(current_user.id, request)
    
    return create_success_response(
        data=VehiculoResponse.model_validate(vehiculo).model_dump(mode='json'),
        message="Vehículo registrado exitosamente",
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "",
    response_model=List[VehiculoResponse],
    summary="Listar vehículos",
    description="Obtener todos los vehículos del cliente autenticado",
    dependencies=[Depends(require_permission(Permission.VEHICLE_VIEW_OWN))],
)
async def list_vehiculos(
    active_only: bool = Query(True, description="Mostrar solo vehículos activos"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Listar vehículos del cliente o todos si es admin."""
    service = VehiculoService(session)
    
    # Admin puede ver todos los vehículos
    if current_user.user_type == "admin":
        vehiculos = await service.get_all_vehiculos(active_only)
    elif current_user.user_type == "client":
        vehiculos = await service.get_client_vehiculos(current_user.id, active_only)
    else:
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes y administradores pueden ver vehículos")
    
    return create_success_response(
        data=[VehiculoResponse.model_validate(v).model_dump(mode='json') for v in vehiculos],
        message=f"Se encontraron {len(vehiculos)} vehículos",
    )


@router.get(
    "/{vehiculo_id}",
    response_model=VehiculoResponse,
    summary="Obtener vehículo",
    description="Obtener detalles de un vehículo específico",
    dependencies=[Depends(require_permission(Permission.VEHICLE_VIEW_OWN))],
)
async def get_vehiculo(
    vehiculo_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Obtener un vehículo por ID."""
    if current_user.user_type != "client":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes pueden ver vehículos")
    
    service = VehiculoService(session)
    vehiculo = await service.get_vehiculo(vehiculo_id, current_user.id)
    
    return create_success_response(
        data=VehiculoResponse.model_validate(vehiculo).model_dump(mode='json'),
        message="Vehículo obtenido exitosamente",
    )


@router.patch(
    "/{vehiculo_id}",
    response_model=VehiculoResponse,
    summary="Actualizar vehículo",
    description="Actualizar información de un vehículo",
    dependencies=[Depends(require_permission(Permission.VEHICLE_UPDATE))],
)
async def update_vehiculo(
    vehiculo_id: int,
    request: VehiculoUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Actualizar un vehículo."""
    if current_user.user_type != "client":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes pueden actualizar vehículos")
    
    service = VehiculoService(session)
    vehiculo = await service.update_vehiculo(vehiculo_id, current_user.id, request)
    
    return create_success_response(
        data=VehiculoResponse.model_validate(vehiculo).model_dump(mode='json'),
        message="Vehículo actualizado exitosamente",
    )


@router.delete(
    "/{vehiculo_id}",
    status_code=status.HTTP_200_OK,
    summary="Eliminar vehículo",
    description="Eliminar un vehículo (soft delete)",
    dependencies=[Depends(require_permission(Permission.VEHICLE_DELETE))],
)
async def delete_vehiculo(
    vehiculo_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Eliminar un vehículo."""
    if current_user.user_type != "client":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes pueden eliminar vehículos")
    
    service = VehiculoService(session)
    await service.delete_vehiculo(vehiculo_id, current_user.id)
    
    return create_success_response(
        data={"vehiculo_id": vehiculo_id, "deleted": True},
        message="Vehículo eliminado exitosamente",
    )


@router.get(
    "/{vehiculo_id}/historial",
    summary="Obtener historial del vehículo",
    description="Obtener todos los incidentes y servicios asociados a un vehículo",
    dependencies=[Depends(require_permission(Permission.VEHICLE_VIEW_OWN))],
)
async def get_vehiculo_historial(
    vehiculo_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Obtener historial de incidentes del vehículo."""
    if current_user.user_type != "client":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes pueden ver el historial de vehículos")
    
    service = VehiculoService(session)
    historial = await service.get_vehiculo_historial(vehiculo_id, current_user.id)
    
    return create_success_response(
        data=historial,
        message="Historial obtenido exitosamente",
    )
