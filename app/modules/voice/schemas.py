"""
Schemas for voice endpoints.
"""
from typing import Optional
from pydantic import BaseModel, Field


class VoiceReportRequest(BaseModel):
    audio_base64: str = Field(..., min_length=1)
    mime_type: str = "audio/webm"


class VoiceCommandRequest(BaseModel):
    texto: str = Field(..., min_length=1, max_length=2000)


class VoiceCommandResult(BaseModel):
    action: str
    type: Optional[str] = None
    filters: dict = {}
    confidence: float
    response_text: str


class VoiceProcessResult(BaseModel):
    texto_transcrito: str
    comando: VoiceCommandResult
