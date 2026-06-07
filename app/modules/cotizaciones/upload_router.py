"""
Router para subida de evidencias multimedia de cotizaciones.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.dependencies import get_current_user_payload
from app.core.logging import get_logger
from app.core.responses import create_success_response
from app.models.cotizacion import Cotizacion

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter()

SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_service_role_key
STORAGE_BUCKET = "uploads"

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_AUDIO_SIZE = 20 * 1024 * 1024


def _get_ext(filename: str) -> str:
    return "." + filename.split(".")[-1].lower() if "." in filename else ""


def _is_image(filename: str) -> bool:
    return _get_ext(filename) in ALLOWED_IMAGE_EXTENSIONS


def _is_audio(filename: str) -> bool:
    return _get_ext(filename) in ALLOWED_AUDIO_EXTENSIONS


def _get_content_type(filename: str) -> str:
    ext = _get_ext(filename)
    mapping = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".webp": "image/webp", ".mp3": "audio/mpeg", ".wav": "audio/wav",
        ".m4a": "audio/mp4", ".ogg": "audio/ogg", ".webm": "audio/webm",
    }
    return mapping.get(ext, "application/octet-stream")


@router.post("/{cotizacion_id}/upload-image")
async def upload_cotizacion_image(
    cotizacion_id: int,
    file: UploadFile = File(...),
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    client_id = int(user_payload["sub"])

    cotizacion = await session.get(Cotizacion, cotizacion_id)
    if not cotizacion:
        raise HTTPException(404, "Cotizacion no encontrada")
    if cotizacion.client_id != client_id:
        raise HTTPException(403, "No tienes permiso para esta cotizacion")

    if not file.filename or not _is_image(file.filename):
        raise HTTPException(400, "Formato de imagen no permitido")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(400, "Imagen demasiado grande (max 10MB)")

    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    ext = _get_ext(file.filename)
    storage_path = f"cotizaciones/{cotizacion_id}/images/{uuid.uuid4().hex}{ext}"

    try:
        sb.storage.from_(STORAGE_BUCKET).upload(
            storage_path, contents,
            {"content-type": _get_content_type(file.filename)},
        )
    except Exception as e:
        logger.error(f"Supabase upload failed: {e}")
        raise HTTPException(500, "Error al subir la imagen")

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{storage_path}"

    current = cotizacion.imagenes_dano or []
    current.append(public_url)
    cotizacion.imagenes_dano = current

    await session.commit()

    return create_success_response(
        data={"url": public_url, "cotizacion_id": cotizacion_id},
        message="Imagen subida exitosamente",
    )


@router.post("/{cotizacion_id}/upload-audio")
async def upload_cotizacion_audio(
    cotizacion_id: int,
    file: UploadFile = File(...),
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    client_id = int(user_payload["sub"])

    cotizacion = await session.get(Cotizacion, cotizacion_id)
    if not cotizacion:
        raise HTTPException(404, "Cotizacion no encontrada")
    if cotizacion.client_id != client_id:
        raise HTTPException(403, "No tienes permiso para esta cotizacion")

    if not file.filename or not _is_audio(file.filename):
        raise HTTPException(400, "Formato de audio no permitido")

    contents = await file.read()
    if len(contents) > MAX_AUDIO_SIZE:
        raise HTTPException(400, "Audio demasiado grande (max 20MB)")

    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    ext = _get_ext(file.filename)
    storage_path = f"cotizaciones/{cotizacion_id}/audio/{uuid.uuid4().hex}{ext}"

    try:
        sb.storage.from_(STORAGE_BUCKET).upload(
            storage_path, contents,
            {"content-type": _get_content_type(file.filename)},
        )
    except Exception as e:
        logger.error(f"Supabase upload failed: {e}")
        raise HTTPException(500, "Error al subir el audio")

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET}/{storage_path}"

    cotizacion.audio_diagnostico = public_url

    await session.commit()

    return create_success_response(
        data={"url": public_url, "cotizacion_id": cotizacion_id},
        message="Audio subido exitosamente",
    )
