from datetime import datetime
from typing import Any, AsyncIterator

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_logger, get_settings
from ...models.bot_conversation import BotConversation
from ...models.bot_message import BotMessage
from ...models.vehiculo import Vehiculo
from ...models.audit_log import AuditLog
from .ai_client import BotAIClient
from .orchestrator import BotToolOrchestrator
import json

logger = get_logger(__name__)

SYSTEM_PROMPT = """Eres el Bot de Asistencia Mecánica Inteligente de MecánicoYa.
Tu función es ayudar a los conductores que enfrentan fallas mecánicas, ruidos extraños, luces de advertencia en el tablero, o emergencias en la carretera.

Pautas de comportamiento:
1. Brinda sugerencias de diagnóstico preliminares y lógicas basadas en los síntomas (ej: batería muerta, alternador fallido, sobrecalentamiento del motor, etc.).
2. Explica los pasos de seguridad inmediatos que deben tomar (ej: estacionar a la derecha, encender luces de emergencia, colocarse chaleco reflectante).
3. Mantén siempre un tono profesional, servicial, tranquilizador y empático.
4. Si el problema parece grave o requiere herramientas especializadas, recuérdales que usen el botón de "Reportar Emergencia" en la app para solicitar asistencia en carretera o que soliciten una cotización a los talleres locales.
5. Si el usuario pregunta por repuestos, precios, o dónde comprar una pieza, usa la herramienta de búsqueda de marketplace disponible y responde únicamente con los productos reales que te devuelva — nunca inventes precios ni productos. Menciona siempre el nombre del taller (campo "workshop_name") al que pertenece cada repuesto que recomiendes, para que el cliente sepa dónde conseguirlo.
6. Si el usuario pregunta por talleres cercanos, dónde llevar su auto, o recomendaciones de talleres en su zona, usa la herramienta de búsqueda de talleres cercanos. El resultado de la herramienta trae "location_missing": true o false — revísalo con cuidado: si es false, SÍ tienes la ubicación real del usuario, así que presenta los talleres de la lista directamente como resultados reales y actuales (nombre, distancia, calificación), sin pedirle la ubicación ni decir "por ejemplo". Solo pide que active la ubicación si "location_missing" es true. Nunca inventes talleres ni distancias.
7. Responde siempre en español. No utilices formatos excesivos, mantén los párrafos concisos y legibles en pantallas móviles.
"""

# Sugerencias curadas para el endpoint /suggestions (v1: estáticas en código).
_GENERIC_SUGGESTIONS = [
    {"id": "noise-brake", "text": "Escucho un chirrido al frenar, ¿qué puede ser?"},
    {"id": "battery-dead", "text": "Mi auto no enciende, ¿cómo sé si es la batería?"},
    {"id": "engine-light", "text": "Se encendió la luz de check engine, ¿es grave?"},
    {"id": "overheating", "text": "El motor se está sobrecalentando, ¿qué hago?"},
    {"id": "find-parts", "text": "Necesito pastillas de freno, ¿dónde las consigo?"},
]

_VEHICLE_SUGGESTIONS = [
    {"id": "noise-brake", "text": "Escucho un chirrido al frenar en mi {label}, ¿qué puede ser?"},
    {"id": "battery-dead", "text": "Mi {label} no enciende, ¿cómo sé si es la batería?"},
    {"id": "find-parts", "text": "Necesito repuestos compatibles con mi {label}"},
]


class BotService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
        self.ai_client = BotAIClient()
        self.orchestrator = BotToolOrchestrator(session, self.ai_client)

    async def list_conversations(self, user_id: int) -> list[BotConversation]:
        """Obtiene la lista de conversaciones de chat del bot de un usuario, ordenadas por actualización."""
        # BotConversationResponse incluye "messages": Pydantic lo lee vía from_attributes
        # al serializar, y sin eager-load dispara un lazy-load fuera del contexto async
        # (MissingGreenlet). Mismo eager-load que ya usa get_conversation().
        stmt = (
            select(BotConversation)
            .options(selectinload(BotConversation.messages))
            .where(BotConversation.user_id == user_id)
            .order_by(BotConversation.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_conversation(self, user_id: int, conversation_id: int) -> BotConversation | None:
        """Obtiene una conversación específica y sus mensajes (eager load)."""
        stmt = (
            select(BotConversation)
            .options(selectinload(BotConversation.messages), selectinload(BotConversation.vehicle))
            .where(
                BotConversation.id == conversation_id,
                BotConversation.user_id == user_id
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_conversation(self, user_id: int, conversation_id: int) -> bool:
        """Elimina una conversación y todos sus mensajes en cascada."""
        stmt = select(BotConversation).where(
            BotConversation.id == conversation_id,
            BotConversation.user_id == user_id
        )
        result = await self.session.execute(stmt)
        conversation = result.scalar_one_or_none()
        if not conversation:
            return False

        await self.session.delete(conversation)

        audit = AuditLog(
            user_id=user_id,
            action="bot_conversation:delete",
            ip_address="127.0.0.1",
            details=json.dumps({"conversation_id": conversation_id}),
            created_at=datetime.utcnow()
        )
        self.session.add(audit)

        return True

    async def _resolve_owned_vehicle(self, user_id: int, vehicle_id: int | None) -> Vehiculo | None:
        """Resuelve un vehículo por id validando que pertenezca al usuario actual (client_id == user_id)."""
        if not vehicle_id:
            return None
        stmt = select(Vehiculo).where(Vehiculo.id == vehicle_id, Vehiculo.client_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _build_system_prompt(vehicle: Vehiculo | None) -> str:
        if not vehicle:
            return SYSTEM_PROMPT
        vehicle_line = (
            f"\n\nContexto del vehículo del usuario: {vehicle.marca or ''} {vehicle.modelo} "
            f"({vehicle.anio}), placa {vehicle.matricula}. Ten este vehículo en cuenta al "
            "diagnosticar y al buscar repuestos compatibles."
        )
        return SYSTEM_PROMPT + vehicle_line

    @staticmethod
    def _build_location_context(latitude: float | None, longitude: float | None) -> dict[str, Any] | None:
        if latitude is None or longitude is None:
            return None
        return {"latitude": latitude, "longitude": longitude}

    async def create_conversation(
        self,
        user_id: int,
        first_message: str,
        vehicle_id: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> BotConversation:
        """Inicia una conversación del bot y genera la primera respuesta de la IA."""
        vehicle = await self._resolve_owned_vehicle(user_id, vehicle_id)

        title = first_message.strip()
        if len(title) > 40:
            title = title[:37] + "..."

        conversation = BotConversation(
            user_id=user_id,
            title=title,
            vehicle_id=vehicle.id if vehicle else None,
        )
        self.session.add(conversation)
        await self.session.flush()

        user_msg = BotMessage(
            conversation_id=conversation.id,
            role="user",
            content=first_message
        )
        self.session.add(user_msg)

        history = [{"role": "user", "content": first_message}]
        system_prompt = self._build_system_prompt(vehicle)
        location_context = self._build_location_context(latitude, longitude)
        result = await self.orchestrator.run(user_id, system_prompt, history, location_context)

        assistant_msg = BotMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=result.content,
            model_used=result.model_used,
            tokens_used=result.tokens_used,
            response_time_ms=result.response_time_ms,
            tool_calls=result.tool_calls,
        )
        self.session.add(assistant_msg)

        conversation.updated_at = datetime.utcnow()

        return conversation

    async def _load_history(self, conversation_id: int) -> list[BotMessage]:
        stmt = select(BotMessage).where(BotMessage.conversation_id == conversation_id).order_by(BotMessage.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def send_message(
        self,
        user_id: int,
        conversation_id: int,
        content: str,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> BotMessage:
        """Agrega un mensaje del usuario a una conversación activa y devuelve la respuesta del bot."""
        conversation = await self.get_conversation(user_id, conversation_id)
        if not conversation:
            raise ValueError("Conversación no encontrada o no pertenece al usuario.")

        user_msg = BotMessage(
            conversation_id=conversation_id,
            role="user",
            content=content
        )
        self.session.add(user_msg)
        await self.session.flush()

        messages = await self._load_history(conversation_id)
        history = [{"role": msg.role, "content": msg.content} for msg in messages]

        vehicle = conversation.vehicle if conversation.vehicle_id else None
        system_prompt = self._build_system_prompt(vehicle)
        location_context = self._build_location_context(latitude, longitude)
        result = await self.orchestrator.run(user_id, system_prompt, history, location_context)

        assistant_msg = BotMessage(
            conversation_id=conversation_id,
            role="assistant",
            content=result.content,
            model_used=result.model_used,
            tokens_used=result.tokens_used,
            response_time_ms=result.response_time_ms,
            tool_calls=result.tool_calls,
        )
        self.session.add(assistant_msg)

        conversation.updated_at = datetime.utcnow()

        return assistant_msg

    async def add_user_message(self, user_id: int, conversation_id: int, content: str) -> BotConversation:
        """Persiste solo el mensaje del usuario (usado antes de iniciar el streaming de la respuesta)."""
        conversation = await self.get_conversation(user_id, conversation_id)
        if not conversation:
            raise ValueError("Conversación no encontrada o no pertenece al usuario.")

        user_msg = BotMessage(conversation_id=conversation_id, role="user", content=content)
        self.session.add(user_msg)
        conversation.updated_at = datetime.utcnow()
        return conversation

    async def stream_reply(
        self,
        user_id: int,
        conversation_id: int,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Genera la respuesta del bot en streaming para una conversación (el mensaje del
        usuario ya debe estar persistido vía add_user_message). Persiste el mensaje final
        del asistente cuando el stream termina.
        """
        conversation = await self.get_conversation(user_id, conversation_id)
        if not conversation:
            yield {"type": "error", "message": "Conversación no encontrada."}
            return

        messages = await self._load_history(conversation_id)
        history = [{"role": msg.role, "content": msg.content} for msg in messages]

        vehicle = conversation.vehicle if conversation.vehicle_id else None
        system_prompt = self._build_system_prompt(vehicle)
        location_context = self._build_location_context(latitude, longitude)

        final_event: dict[str, Any] | None = None
        try:
            async for event in self.orchestrator.stream(user_id, system_prompt, history, location_context):
                if event["type"] == "final":
                    final_event = event
                yield event
        except Exception as exc:
            logger.error("Bot stream failed unexpectedly", error=str(exc))
            yield {"type": "error", "message": "Ocurrió un error generando la respuesta."}
            return

        if final_event is not None:
            assistant_msg = BotMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=final_event.get("content", ""),
                model_used=final_event.get("model_used"),
                tokens_used=final_event.get("tokens_used"),
                response_time_ms=final_event.get("response_time_ms"),
                tool_calls=final_event.get("tool_calls"),
            )
            self.session.add(assistant_msg)
            conversation.updated_at = datetime.utcnow()
            await self.session.commit()
            yield {"type": "persisted", "message_id": assistant_msg.id}

    async def list_suggestions(self, user_id: int, vehicle_id: int | None = None) -> list[dict[str, str]]:
        """Sugerencias de preguntas frecuentes, personalizadas si se conoce el vehículo."""
        vehicle = await self._resolve_owned_vehicle(user_id, vehicle_id)
        if not vehicle:
            return list(_GENERIC_SUGGESTIONS)

        label = f"{vehicle.marca or ''} {vehicle.modelo}".strip()
        suggestions = [
            {"id": item["id"], "text": item["text"].format(label=label)} for item in _VEHICLE_SUGGESTIONS
        ]
        suggestions.append({"id": "engine-light", "text": "Se encendió la luz de check engine, ¿es grave?"})
        return suggestions
