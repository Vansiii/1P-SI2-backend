"""
Validadores para archivos.
"""
from typing import List
from fastapi import UploadFile, HTTPException, status


ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

ALLOWED_AUDIO_TYPES = {
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    "audio/mp4",
    "audio/x-m4a",
}

ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10MB


def validate_file_type(file: UploadFile, allowed_types: set) -> None:
    """Validar tipo MIME del archivo."""
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo no permitido. Tipos aceptados: {', '.join(allowed_types)}"
        )


def validate_file_size(file: UploadFile, max_size: int) -> None:
    """Validar tamaño del archivo."""
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    
    if size > max_size:
        max_size_mb = max_size / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archivo muy grande. Tamaño máximo: {max_size_mb}MB"
        )


def validate_image(file: UploadFile) -> None:
    """Validar imagen."""
    validate_file_type(file, ALLOWED_IMAGE_TYPES)
    validate_file_size(file, MAX_IMAGE_SIZE)


def validate_audio(file: UploadFile) -> None:
    """Validar audio."""
    validate_file_type(file, ALLOWED_AUDIO_TYPES)
    validate_file_size(file, MAX_AUDIO_SIZE)


def validate_document(file: UploadFile) -> None:
    """Validar documento."""
    validate_file_type(file, ALLOWED_DOCUMENT_TYPES)
    validate_file_size(file, MAX_DOCUMENT_SIZE)
