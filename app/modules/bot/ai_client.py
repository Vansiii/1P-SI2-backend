"""Cliente HTTP robusto para los proveedores de IA del MecánicoBot (Groq + Gemini fallback)."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

from ...core import ExternalServiceException, get_logger, get_settings

logger = get_logger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_GENERATE_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(slots=True)
class ChatResult:
    """Resultado de una llamada de chat no-streaming (usada para decidir tool-calling)."""

    content: str | None
    tool_calls: list[dict[str, Any]] | None
    model_used: str
    tokens_used: int | None
    latency_ms: int


class BotAIClient:
    """
    Cliente para Groq (motor principal, con soporte de tool-calling y streaming)
    y Gemini (fallback de texto plano cuando Groq no está disponible).

    Replica el patrón de retry/fallback multi-modelo de
    app/modules/incidentes/ai_classifier.py (GeminiIncidentClassifier).
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._max_attempts = 2
        self._retry_base_delay_seconds = 0.75
        self._timeout_seconds = 20.0

    @property
    def groq_enabled(self) -> bool:
        return bool(self.settings.groq_api_key)

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.settings.gemini_api_key)

    # ---------- Groq: chat con tool-calling (no streaming) ----------

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        """Llama a Groq (chat completions, formato OpenAI-compatible) con soporte de function-calling."""
        if not self.groq_enabled:
            raise ExternalServiceException(service_name="Groq", message="Groq API key no configurada")

        payload: dict[str, Any] = {
            "model": self.settings.groq_model,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 1024,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.settings.groq_api_key}",
            "Content-Type": "application/json",
        }

        start = time.perf_counter()
        data = await self._post_with_retry(GROQ_CHAT_URL, payload, headers, service_name="Groq")
        latency_ms = int((time.perf_counter() - start) * 1000)

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}

        return ChatResult(
            content=message.get("content"),
            tool_calls=message.get("tool_calls"),
            model_used=data.get("model") or self.settings.groq_model,
            tokens_used=usage.get("total_tokens"),
            latency_ms=latency_ms,
        )

    # ---------- Groq: streaming ----------

    async def stream_groq_chat(self, messages: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        """
        Streamea la respuesta de Groq token por token (formato SSE estilo OpenAI).
        Yields dicts: {"type": "token", "content": str} y finalmente {"type": "final", "content": str, "model_used": str}.
        """
        if not self.groq_enabled:
            raise ExternalServiceException(service_name="Groq", message="Groq API key no configurada")

        payload = {
            "model": self.settings.groq_model,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 1024,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.groq_api_key}",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
        full_content_parts: list[str] = []

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", GROQ_CHAT_URL, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise ExternalServiceException(
                        service_name="Groq",
                        message=f"Groq stream HTTP {response.status_code}: {body[:300]!r}",
                    )

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[len("data:"):].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk.get("choices") or [{}]
                    delta = choices[0].get("delta") or {}
                    token = delta.get("content")
                    if token:
                        full_content_parts.append(token)
                        yield {"type": "token", "content": token}

        yield {
            "type": "final",
            "content": "".join(full_content_parts),
            "model_used": self.settings.groq_model,
        }

    # ---------- Gemini: fallback de texto plano (sin tool-calling) ----------

    async def call_gemini_text(self, system_prompt: str, history: list[dict[str, str]]) -> str:
        """Llama a Gemini como fallback de texto plano, con retry y fallback multi-modelo."""
        if not self.gemini_enabled:
            raise ExternalServiceException(service_name="Gemini", message="Gemini API key no configurada")

        dialog_lines = [f"System: {system_prompt}"]
        for msg in history:
            role_label = "Usuario" if msg["role"] == "user" else "Bot"
            dialog_lines.append(f"{role_label}: {msg['content']}")
        dialog_lines.append("Bot:")
        prompt = "\n\n".join(dialog_lines)

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
        }

        model_candidates = self._build_gemini_model_candidates()

        for index, model_name in enumerate(model_candidates):
            url = GEMINI_GENERATE_URL_TEMPLATE.format(model=model_name)
            has_next_candidate = index < len(model_candidates) - 1

            for attempt in range(1, self._max_attempts + 1):
                try:
                    async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                        response = await client.post(
                            url,
                            headers={"x-goog-api-key": self.settings.gemini_api_key},
                            json=payload,
                        )
                        response.raise_for_status()
                        data = response.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    should_retry = status_code in _RETRYABLE_STATUS_CODES and attempt < self._max_attempts
                    logger.warning(
                        "Gemini bot fallback request failed",
                        model_name=model_name,
                        attempt=attempt,
                        status_code=status_code,
                        has_next_candidate=has_next_candidate,
                    )
                    if should_retry:
                        await asyncio.sleep(self._retry_base_delay_seconds * attempt)
                        continue
                    if has_next_candidate and status_code in _RETRYABLE_STATUS_CODES:
                        break
                    raise ExternalServiceException(
                        service_name="Gemini",
                        message=f"Gemini API HTTP {status_code} for model '{model_name}'",
                        original_error=exc,
                    ) from exc
                except httpx.RequestError as exc:
                    should_retry = attempt < self._max_attempts
                    logger.warning(
                        "Gemini bot fallback network error",
                        model_name=model_name,
                        attempt=attempt,
                        has_next_candidate=has_next_candidate,
                        error=str(exc),
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

        raise ExternalServiceException(service_name="Gemini", message="All configured Gemini model requests failed")

    def _build_gemini_model_candidates(self) -> list[str]:
        """Modelo primario + fallbacks configurados, sin duplicados."""
        candidates = [self.settings.gemini_model.strip()]
        fallback_models = [
            model.strip() for model in self.settings.gemini_fallback_models.split(",") if model.strip()
        ]
        for model in fallback_models:
            if model not in candidates:
                candidates.append(model)
        return candidates

    # ---------- Helper interno: POST con retry ----------

    async def _post_with_retry(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], service_name: str
    ) -> dict[str, Any]:
        for attempt in range(1, self._max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                should_retry = status_code in _RETRYABLE_STATUS_CODES and attempt < self._max_attempts
                logger.warning(
                    f"{service_name} request failed",
                    status_code=status_code,
                    attempt=attempt,
                    max_attempts=self._max_attempts,
                )
                if should_retry:
                    await asyncio.sleep(self._retry_base_delay_seconds * attempt)
                    continue
                raise ExternalServiceException(
                    service_name=service_name,
                    message=f"{service_name} API HTTP {status_code}: {exc.response.text[:300]}",
                    original_error=exc,
                ) from exc
            except httpx.RequestError as exc:
                should_retry = attempt < self._max_attempts
                logger.warning(
                    f"{service_name} network request failed",
                    attempt=attempt,
                    max_attempts=self._max_attempts,
                    error=str(exc),
                )
                if should_retry:
                    await asyncio.sleep(self._retry_base_delay_seconds * attempt)
                    continue
                raise ExternalServiceException(
                    service_name=service_name,
                    message=f"{service_name} request error",
                    original_error=exc,
                ) from exc

        raise ExternalServiceException(service_name=service_name, message=f"{service_name} request failed after retries")
