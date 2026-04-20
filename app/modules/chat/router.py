"""
Chat endpoints for managing conversations and messages.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.dependencies import get_current_user
from ...core.responses import success_response, error_response
from ...core.exceptions import NotFoundError, ValidationError
from .services import ChatService
from .schemas import (
    SendMessageRequest,
    MessageResponse,
    ConversationResponse,
    ConversationStatistics,
    MarkAsReadRequest
)
from ...models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/incidents/{incident_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    incident_id: int,
    request: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Send a message in an incident conversation.
    
    This endpoint:
    - Creates a message in the conversation
    - Updates conversation metadata
    - Broadcasts message via WebSocket to all participants
    - Increments unread count for recipient
    
    **Permissions:** Client or assigned technician/workshop staff
    """
    chat_service = ChatService(db)

    try:
        message = await chat_service.send_message(
            incident_id=incident_id,
            sender_id=current_user.id,
            message_text=request.message,
            message_type=request.message_type
        )
        return message

    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/incidents/{incident_id}/conversation", response_model=ConversationResponse)
async def get_incident_conversation(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get or create conversation for an incident.
    
    This endpoint:
    - Returns existing conversation if it exists
    - Creates a new conversation if it doesn't exist (for accepted incidents)
    - Validates that the user has access to the incident
    
    **Permissions:** Client, assigned workshop, or assigned technician
    """
    from ...models.incidente import Incidente
    from sqlalchemy import select
    
    chat_service = ChatService(db)

    # Verify incident exists and user has access
    incident = await db.scalar(
        select(Incidente).where(Incidente.id == incident_id)
    )
    
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    
    # Check permissions
    has_access = False
    if current_user.user_type == "client" and incident.client_id == current_user.id:
        has_access = True
    elif current_user.user_type == "workshop" and incident.taller_id == current_user.id:
        has_access = True
    elif current_user.user_type == "technician":
        # Check if technician is assigned to this incident
        from ...models.technician import Technician
        technician = await db.scalar(
            select(Technician).where(Technician.user_id == current_user.id)
        )
        if technician and incident.tecnico_id == technician.id:
            has_access = True
    
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this incident's conversation"
        )
    
    # Get or create conversation
    conversation = await chat_service.get_or_create_conversation(
        incident_id=incident_id,
        client_id=incident.client_id,
        workshop_id=incident.taller_id
    )

    return conversation


@router.get("/incidents/{incident_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    incident_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    before_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get messages for an incident conversation.
    
    Returns messages ordered by creation time (newest first).
    Supports pagination using limit/offset or before_id.
    
    **Permissions:** Client or assigned technician/workshop staff
    """
    chat_service = ChatService(db)

    messages = await chat_service.get_messages(
        incident_id=incident_id,
        limit=limit,
        offset=offset,
        before_id=before_id
    )

    return messages


@router.post("/incidents/{incident_id}/messages/mark-read", status_code=status.HTTP_200_OK)
async def mark_messages_as_read(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mark all unread messages as read for the current user.
    
    This endpoint:
    - Marks all messages from other participants as read
    - Updates read_at timestamp
    - Resets unread count in conversation
    
    **Permissions:** Client or assigned technician/workshop staff
    """
    chat_service = ChatService(db)

    try:
        marked_count = await chat_service.mark_messages_as_read(
            incident_id=incident_id,
            user_id=current_user.id
        )

        return success_response(
            data={"marked_count": marked_count},
            message=f"Marked {marked_count} messages as read"
        )

    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/incidents/{incident_id}/conversation", response_model=ConversationResponse)
async def get_conversation(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get conversation metadata for an incident.
    
    Returns conversation information including unread counts.
    
    **Permissions:** Client or assigned technician/workshop staff
    """
    chat_service = ChatService(db)

    conversation = await chat_service.get_conversation(incident_id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation for incident {incident_id} not found"
        )

    return conversation


@router.get("/conversations", response_model=List[ConversationResponse])
async def get_user_conversations(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all conversations for the current user.
    
    Returns conversations ordered by last message time.
    
    **Permissions:** Authenticated user
    """
    chat_service = ChatService(db)

    # Determine if user is client or workshop staff
    is_client = current_user.user_type == "client"

    conversations = await chat_service.get_user_conversations(
        user_id=current_user.id,
        is_client=is_client,
        limit=limit
    )

    return conversations


@router.get("/incidents/{incident_id}/unread-count", status_code=status.HTTP_200_OK)
async def get_unread_count(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get unread message count for the current user in an incident.
    
    **Permissions:** Client or assigned technician/workshop staff
    """
    chat_service = ChatService(db)

    unread_count = await chat_service.get_unread_count(
        incident_id=incident_id,
        user_id=current_user.id
    )

    return success_response(
        data={"unread_count": unread_count},
        message="Unread count retrieved successfully"
    )


@router.get("/incidents/{incident_id}/statistics", response_model=ConversationStatistics)
async def get_conversation_statistics(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get statistics for a conversation.
    
    Returns total messages, unread count, and message timestamps.
    
    **Permissions:** Client or assigned technician/workshop staff
    """
    chat_service = ChatService(db)

    stats = await chat_service.get_conversation_statistics(incident_id)

    return stats


@router.delete("/messages/{message_id}", status_code=status.HTTP_200_OK)
async def delete_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a message (soft delete).
    
    Only the sender can delete their own messages.
    The message content is replaced with "[Mensaje eliminado]".
    
    **Permissions:** Message sender only
    """
    chat_service = ChatService(db)

    try:
        await chat_service.delete_message(
            message_id=message_id,
            user_id=current_user.id
        )

        return success_response(
            message="Message deleted successfully"
        )

    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
