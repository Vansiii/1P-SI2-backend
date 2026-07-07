import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ...core.database import get_db_session
from ...shared.dependencies.auth import get_current_user
from ...models.user import User
from ...core.responses import create_success_response
from .service import BotService
from .schemas import (
    BotConversationCreate,
    BotConversationResponse,
    BotMessageCreate,
    BotMessageResponse,
    BotSuggestionResponse,
)

router = APIRouter(prefix="/bot", tags=["Bot de Asistencia"])


@router.post("/conversations", response_model=dict, status_code=status.HTTP_201_CREATED)
async def start_conversation(
    payload: BotConversationCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Inicia una nueva conversación con el bot de asistencia.
    """
    service = BotService(db)
    conversation = await service.create_conversation(
        current_user.id,
        payload.first_message,
        payload.vehicle_id,
        payload.latitude,
        payload.longitude,
    )
    await db.commit()

    # Reload conversation to serialize properly
    db_conv = await service.get_conversation(current_user.id, conversation.id)
    return create_success_response(
        data=BotConversationResponse.model_validate(db_conv),
        message="Conversación iniciada con éxito."
    )


@router.get("/conversations", response_model=dict)
async def list_conversations(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Lista todas las conversaciones pasadas del bot del usuario autenticado.
    """
    service = BotService(db)
    conversations = await service.list_conversations(current_user.id)
    data = [BotConversationResponse.model_validate(c) for c in conversations]
    return create_success_response(
        data=data,
        message="Historial de conversaciones cargado."
    )


@router.get("/suggestions", response_model=dict)
async def get_suggestions(
    vehicle_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Devuelve preguntas sugeridas para iniciar una consulta, personalizadas si se
    provee un vehículo de contexto.
    """
    service = BotService(db)
    suggestions = await service.list_suggestions(current_user.id, vehicle_id)
    return create_success_response(
        data=[BotSuggestionResponse(**s) for s in suggestions],
        message="Sugerencias cargadas."
    )


@router.get("/conversations/{id}", response_model=dict)
async def get_conversation(
    id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene los detalles y mensajes de una conversación específica.
    """
    service = BotService(db)
    conversation = await service.get_conversation(current_user.id, id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada."
        )
    return create_success_response(
        data=BotConversationResponse.model_validate(conversation),
        message="Conversación cargada."
    )


@router.delete("/conversations/{id}", response_model=dict)
async def delete_conversation(
    id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Elimina una conversación específica y sus mensajes.
    """
    service = BotService(db)
    success = await service.delete_conversation(current_user.id, id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada."
        )
    await db.commit()
    return create_success_response(
        data=None,
        message="Conversación eliminada exitosamente."
    )


@router.post("/conversations/{id}/messages", response_model=dict)
async def send_message(
    id: int,
    payload: BotMessageCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Envía un mensaje adicional al bot en una conversación existente.
    """
    service = BotService(db)
    try:
        msg = await service.send_message(
            current_user.id, id, payload.content, payload.latitude, payload.longitude
        )
        await db.commit()
        return create_success_response(
            data=BotMessageResponse.model_validate(msg),
            message="Respuesta del asistente generada."
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/conversations/{id}/messages/stream")
async def send_message_stream(
    id: int,
    payload: BotMessageCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user)
):
    """
    Envía un mensaje al bot y transmite la respuesta en vivo vía Server-Sent Events.

    Formato de eventos (`event: <tipo>\\ndata: <json>\\n\\n`):
    - tool_result: se ejecutó una búsqueda (ej. marketplace) antes de responder.
    - token: fragmento incremental del texto de la respuesta.
    - final: respuesta completa + metadata (modelo usado, tokens, tool_calls, productos).
    - persisted: id del mensaje ya guardado en base de datos.
    - error: algo falló durante la generación.
    """
    service = BotService(db)
    try:
        await service.add_user_message(current_user.id, id, payload.content)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    async def event_generator():
        async for event in service.stream_reply(current_user.id, id, payload.latitude, payload.longitude):
            event_type = event.get("type", "message")
            yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
