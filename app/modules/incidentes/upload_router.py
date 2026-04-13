"""
Router para subida de evidencias multimedia de incidentes.
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

router = APIRouter(prefix="/incidentes/upload", tags=["Incidentes - Upload"])


# Configuración de Supabase Storage
SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_service_role_key
STORAGE_BUCKET = "uploads"  # Bucket único para todos los uploads

# Tipos de archivo permitidos
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB para imágenes
MAX_AUDIO_SIZE = 20 * 1024 * 1024  # 20MB para audio


def extract_storage_path_from_url(file_url: str) -> Optional[str]:
    """Extraer el path del storage desde la URL pública."""
    try:
        # URL format: https://{project}.supabase.co/storage/v1/object/public/uploads/{path}
        if "/storage/v1/object/public/uploads/" in file_url:
            return file_url.split("/storage/v1/object/public/uploads/")[1]
        return None
    except Exception:
        return None


def get_file_extension(filename: str) -> str:
    """Obtener extensión del archivo."""
    return "." + filename.split(".")[-1].lower() if "." in filename else ""


def is_allowed_image(filename: str) -> bool:
    """Verificar si el archivo de imagen es permitido."""
    ext = get_file_extension(filename)
    return ext in ALLOWED_IMAGE_EXTENSIONS


def is_allowed_audio(filename: str) -> bool:
    """Verificar si el archivo de audio es permitido."""
    ext = get_file_extension(filename)
    return ext in ALLOWED_AUDIO_EXTENSIONS


@router.post(
    "/image",
    status_code=status.HTTP_200_OK,
    summary="Subir imagen de incidente",
    description="Subir una imagen como evidencia de un incidente",
    dependencies=[Depends(require_permission(Permission.PROFILE_VIEW_OWN))],
)
async def upload_incident_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Subir imagen de incidente."""
    # Verificar que el usuario es un cliente
    if current_user.user_type != "client":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes pueden subir imágenes de incidentes")
    
    # Validar tipo de archivo
    if not file.filename or not is_allowed_image(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo no permitido. Usa: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
        )
    
    # Leer contenido del archivo
    contents = await file.read()
    
    # Validar tamaño
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archivo muy grande. Máximo: {MAX_IMAGE_SIZE / 1024 / 1024}MB"
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
        storage_filename = f"images/incidents/client_{current_user.id}/{timestamp}_{unique_id}{ext}"
        
        # Determinar content-type basado en la extensión
        content_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        ext = get_file_extension(file.filename)
        content_type = content_type_map.get(ext, "image/jpeg")
        
        # Subir archivo a Supabase Storage
        response = supabase.storage.from_(STORAGE_BUCKET).upload(
            path=storage_filename,
            file=contents,
            file_options={"content-type": content_type}
        )
        
        # Obtener URL pública
        public_url = supabase.storage.from_(STORAGE_BUCKET).get_public_url(storage_filename)
        
        logger.info(
            "Imagen de incidente subida",
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


@router.post(
    "/audio",
    status_code=status.HTTP_200_OK,
    summary="Subir audio de incidente",
    description="Subir un audio como evidencia de un incidente",
    dependencies=[Depends(require_permission(Permission.PROFILE_VIEW_OWN))],
)
async def upload_incident_audio(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Subir audio de incidente."""
    # Verificar que el usuario es un cliente
    if current_user.user_type != "client":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes pueden subir audios de incidentes")
    
    # Validar tipo de archivo
    if not file.filename or not is_allowed_audio(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo no permitido. Usa: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}"
        )
    
    # Leer contenido del archivo
    contents = await file.read()
    
    # Validar tamaño
    if len(contents) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archivo muy grande. Máximo: {MAX_AUDIO_SIZE / 1024 / 1024}MB"
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
        storage_filename = f"audios/incidents/client_{current_user.id}/{timestamp}_{unique_id}{ext}"
        
        # Determinar content-type basado en la extensión
        content_type_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".webm": "audio/webm",
        }
        ext = get_file_extension(file.filename)
        content_type = content_type_map.get(ext, "audio/mpeg")
        
        # Subir archivo a Supabase Storage
        response = supabase.storage.from_(STORAGE_BUCKET).upload(
            path=storage_filename,
            file=contents,
            file_options={"content-type": content_type}
        )
        
        # Obtener URL pública
        public_url = supabase.storage.from_(STORAGE_BUCKET).get_public_url(storage_filename)
        
        logger.info(
            "Audio de incidente subido",
            user_id=current_user.id,
            filename=storage_filename,
            original_name=file.filename,
            size=len(contents)
        )
        
        return create_success_response(
            data={
                "file_name": file.filename,
                "file_url": public_url,
                "file_type": "audio",
                "mime_type": content_type,
                "size": len(contents),
                "uploaded_by": current_user.id,
            },
            message="Audio subido exitosamente",
        )
    
    except Exception as e:
        logger.error(f"Error al subir audio: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al subir audio: {str(e)}"
        )


@router.delete(
    "/file",
    status_code=status.HTTP_200_OK,
    summary="Eliminar archivo de incidente",
    description="Eliminar un archivo (imagen o audio) de Supabase Storage",
    dependencies=[Depends(require_permission(Permission.PROFILE_VIEW_OWN))],
)
async def delete_incident_file(
    file_url: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Eliminar archivo de incidente del storage."""
    # Verificar que el usuario es un cliente
    if current_user.user_type != "client":
        from ...core import ForbiddenException
        raise ForbiddenException("Solo los clientes pueden eliminar archivos de incidentes")
    
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
            "Archivo de incidente eliminado",
            user_id=current_user.id,
            storage_path=storage_path,
        )
        
        return create_success_response(
            data={
                "file_url": file_url,
                "storage_path": storage_path,
                "deleted": True,
            },
            message="Archivo eliminado exitosamente",
        )
    
    except Exception as e:
        logger.error(f"Error al eliminar archivo: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar archivo: {str(e)}"
        )
