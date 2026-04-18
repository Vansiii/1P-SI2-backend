"""Gemini multimodal classifier for incident processing (UC10)."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import re
import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, ValidationError

from ...core import ExternalServiceException, ValidationException, get_logger, get_settings

logger = get_logger(__name__)

SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/mpeg",
    "audio/wav",
    "audio/mp4",
    "audio/ogg",
    "audio/webm",
}

CATEGORY_VALUES = (
    "bateria",
    "llanta",
    "motor",
    "choque_leve",
    "electrico",
    "combustible",
    "perdida_llaves",
    "llave_atrapada",
    "otros",
    "incierto",
)


class GeminiIncidentClassification(BaseModel):
    """Normalized AI output for incident classification."""

    category: Literal[
        "bateria",
        "llanta",
        "motor",
        "choque_leve",
        "electrico",
        "combustible",
        "perdida_llaves",
        "llave_atrapada",
        "otros",
        "incierto",
    ]
    priority: Literal["alta", "media", "baja"]
    summary: str = Field(..., min_length=25, max_length=1200)
    is_ambiguous: bool
    confidence: float = Field(..., ge=0, le=1)
    findings: list[str] = Field(default_factory=list, max_length=8)
    missing_data: list[str] = Field(default_factory=list, max_length=6)
    workshop_recommendation: str = Field(default="", max_length=900)


@dataclass(slots=True)
class GeminiClassificationOutput:
    """Classifier return object with telemetry details."""

    classification: GeminiIncidentClassification
    used_model_name: str
    raw_response_json: str
    latency_ms: int


def parse_gemini_response_json(raw_text: str) -> dict[str, object]:
    """Parse Gemini text output as a strict JSON object."""
    cleaned_text = raw_text.strip()

    if cleaned_text.startswith("```"):
        cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text)
        cleaned_text = re.sub(r"\s*```$", "", cleaned_text)

    json_start = cleaned_text.find("{")
    json_end = cleaned_text.rfind("}")
    if json_start != -1 and json_end != -1 and json_end >= json_start:
        cleaned_text = cleaned_text[json_start : json_end + 1]

    try:
        parsed = json.loads(cleaned_text)
    except json.JSONDecodeError as exc:
        raise ValidationException(
            "Gemini returned an invalid JSON response",
            details={"raw_response_excerpt": raw_text[:500]},
        ) from exc

    if not isinstance(parsed, dict):
        raise ValidationException("Gemini output must be a JSON object")

    return parsed


class GeminiIncidentClassifier:
    """Gemini API client for multimodal incident classification."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._max_attempts_per_model = 2
        self._retry_base_delay_seconds = 0.75

    @property
    def model_name(self) -> str:
        """Configured Gemini model name."""
        return self.settings.gemini_model

    @property
    def prompt_version(self) -> str:
        """Configured prompt version."""
        return self.settings.gemini_prompt_version

    @property
    def is_enabled(self) -> bool:
        """Whether Gemini integration is enabled."""
        return self.settings.is_gemini_enabled

    async def classify_incident(
        self,
        description: str,
        image_urls: list[str],
        audio_urls: list[str],
    ) -> GeminiClassificationOutput:
        """Classify an incident using text and optional multimedia evidence."""
        if not self.is_enabled:
            raise ValidationException("Gemini integration is disabled in environment settings")

        prompt = self._build_prompt(description)
        parts: list[dict[str, object]] = [{"text": prompt}]

        image_parts = await self._build_media_parts(
            media_urls=image_urls,
            media_type="image",
            max_items=3,
        )
        audio_parts = await self._build_media_parts(
            media_urls=audio_urls,
            media_type="audio",
            max_items=2,
        )
        parts.extend(image_parts)
        parts.extend(audio_parts)

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        start_time = time.perf_counter()
        response_data, used_model_name = await self._call_gemini(payload)
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        raw_text = self._extract_text_response(response_data)
        parsed_json = parse_gemini_response_json(raw_text)

        try:
            classification = GeminiIncidentClassification.model_validate(parsed_json)
        except ValidationError as exc:
            raise ValidationException(
                "Gemini JSON does not match the expected schema",
                details={"validation_errors": exc.errors()},
            ) from exc

        return GeminiClassificationOutput(
            classification=classification,
            used_model_name=used_model_name,
            raw_response_json=json.dumps(parsed_json, ensure_ascii=False),
            latency_ms=latency_ms,
        )

    async def _call_gemini(self, payload: dict[str, object]) -> tuple[dict[str, object], str]:
        """Call Gemini API with fallback models and return response + selected model."""
        timeout_seconds = float(self.settings.gemini_timeout_seconds)
        model_candidates = self._build_model_candidates()

        for index, model_name in enumerate(model_candidates):
            endpoint = self._build_endpoint(model_name)
            has_next_candidate = index < len(model_candidates) - 1

            for attempt in range(1, self._max_attempts_per_model + 1):
                try:
                    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                        response = await client.post(
                            endpoint,
                            headers={"x-goog-api-key": self.settings.gemini_api_key},
                            json=payload,
                        )
                        response.raise_for_status()
                        return response.json(), model_name
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    body_excerpt = exc.response.text[:500]
                    should_retry = (
                        status_code in {429, 500, 502, 503, 504}
                        and attempt < self._max_attempts_per_model
                    )
                    should_try_next_model = status_code in {429, 500, 502, 503, 504}

                    logger.warning(
                        "Gemini model request failed",
                        model_name=model_name,
                        attempt=attempt,
                        max_attempts=self._max_attempts_per_model,
                        status_code=status_code,
                        has_next_candidate=has_next_candidate,
                        response_excerpt=body_excerpt[:200],
                    )

                    if should_retry:
                        await asyncio.sleep(self._retry_base_delay_seconds * attempt)
                        continue

                    if has_next_candidate and should_try_next_model:
                        break

                    raise ExternalServiceException(
                        service_name="Gemini",
                        message=(
                            f"Gemini API HTTP {status_code} for model '{model_name}'"
                        ),
                        original_error=RuntimeError(body_excerpt),
                    ) from exc
                except httpx.RequestError as exc:
                    error_message = str(exc) or repr(exc)
                    should_retry = attempt < self._max_attempts_per_model

                    logger.warning(
                        "Gemini network request failed",
                        model_name=model_name,
                        attempt=attempt,
                        max_attempts=self._max_attempts_per_model,
                        has_next_candidate=has_next_candidate,
                        error_type=type(exc).__name__,
                        error=error_message,
                    )

                    if should_retry:
                        await asyncio.sleep(self._retry_base_delay_seconds * attempt)
                        continue

                    if has_next_candidate:
                        break

                    raise ExternalServiceException(
                        service_name="Gemini",
                        message=f"Gemini request error for model '{model_name}'",
                        original_error=exc,
                    ) from exc

        raise ExternalServiceException(
            service_name="Gemini",
            message="All configured Gemini model requests failed",
        )

    def _build_model_candidates(self) -> list[str]:
        """Build ordered model candidates (primary + fallbacks) without duplicates."""
        candidates = [self.settings.gemini_model.strip()]
        fallback_models = [
            model.strip()
            for model in self.settings.gemini_fallback_models.split(",")
            if model.strip()
        ]

        for model_name in fallback_models:
            if model_name not in candidates:
                candidates.append(model_name)

        return candidates

    @staticmethod
    def _build_endpoint(model_name: str) -> str:
        """Build Gemini generateContent endpoint for one model."""
        return (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent"
        )

    async def _build_media_parts(
        self,
        media_urls: list[str],
        media_type: Literal["image", "audio"],
        max_items: int,
    ) -> list[dict[str, object]]:
        """Download and encode evidence files as Gemini inline parts."""
        parts: list[dict[str, object]] = []

        for media_url in media_urls[:max_items]:
            part = await self._download_media_part(media_url, media_type)
            if part is not None:
                parts.append(part)

        return parts

    async def _download_media_part(
        self,
        media_url: str,
        media_type: Literal["image", "audio"],
    ) -> dict[str, object] | None:
        """Download a media URL and convert it to Gemini inlineData format."""
        max_media_bytes = self.settings.gemini_max_media_bytes

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(media_url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "Skipping unreadable evidence URL",
                media_type=media_type,
                media_url=media_url,
                error=str(exc),
            )
            return None

        content_length = self._parse_content_length(response.headers.get("content-length"))
        if content_length and content_length > max_media_bytes:
            logger.warning(
                "Skipping oversized evidence based on content-length",
                media_type=media_type,
                media_url=media_url,
                content_length=content_length,
                max_media_bytes=max_media_bytes,
            )
            return None

        content_bytes = response.content
        if len(content_bytes) > max_media_bytes:
            logger.warning(
                "Skipping oversized evidence after download",
                media_type=media_type,
                media_url=media_url,
                downloaded_bytes=len(content_bytes),
                max_media_bytes=max_media_bytes,
            )
            return None

        mime_type = self._resolve_mime_type(
            media_url=media_url,
            header_content_type=response.headers.get("content-type", ""),
            default_type="image/jpeg" if media_type == "image" else "audio/mpeg",
        )

        if media_type == "image" and mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            logger.warning(
                "Skipping unsupported image MIME type",
                media_url=media_url,
                mime_type=mime_type,
            )
            return None

        if media_type == "audio" and mime_type not in SUPPORTED_AUDIO_MIME_TYPES:
            logger.warning(
                "Skipping unsupported audio MIME type",
                media_url=media_url,
                mime_type=mime_type,
            )
            return None

        encoded_content = base64.b64encode(content_bytes).decode("ascii")
        return {
            "inlineData": {
                "mimeType": mime_type,
                "data": encoded_content,
            }
        }

    @staticmethod
    def _extract_text_response(response_data: dict[str, object]) -> str:
        """Extract text payload from Gemini API response."""
        candidates = response_data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValidationException("Gemini returned no candidates")

        first_candidate = candidates[0]
        if not isinstance(first_candidate, dict):
            raise ValidationException("Gemini candidate payload is invalid")

        content = first_candidate.get("content")
        if not isinstance(content, dict):
            raise ValidationException("Gemini content payload is invalid")

        parts = content.get("parts")
        if not isinstance(parts, list):
            raise ValidationException("Gemini parts payload is invalid")

        for part in parts:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"]

        raise ValidationException("Gemini text response was not found")

    @staticmethod
    def _parse_content_length(raw_content_length: str | None) -> int | None:
        """Parse content-length header safely."""
        if not raw_content_length:
            return None

        try:
            parsed_content_length = int(raw_content_length)
        except ValueError:
            return None

        if parsed_content_length < 0:
            return None

        return parsed_content_length

    @staticmethod
    def _resolve_mime_type(media_url: str, header_content_type: str, default_type: str) -> str:
        """Resolve MIME type from headers and URL path."""
        normalized_header_type = header_content_type.split(";")[0].strip().lower()
        if normalized_header_type:
            return normalized_header_type

        parsed_url = urlparse(media_url)
        guessed_type, _ = mimetypes.guess_type(parsed_url.path)
        if guessed_type:
            return guessed_type

        return default_type

    def _build_prompt(self, description: str) -> str:
        """Build strict classification prompt for Gemini."""
        categories = ", ".join(CATEGORY_VALUES)

        return (
            "You are an assistant that classifies vehicle emergency incidents for workshop dispatch. "
            "Analyze user description and optional multimedia evidence. "
            "Write the analysis in Spanish with practical workshop context.\n\n"
            "Return ONLY a valid JSON object with this exact schema and keys:\n"
            "{\n"
            '  "category": "one of the allowed categories",\n'
            '  "priority": "alta | media | baja",\n'
            '  "summary": "detailed technical context for dispatch and diagnostics",\n'
            '  "is_ambiguous": true or false,\n'
            '  "confidence": number between 0 and 1,\n'
            '  "findings": ["objective finding 1", "objective finding 2"],\n'
            '  "missing_data": ["missing item 1", "missing item 2"],\n'
            '  "workshop_recommendation": "immediate action plan for workshop"\n'
            "}\n\n"
            "Rules:\n"
            f"- Allowed categories: {categories}.\n"
            "- Do not invent facts not present in evidence.\n"
            "- If evidence is insufficient, set category='incierto' and is_ambiguous=true.\n"
            "- If confidence < 0.65, set is_ambiguous=true.\n"
            "- Summary must be action-oriented, in Spanish, and provide useful context for technicians.\n"
            "- Summary should cover symptoms, probable cause hypothesis, operational risk, and urgency rationale.\n"
            "- Findings should include 3 to 6 concise evidence-based points when possible.\n"
            "- Missing_data should identify what additional evidence would increase certainty.\n"
            "- Workshop_recommendation should include immediate action, first diagnostics, and safety caution if relevant.\n\n"
            "Incident description:\n"
            f"{description.strip()}"
        )
