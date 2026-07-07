"""
Router para subida de imágenes de productos de inventario (CU34).
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.dependencies import require_active_tenant, require_permission, TenantContext
from app.core.permissions import Permission
from app.core.responses import create_success_response
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/inventory/upload", tags=["Workshop - Inventory Upload"])

SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_service_role_key
STORAGE_BUCKET = "uploads"  # Bucket único para todos los uploads
STORAGE_PATH = "images/products"  # Ruta dentro del bucket

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def get_file_extension(filename: str) -> str:
    return "." + filename.split(".")[-1].lower() if "." in filename else ""


def is_allowed_file(filename: str) -> bool:
    return get_file_extension(filename) in ALLOWED_EXTENSIONS


def get_content_type(filename: str) -> str:
    ext = get_file_extension(filename)
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
    summary="Subir imagen de producto de inventario",
    description="Subir una imagen de producto a Supabase Storage",
    dependencies=[Depends(require_permission(Permission.INVENTORY_UPDATE))],
)
async def upload_product_image(
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(require_active_tenant),
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")

    if not file.filename or not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo no permitido. Usa: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archivo muy grande. Máximo: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )

    try:
        from supabase import create_client, Client

        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

        ext = get_file_extension(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        storage_filename = f"{STORAGE_PATH}/tenant_{ctx.tenant_id}/{timestamp}_{unique_id}{ext}"

        content_type = get_content_type(file.filename)

        supabase.storage.from_(STORAGE_BUCKET).upload(
            path=storage_filename,
            file=contents,
            file_options={"content-type": content_type}
        )

        public_url = supabase.storage.from_(STORAGE_BUCKET).get_public_url(storage_filename)

        logger.info(
            "Imagen de producto subida",
            tenant_id=ctx.tenant_id,
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
                "uploaded_by": ctx.user_id,
            },
            message="Imagen subida exitosamente",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al subir imagen de producto: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al subir imagen: {str(e)}"
        )
