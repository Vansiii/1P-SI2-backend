"""
Router para gestión de archivos.
"""
from fastapi import APIRouter, Depends, UploadFile, File as FastAPIFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session
from ...core.responses import create_success_response
from ...core.permissions import Permission
from ...core.dependencies import require_permission
from ...shared.dependencies.auth import get_current_user
from ...models.user import User
from .schemas import FileUploadResponse, SignedUrlResponse
from .service import StorageService
from .validators import validate_image, validate_audio, validate_document

router = APIRouter(prefix="/files", tags=["Files"])


@router.post(
    "/users/profile",
    status_code=status.HTTP_201_CREATED,
    response_model=FileUploadResponse,
    summary="Subir imagen de perfil",
    dependencies=[Depends(require_permission(Permission.PROFILE_UPDATE_OWN))],
)
async def upload_profile_image(
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """Subir imagen de perfil de usuario."""
    validate_image(file)
    
    service = StorageService(session)
    result = await service.upload_file(
        file=file,
        entity_type="user",
        entity_id=str(current_user.id),
        user_id=current_user.id,
        subfolder="profile"
    )
    
    return create_success_response(
        data=result,
        message="Imagen de perfil subida exitosamente",
        status_code=status.HTTP_201_CREATED
    )


@router.post(
    "/users/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=FileUploadResponse,
    summary="Subir documento de usuario",
    dependencies=[Depends(require_permission(Permission.PROFILE_UPDATE_OWN))],
)
async def upload_user_document(
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """Subir documento de usuario."""
    validate_document(file)
    
    service = StorageService(session)
    result = await service.upload_file(
        file=file,
        entity_type="user",
        entity_id=str(current_user.id),
        user_id=current_user.id,
        subfolder="documents"
    )
    
    return create_success_response(
        data=result,
        message="Documento subido exitosamente",
        status_code=status.HTTP_201_CREATED
    )


@router.post(
    "/incidents/{incident_id}/images",
    status_code=status.HTTP_201_CREATED,
    response_model=FileUploadResponse,
    summary="Subir imagen de incidente",
    dependencies=[Depends(require_permission(Permission.EMERGENCY_CREATE))],
)
async def upload_incident_image(
    incident_id: int,
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """Subir imagen de incidente."""
    validate_image(file)
    
    service = StorageService(session)
    result = await service.upload_file(
        file=file,
        entity_type="incident",
        entity_id=str(incident_id),
        user_id=current_user.id,
        subfolder="images"
    )
    
    return create_success_response(
        data=result,
        message="Imagen de incidente subida exitosamente",
        status_code=status.HTTP_201_CREATED
    )


@router.post(
    "/incidents/{incident_id}/audios",
    status_code=status.HTTP_201_CREATED,
    response_model=FileUploadResponse,
    summary="Subir audio de incidente",
    dependencies=[Depends(require_permission(Permission.EMERGENCY_CREATE))],
)
async def upload_incident_audio(
    incident_id: int,
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """Subir audio de incidente."""
    validate_audio(file)
    
    service = StorageService(session)
    result = await service.upload_file(
        file=file,
        entity_type="incident",
        entity_id=str(incident_id),
        user_id=current_user.id,
        subfolder="audios"
    )
    
    return create_success_response(
        data=result,
        message="Audio de incidente subido exitosamente",
        status_code=status.HTTP_201_CREATED
    )


@router.post(
    "/vehicles/{vehicle_id}/images",
    status_code=status.HTTP_201_CREATED,
    response_model=FileUploadResponse,
    summary="Subir imagen de vehículo",
    dependencies=[Depends(require_permission(Permission.VEHICLE_UPDATE))],
)
async def upload_vehicle_image(
    vehicle_id: int,
    file: UploadFile = FastAPIFile(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """Subir imagen de vehículo."""
    validate_image(file)
    
    service = StorageService(session)
    result = await service.upload_file(
        file=file,
        entity_type="vehicle",
        entity_id=str(vehicle_id),
        user_id=current_user.id,
        subfolder="images"
    )
    
    return create_success_response(
        data=result,
        message="Imagen de vehículo subida exitosamente",
        status_code=status.HTTP_201_CREATED
    )


@router.get(
    "/{file_id}/signed-url",
    response_model=SignedUrlResponse,
    summary="Obtener URL firmada",
    dependencies=[Depends(require_permission(Permission.PROFILE_VIEW_OWN))],
)
async def get_file_signed_url(
    file_id: int,
    expires_in: int = 3600,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """Obtener URL firmada para acceso temporal a archivo."""
    service = StorageService(session)
    
    file_metadata = await service.get_file_metadata(file_id)
    if not file_metadata:
        from ...core.exceptions import NotFoundException
        raise NotFoundException("Archivo no encontrado")
    
    result = await service.get_signed_url(
        file_path=file_metadata.file_path,
        expires_in=expires_in
    )
    
    return create_success_response(
        data=result,
        message="URL firmada generada exitosamente"
    )


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_200_OK,
    summary="Eliminar archivo",
    dependencies=[Depends(require_permission(Permission.PROFILE_DELETE_OWN))],
)
async def delete_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """Eliminar archivo del storage."""
    service = StorageService(session)
    
    file_metadata = await service.get_file_metadata(file_id)
    if not file_metadata:
        from ...core.exceptions import NotFoundException
        raise NotFoundException("Archivo no encontrado")
    
    # Verificar que el usuario sea el propietario
    if file_metadata.uploaded_by != current_user.id:
        from ...core.exceptions import ForbiddenException
        raise ForbiddenException("No tienes permiso para eliminar este archivo")
    
    await service.delete_file(file_metadata.file_path)
    
    return create_success_response(
        data={"file_id": file_id, "deleted": True},
        message="Archivo eliminado exitosamente"
    )
