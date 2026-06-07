"""
Voice service — transcripción de audio y NLU de comandos de voz usando Gemini.
"""
from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from ...core import ExternalServiceException, get_logger, get_settings

logger = get_logger(__name__)

VOICE_SYSTEM_PROMPT = """Eres un intérprete de comandos de voz para MecánicoYa, una plataforma de emergencias vehiculares.

Tu tarea es interpretar el texto transcrito del usuario y devolver ÚNICAMENTE un JSON válido con la intención estructurada.

Responde SIEMPRE con este formato exacto (sin markdown, sin explicaciones):
{
  "action": "report" | "create_incident" | "query_status" | "search" | "export" | "unknown",
  "type": "spending" | "my_incidents" | "vehicle_history" | "kpi" | "financial" | "efficiency" | "hotspots" | "cancelled" | "sla" | "technicians" | "ratings" | "system" | "audit" | "subscriptions" | null,
  "filters": {
    "period": "today" | "this_week" | "this_month" | "last_month" | null,
    "status": "active" | "resolved" | "cancelled" | "all" | null,
    "start_date": "YYYY-MM-DD" | null,
    "end_date": "YYYY-MM-DD" | null,
    "vehicle_plate": null
  },
  "confidence": 0.0 a 1.0,
  "response_text": "respuesta amigable en español confirmando lo que se entendió"
}

Reglas:
- Si el usuario quiere reportar una emergencia nueva, action="create_incident" y type=null.
- Si el usuario pregunta por sus gastos, action="report" y type="spending".
- Si el usuario pregunta por el estado de su emergencia, action="query_status".
- Si el usuario quiere buscar talleres, action="search".
- Si no entiendes, action="unknown" y responde pidiendo que reformule.
- Interpreta referencias temporales: "este mes" → period="this_month", "esta semana" → period="this_week", "hoy" → period="today".
- Extrae matrículas de vehículos si se mencionan (formato ABC-123 o similar).
"""


@dataclass(slots=True)
class VoiceCommand:
    action: str
    type: Optional[str]
    filters: dict
    confidence: float
    response_text: str
    original_text: str


def _parse_gemini_json(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end >= start:
        cleaned = cleaned[start:end + 1]
    return json.loads(cleaned)


class VoiceService:
    """Servicio de procesamiento de voz con Gemini."""

    def __init__(self):
        self.settings = get_settings()

    @property
    def is_enabled(self) -> bool:
        return self.settings.is_gemini_enabled

    @property
    def _api_url(self) -> str:
        return (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_model}:generateContent"
        )

    def _headers(self) -> dict:
        return {"x-goog-api-key": self.settings.gemini_api_key, "Content-Type": "application/json"}

    async def transcribe_audio(self, audio_base64: str, mime_type: str = "audio/webm") -> str:
        """Transcribe audio a texto usando Gemini multimodal."""
        if not self.is_enabled:
            raise ExternalServiceException("Gemini no está configurado")

        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"inlineData": {"mimeType": mime_type, "data": audio_base64}},
                    {"text": "Transcribe exactamente el audio en español. Solo devuelve el texto transcrito, sin introducción ni comentarios."},
                ],
            }],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500},
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self._api_url}?key={self.settings.gemini_api_key}", json=payload)
            if resp.status_code != 200:
                logger.error("Gemini transcription failed", status=resp.status_code, body=resp.text[:300])
                raise ExternalServiceException("Error al transcribir el audio")
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return text

    async def interpret_command(self, text: str, role: str) -> VoiceCommand:
        """Interpreta texto en lenguaje natural como comando estructurado."""
        if not self.is_enabled:
            raise ExternalServiceException("Gemini no está configurado")

        prompt = (
            f"{VOICE_SYSTEM_PROMPT}\n\n"
            f"El rol del usuario es: {role}\n"
            f"El usuario dijo: \"{text}\"\n\n"
            f"Responde solo con el JSON."
        )

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 300},
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{self._api_url}?key={self.settings.gemini_api_key}", json=payload)
            if resp.status_code != 200:
                logger.error("Gemini NLU failed", status=resp.status_code, body=resp.text[:300])
                raise ExternalServiceException("Error al interpretar el comando")
            data = resp.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            parsed = _parse_gemini_json(raw)
            return VoiceCommand(
                action=parsed.get("action", "unknown"),
                type=parsed.get("type"),
                filters=parsed.get("filters", {}),
                confidence=parsed.get("confidence", 0.0),
                response_text=parsed.get("response_text", "Comando interpretado."),
                original_text=text,
            )

    async def process_audio(self, audio_base64: str, mime_type: str, role: str) -> dict:
        """Pipeline completo: audio → transcripción → interpretación."""
        texto = await self.transcribe_audio(audio_base64, mime_type)
        comando = await self.interpret_command(texto, role)
        return {
            "texto_transcrito": texto,
            "comando": {
                "action": comando.action,
                "type": comando.type,
                "filters": comando.filters,
                "confidence": comando.confidence,
                "response_text": comando.response_text,
            },
        }

    async def process_text(self, text: str, role: str) -> dict:
        """Pipeline: texto → interpretación."""
        comando = await self.interpret_command(text, role)
        return {
            "texto_transcrito": text,
            "comando": {
                "action": comando.action,
                "type": comando.type,
                "filters": comando.filters,
                "confidence": comando.confidence,
                "response_text": comando.response_text,
            },
        }
