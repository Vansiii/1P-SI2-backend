"""Orquesta la decisión de tool-calling y la generación de la respuesta final del MecánicoBot."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from ...core import ExternalServiceException, get_logger
from .ai_client import BotAIClient
from .tools import (
    TOOL_REGISTRY,
    TOOLS_SCHEMA,
    build_fallback_arguments,
    detect_intent_keywords,
    parse_tool_call_arguments,
)

logger = get_logger(__name__)

_MAX_TOOL_CALLS_PER_TURN = 2


@dataclass(slots=True)
class ToolResolution:
    """Resultado de la fase de tool-calling: mensajes aumentados listos para la generación final."""

    augmented_messages: list[dict[str, Any]]
    executed_tool_calls: list[dict[str, Any]]
    products: list[dict[str, Any]]
    groq_available: bool


@dataclass(slots=True)
class OrchestratorResult:
    """Resultado completo (no-streaming) de un turno del bot."""

    content: str
    model_used: str
    tokens_used: int | None
    response_time_ms: int
    tool_calls: list[dict[str, Any]] | None = None
    products: list[dict[str, Any]] = field(default_factory=list)


class BotToolOrchestrator:
    """
    Coordina: (1) intento de tool-calling nativo de Groq, (2) fallback determinístico
    por palabras clave si el modelo no invoca ninguna tool, (3) generación de la
    respuesta final (streaming o no) usando los resultados reales de las tools.
    """

    def __init__(self, session: AsyncSession, ai_client: BotAIClient) -> None:
        self.session = session
        self.ai_client = ai_client

    async def run(
        self,
        user_id: int,
        system_prompt: str,
        history: list[dict[str, str]],
        context: dict[str, Any] | None = None,
    ) -> OrchestratorResult:
        """Turno completo no-streaming (usado por los endpoints existentes de creación/mensaje)."""
        start = time.perf_counter()
        base_messages = [{"role": "system", "content": system_prompt}] + history

        resolution = await self.resolve_tools(user_id, base_messages, history, context)

        final_content: str | None = None
        model_used: str | None = None
        tokens_used: int | None = None

        if resolution.groq_available:
            try:
                final_chat = await self.ai_client.chat_with_tools(resolution.augmented_messages, tools=None)
                final_content = final_chat.content
                model_used = final_chat.model_used
                tokens_used = final_chat.tokens_used
            except ExternalServiceException as exc:
                logger.warning("Groq final synthesis call failed, falling back to Gemini", error=str(exc))

        if final_content is None:
            final_content, model_used = await self._gemini_fallback_text(
                system_prompt, history, self._build_tool_context_note(resolution)
            )

        response_time_ms = int((time.perf_counter() - start) * 1000)
        return OrchestratorResult(
            content=final_content,
            model_used=model_used or "unknown",
            tokens_used=tokens_used,
            response_time_ms=response_time_ms,
            tool_calls=resolution.executed_tool_calls or None,
            products=resolution.products,
        )

    async def stream(
        self,
        user_id: int,
        system_prompt: str,
        history: list[dict[str, str]],
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Turno completo en streaming (usado por el endpoint SSE).
        Yields eventos: {"type": "tool_result", "products": [...]} (opcional),
        luego {"type": "token", "content": str} repetido, y finalmente
        {"type": "final", "content": str, "model_used": str, "tokens_used": int|None,
         "tool_calls": [...] | None, "products": [...]}.
        """
        start = time.perf_counter()
        base_messages = [{"role": "system", "content": system_prompt}] + history

        resolution = await self.resolve_tools(user_id, base_messages, history, context)

        if resolution.executed_tool_calls:
            yield {"type": "tool_result", "products": resolution.products}

        full_content = ""
        model_used = self.ai_client.settings.groq_model
        tokens_used: int | None = None

        if resolution.groq_available:
            try:
                async for chunk in self.ai_client.stream_groq_chat(resolution.augmented_messages):
                    if chunk["type"] == "token":
                        full_content += chunk["content"]
                        yield chunk
                    elif chunk["type"] == "final":
                        full_content = chunk["content"] or full_content
                        model_used = chunk.get("model_used", model_used)
            except ExternalServiceException as exc:
                logger.warning("Groq streaming failed, falling back to Gemini (non-streaming)", error=str(exc))
                full_content = ""

        if not full_content:
            gemini_text, gemini_model = await self._gemini_fallback_text(
                system_prompt, history, self._build_tool_context_note(resolution)
            )
            full_content = gemini_text
            model_used = gemini_model
            yield {"type": "token", "content": full_content}

        response_time_ms = int((time.perf_counter() - start) * 1000)
        yield {
            "type": "final",
            "content": full_content,
            "model_used": model_used,
            "tokens_used": tokens_used,
            "tool_calls": resolution.executed_tool_calls or None,
            "products": resolution.products,
            "response_time_ms": response_time_ms,
        }

    # ---------- Fase de tool-calling (compartida entre run() y stream()) ----------

    async def resolve_tools(
        self,
        user_id: int,
        base_messages: list[dict[str, Any]],
        history: list[dict[str, str]],
        context: dict[str, Any] | None = None,
    ) -> ToolResolution:
        executed_tool_calls: list[dict[str, Any]] = []
        products: list[dict[str, Any]] = []
        augmented_messages = list(base_messages)
        groq_available = True

        try:
            decision = await self.ai_client.chat_with_tools(base_messages, tools=TOOLS_SCHEMA)
        except ExternalServiceException as exc:
            logger.warning("Groq tool-decision call failed", error=str(exc))
            decision = None
            # Un HTTP 4xx (ej. "tool_use_failed" porque el modelo generó argumentos
            # mal formados) es un fallo puntual de esa llamada, no una caída real de
            # Groq — dejamos groq_available=True para que la síntesis final en texto
            # plano (sin tools) siga intentándose contra Groq en vez de saltar a Gemini.
            status_match = re.search(r"HTTP (\d+)", str(exc))
            status_code = int(status_match.group(1)) if status_match else None
            if status_code is None or status_code >= 500:
                groq_available = False

        if decision is not None and decision.tool_calls:
            tool_messages: list[dict[str, Any]] = []
            for tool_call in decision.tool_calls[:_MAX_TOOL_CALLS_PER_TURN]:
                fn = tool_call.get("function") or {}
                name = fn.get("name")
                arguments = parse_tool_call_arguments(fn.get("arguments"))
                tool_result = await self._execute_tool_safely(name, user_id, arguments, context)
                if tool_result is None:
                    continue

                executed_tool_calls.append(
                    {
                        "name": name,
                        "arguments": arguments,
                        "result_summary": tool_result.get("results_for_model"),
                        "location_missing": tool_result.get("location_missing", False),
                    }
                )
                products.extend(tool_result.get("products", []))
                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "name": name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

            if tool_messages:
                augmented_messages = base_messages + [
                    {
                        "role": "assistant",
                        "content": decision.content or "",
                        "tool_calls": decision.tool_calls,
                    }
                ] + tool_messages

        # Fallback determinístico: el modelo no llamó ninguna tool pero el mensaje
        # del usuario sugiere claramente intención de compra/búsqueda de repuestos.
        if not executed_tool_calls:
            last_user_message = self._last_user_message(history)
            intent_tool = detect_intent_keywords(last_user_message)
            if intent_tool:
                fallback_args = build_fallback_arguments(intent_tool, last_user_message)
                tool_result = await self._execute_tool_safely(intent_tool, user_id, fallback_args, context)
                if tool_result is not None:
                    executed_tool_calls.append(
                        {
                            "name": intent_tool,
                            "arguments": fallback_args,
                            "result_summary": tool_result.get("results_for_model"),
                            "location_missing": tool_result.get("location_missing", False),
                        }
                    )
                    products.extend(tool_result.get("products", []))
                    context_note = {
                        "role": "system",
                        "content": self._build_single_result_note(tool_result),
                    }
                    augmented_messages = base_messages + [context_note]

        return ToolResolution(
            augmented_messages=augmented_messages,
            executed_tool_calls=executed_tool_calls,
            products=products,
            groq_available=groq_available,
        )

    async def _execute_tool_safely(
        self, name: str | None, user_id: int, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        if not name:
            return None
        executor = TOOL_REGISTRY.get(name)
        if not executor:
            return None
        try:
            return await executor(self.session, user_id, arguments, context)
        except Exception as exc:  # defensivo: una tool fallando nunca debe tumbar el chat
            logger.warning("Bot tool execution failed", tool=name, error=str(exc))
            return {"tool": name, "error": "No se pudo completar la búsqueda.", "results_for_model": [], "products": []}

    async def _gemini_fallback_text(
        self, system_prompt: str, history: list[dict[str, str]], tool_context_note: str | None = None
    ) -> tuple[str, str]:
        try:
            effective_prompt = system_prompt if not tool_context_note else f"{system_prompt}\n\n{tool_context_note}"
            text = await self.ai_client.call_gemini_text(effective_prompt, history)
            return text, self.ai_client.settings.gemini_model
        except ExternalServiceException as exc:
            logger.error("Gemini fallback also failed", error=str(exc))
            return (
                "Lo siento, en este momento tengo dificultades técnicas para procesar tu consulta. "
                "Por favor, reintenta en unos instantes.",
                "fallback-static",
            )

    @staticmethod
    def _build_tool_context_note(resolution: ToolResolution) -> str | None:
        """Nota con los resultados reales de las tools ejecutadas, para que ningún
        proveedor (ni Groq ni Gemini) invente productos/precios/talleres que no existen."""
        if not resolution.executed_tool_calls:
            return None
        if any(call.get("location_missing") for call in resolution.executed_tool_calls):
            return (
                "El usuario pidió talleres cercanos pero la app no pudo obtener su ubicación "
                "(GPS desactivado o permiso denegado). No inventes talleres ni distancias: pídele "
                "que active la ubicación en la app e intente de nuevo."
            )
        summaries = [call.get("result_summary") for call in resolution.executed_tool_calls if call.get("result_summary")]
        if not summaries:
            return (
                "Se buscó en el marketplace/talleres pero no se encontraron resultados reales que coincidan. "
                "No inventes nombres de productos, talleres ni precios: informa al usuario que no hay "
                "resultados disponibles por ahora y sugiere reformular la búsqueda."
            )
        return (
            "Resultados reales disponibles para referenciar en tu respuesta "
            f"(no inventes otros productos, talleres ni precios; si son repuestos, cita siempre el "
            f"nombre del taller que aparece en 'workshop_name'): {json.dumps(summaries, ensure_ascii=False)}"
        )

    @staticmethod
    def _build_single_result_note(tool_result: dict[str, Any]) -> str:
        """Nota de contexto para el camino de fallback por keywords (una sola tool ejecutada)."""
        if tool_result.get("location_missing"):
            return (
                "El usuario pidió talleres cercanos pero la app no pudo obtener su ubicación "
                "(GPS desactivado o permiso denegado). No inventes talleres ni distancias: pídele "
                "que active la ubicación en la app e intente de nuevo."
            )
        results = tool_result.get("results_for_model")
        if not results:
            return (
                "Se buscó en el marketplace/talleres pero no se encontraron resultados reales que coincidan. "
                "No inventes nombres de productos, talleres ni precios: informa al usuario que no hay "
                "resultados disponibles por ahora y sugiere reformular la búsqueda."
            )
        return (
            "Resultados reales disponibles para referenciar en tu respuesta "
            f"(no inventes otros productos, talleres ni precios; si son repuestos, cita siempre el "
            f"nombre del taller que aparece en 'workshop_name'): {json.dumps(results, ensure_ascii=False)}"
        )

    @staticmethod
    def _last_user_message(history: list[dict[str, str]]) -> str:
        for msg in reversed(history):
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""
