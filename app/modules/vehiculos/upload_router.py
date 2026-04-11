"""
Router para subida de imágenes de vehículos.
"""
from typing import Optional
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, UploadFile, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session, get_logger
from ...core.responses import create_success_response
from ...core.permissions import Permission
from ...core.dependencies import require_permission
from ...shared.dependencies.auth import get_current_user
from ...models.user import User
from ...core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/vehiculos/upload", tags=["Vehículos - Upload"])


# Configuración de Supabase Storage
SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_service_role_key
STORAGE_BUCKET = "uploads"  # Bucket único para todos los uploads
STORAGE_PATH = "images/vehicles"  # Ruta dentro del bucket

# Tipos de archivo permitidos
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def get_file_extension(filename: str) -> str:
    """Obtener extensión del archivo."""
    return "." + filename.split(".")[-1].lower() if "." in filename else ""


def is_allowed_file(filename: str) -> bool:
    """Verificar si el archivo es permitido."""
    ext = get_file_extension(filename)
    return ext in ALLOWED_EXTENSIONS


def get_content_type(filename: str) -> str:
    """Obtener el content-type correcto basado en la extensión."""
    ext = get_file_extension(filename).lower()
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    return content_types.get(ext, "image/jpeg")


@router.post(
    "/image",
    status_code=status.HTTP_200_OK,
    summary="Subir imagen de vehículo",
    description="Subir una imagen de vehículo a Supabase Storage",
    dependencies=[Depends(require_permission(Permission.PROFILE_VIEW_OWN))],
)
async def upload_vehicle_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Subir imagen de vehículo."""
    # Verificar que el usuario es un cliente
    if current_user.user_type != "client":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes pueden subir imágenes de vehículos")
    
    # Validar tipo de archivo
    if not file.filename or not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo no permitido. Usa: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Leer contenido del archivo
    contents = await file.read()
    
    # Validar tamaño
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archivo muy grande. Máximo: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    try:
        # Importar cliente de Supabase
        from supabase import create_client, Client
        
        # Crear cliente de Supabase
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Generar nombre único para el archivo
        ext = get_file_extension(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        storage_filename = f"{STORAGE_PATH}/client_{current_user.id}/{timestamp}_{unique_id}{ext}"
        
        # Determinar el content-type correcto basado en la extensión
        content_type = get_content_type(file.filename)
        
        # Subir archivo a Supabase Storage
        response = supabase.storage.from_(STORAGE_BUCKET).upload(
            path=storage_filename,
            file=contents,
            file_options={"content-type": content_type}
        )
        
        # Obtener URL pública
        public_url = supabase.storage.from_(STORAGE_BUCKET).get_public_url(storage_filename)
        
        logger.info(
            "Imagen de vehículo subida",
            user_id=current_user.id,
            filename=storage_filename,
            original_name=file.filename,
            size=len(contents)
        )
        
        return create_success_response(
            data={
                "file_name": file.filename,
                "file_url": public_url,
                "file_type": "image",
                "mime_type": content_type,
                "size": len(contents),
                "uploaded_by": current_user.id,
            },
            message="Imagen subida exitosamente",
        )
    
    except Exception as e:
        logger.error(f"Error al subir imagen: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al subir imagen: {str(e)}"
        )


def extract_storage_path_from_url(file_url: str) -> Optional[str]:
    """Extraer el path del storage desde la URL pública."""
    try:
        # URL format: https://{project}.supabase.co/storage/v1/object/public/uploads/{path}
        if "/storage/v1/object/public/uploads/" in file_url:
            return file_url.split("/storage/v1/object/public/uploads/")[1]
        return None
    except Exception:
        return None


@router.delete(
    "/image",
    status_code=status.HTTP_200_OK,
    summary="Eliminar imagen de vehículo",
    description="Eliminar una imagen de vehículo de Supabase Storage",
    dependencies=[Depends(require_permission(Permission.PROFILE_VIEW_OWN))],
)
async def delete_vehicle_image(
    file_url: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Eliminar imagen de vehículo del storage."""
    # Verificar que el usuario es un cliente
    if current_user.user_type != "client":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes pueden eliminar imágenes de vehículos")
    
    # Extraer el path del storage desde la URL
    storage_path = extract_storage_path_from_url(file_url)
    
    if not storage_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL de archivo inválida"
        )
    
    # Verificar que el archivo pertenece al usuario actual
    if f"client_{current_user.id}" not in storage_path:
        from ...core import ForbiddenException
        raise ForbiddenException("No tienes permiso para eliminar este archivo")
    
    try:
        # Importar cliente de Supabase
        from supabase import create_client, Client
        
        # Crear cliente de Supabase
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Eliminar archivo de Supabase Storage
        response = supabase.storage.from_(STORAGE_BUCKET).remove([storage_path])
        
        logger.info(
            "Imagen de vehículo eliminada",
            user_id=current_user.id,
            storage_path=storage_path,
        )
        
        return create_success_response(
            data={
                "file_url": file_url,
                "storage_path": storage_path,
                "deleted": True,
            },
            message="Imagen eliminada exitosamente",
        )
    
    except Exception as e:
        logger.error(f"Error al eliminar imagen: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar imagen: {str(e)}"
        )
