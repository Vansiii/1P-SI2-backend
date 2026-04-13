"""
Servicio para gestión de archivos en Supabase Storage.
"""
import uuid
from typing import Optional
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...core.storage import supabase_client
from ...core import get_logger
from ...models.file import File
from .schemas import FileUploadResponse, FileMetadata, SignedUrlResponse

logger = get_logger(__name__)

BUCKET_NAME = "uploads"


class StorageService:
    """Servicio para gestión de archivos."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.storage = supabase_client.storage.from_(BUCKET_NAME)
    
    def _get_file_extension(self, mime_type: str) -> str:
        """Obtener extensión de archivo según MIME type."""
        extensions = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "audio/mpeg": "mp3",
            "audio/wav": "wav",
            "audio/ogg": "ogg",
            "audio/mp4": "m4a",
            "audio/x-m4a": "m4a",
            "application/pdf": "pdf",
            "application/msword": "doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        }
        return extensions.get(mime_type, "bin")
    
    def _build_path(
        self,
        entity_type: str,
        entity_id: str,
        subfolder: Optional[str] = None
    ) -> str:
        """Construir ruta del archivo."""
        file_uuid = str(uuid.uuid4())
        
        if entity_type == "user":
            if subfolder == "profile":
                return f"users/{entity_id}/profile/{file_uuid}"
            elif subfolder == "documents":
                return f"users/{entity_id}/documents/{file_uuid}"
            else:
                return f"users/{entity_id}/{file_uuid}"
        
        elif entity_type == "incident":
            if subfolder == "images":
                return f"incidents/{entity_id}/images/{file_uuid}"
            elif subfolder == "audios":
                return f"incidents/{entity_id}/audios/{file_uuid}"
            else:
                return f"incidents/{entity_id}/{file_uuid}"
        
        elif entity_type == "vehicle":
            return f"vehicles/{entity_id}/images/{file_uuid}"
        
        else:
            return f"temp/{file_uuid}"
    
    async def upload_file(
        self,
        file: UploadFile,
        entity_type: str,
        entity_id: str,
        user_id: int,
        subfolder: Optional[str] = None
    ) -> FileUploadResponse:
        """Subir archivo a Supabase Storage."""
        try:
            # Leer contenido del archivo
            content = await file.read()
            
            # Construir ruta
            base_path = self._build_path(entity_type, entity_id, subfolder)
            extension = self._get_file_extension(file.content_type)
            file_path = f"{base_path}.{extension}"
            
            # Subir a Supabase
            response = self.storage.upload(
                path=file_path,
                file=content,
                file_options={
                    "content-type": file.content_type,
                    "upsert": "false"
                }
            )
            
            if hasattr(response, 'error') and response.error:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error al subir archivo: {response.error}"
                )
            
            # Obtener URL pública (firmada)
            signed_url_response = self.storage.create_signed_url(
                path=file_path,
                expires_in=31536000  # 1 año
            )
            
            file_url = signed_url_response.get("signedURL", "")
            
            # Guardar metadata en BD
            file_record = File(
                file_name=f"{uuid.uuid4()}.{extension}",
                file_path=file_path,
                file_url=file_url,
                mime_type=file.content_type,
                size=len(content),
                entity_type=entity_type,
                entity_id=str(entity_id),
                uploaded_by=user_id
            )
            
            self.session.add(file_record)
            await self.session.commit()
            await self.session.refresh(file_record)
            
            logger.info(f"Archivo subido: {file_path} por usuario {user_id}")
            
            return FileUploadResponse.model_validate(file_record)
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al subir archivo: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al subir archivo"
            )
    
    async def get_signed_url(
        self,
        file_path: str,
        expires_in: int = 3600
    ) -> SignedUrlResponse:
        """Obtener URL firmada para acceso temporal."""
        try:
            response = self.storage.create_signed_url(
                path=file_path,
                expires_in=expires_in
            )
            
            signed_url = response.get("signedURL", "")
            
            if not signed_url:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Archivo no encontrado"
                )
            
            return SignedUrlResponse(
                signed_url=signed_url,
                expires_in=expires_in
            )
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al generar URL firmada: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al generar URL de acceso"
            )
    
    async def delete_file(self, file_path: str) -> bool:
        """Eliminar archivo del storage."""
        try:
            response = self.storage.remove([file_path])
            
            if hasattr(response, 'error') and response.error:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error al eliminar archivo: {response.error}"
                )
            
            # Eliminar registro de BD
            result = await self.session.execute(
                select(File).where(File.file_path == file_path)
            )
            file_record = result.scalar_one_or_none()
            
            if file_record:
                await self.session.delete(file_record)
                await self.session.commit()
            
            logger.info(f"Archivo eliminado: {file_path}")
            return True
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error al eliminar archivo: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al eliminar archivo"
            )
    
    async def get_file_metadata(self, file_id: int) -> Optional[File]:
        """Obtener metadata de archivo por ID."""
        result = await self.session.execute(
            select(File).where(File.id == file_id)
        )
        return result.scalar_one_or_none()
    
    async def get_entity_files(
        self,
        entity_type: str,
        entity_id: str
    ) -> list[File]:
        """Obtener todos los archivos de una entidad."""
        result = await self.session.execute(
            select(File)
            .where(File.entity_type == entity_type)
            .where(File.entity_id == str(entity_id))
            .order_by(File.created_at.desc())
        )
        return list(result.scalars().all())
