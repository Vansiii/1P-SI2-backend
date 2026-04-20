"""
WebSocket endpoints for real-time communication.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import json
from datetime import datetime

from ...core.websocket import manager
from ...core.database import get_db_session
from ...core.security import decode_access_token
from ...core.logging import get_logger
from ...core.websocket_events import emit_to_incident_room, EventTypes
from ...models.user import User
from ...models.incidente import Incidente
from ...modules.auth.schemas import TokenPayload

logger = get_logger(__name__)

router = APIRouter()


async def authenticate_websocket(token: str, session: AsyncSession) -> Optional[User]:
    """
    Authenticate WebSocket connection using JWT token.
    
    Args:
        token: JWT token from query parameter
        session: Database session
        
    Returns:
        User object if authentication successful, None otherwise
    """
    try:
        # Decode JWT token
        token_data = decode_access_token(token)
        token_payload = TokenPayload.model_validate(token_data)
        
        # Get user from database
        user_id = int(token_payload.sub)
        user = await session.scalar(select(User).where(User.id == user_id))
        
        if user is None or not user.is_active:
            return None
            
        return user
        
    except Exception as e:
        logger.error(f"WebSocket authentication failed: {str(e)}")
        return None


@router.websocket("/ws/tracking/{user_id}")
async def websocket_tracking_endpoint(
    websocket: WebSocket,
    user_id: int,
    token: str = Query(..., description="JWT token for authentication"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    WebSocket endpoint for general user tracking and notifications.
    
    Handles:
    - General notifications
    - Connection management
    - Heartbeat/ping-pong
    - Technician status updates (for workshops)
    
    Query Parameters:
        token: JWT authentication token
    """
    # Authenticate user
    user = await authenticate_websocket(token, session)
    if user is None:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    has_access = (
        user.id == user_id or 
        user.user_type in ("administrator", "workshop")
    )
    
    if not has_access:
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Accept connection - all validations passed
    await websocket.accept()
    
    # Connect user with user type
    await manager.connect(websocket, user_id, user_type=user.user_type)
    
    try:
        while True:
            # Listen for messages from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                # Handle different message types
                if message_type == "pong":
                    # Client responded to ping
                    logger.debug(f"Received pong from user {user_id}")
                    
                elif message_type == "join_incident":
                    # User wants to join an incident room
                    incident_id = message.get("incident_id")
                    if incident_id:
                        # Verify user has access to this incident
                        incident = await session.scalar(
                            select(Incidente).where(Incidente.id == incident_id)
                        )
                        if incident and (
                            incident.client_id == user_id or 
                            incident.tecnico_id == user_id or
                            incident.taller_id == user_id or  # Workshop access
                            user.user_type in ("administrator", "workshop")
                        ):
                            await manager.join_incident_room(user_id, incident_id)
                        else:
                            await manager.send_personal_message(user_id, {
                                "type": "error",
                                "message": "No tienes acceso a este incidente"
                            })
                
                elif message_type == "leave_incident":
                    # User wants to leave an incident room
                    incident_id = message.get("incident_id")
                    if incident_id:
                        await manager.leave_incident_room(user_id, incident_id)
                
                else:
                    logger.warning(f"Unknown message type: {message_type} from user {user_id}")
                    
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received from user {user_id}: {data}")
            except Exception as e:
                logger.error(f"Error processing message from user {user_id}: {str(e)}")
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user_id={user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {str(e)}")
    finally:
        manager.disconnect(user_id)


@router.websocket("/ws/incidents/{incident_id}")
async def websocket_incident_endpoint(
    websocket: WebSocket,
    incident_id: int,
    token: str = Query(..., description="JWT token for authentication"),
    session: AsyncSession = Depends(get_db_session)
):
    """
    WebSocket endpoint for incident-specific communication.
    
    Handles:
    - Real-time location updates
    - Incident status changes
    - Chat messages
    - Technician updates
    
    Query Parameters:
        token: JWT authentication token
    """
    logger.info(f"WebSocket connection attempt for incident {incident_id}")
    logger.info(f"Token received: {token[:20] if token else 'NO TOKEN'}...")
    
    # Authenticate user BEFORE accepting connection
    user = await authenticate_websocket(token, session)
    if user is None:
        logger.warning(f"WebSocket authentication failed for incident {incident_id}")
        # Reject connection by accepting and immediately closing with error code
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    logger.info(f"User authenticated: {user.id} ({user.user_type})")
    
    # Verify user has access to this incident BEFORE accepting connection
    incident = await session.scalar(
        select(Incidente).where(Incidente.id == incident_id)
    )
    
    if incident is None:
        logger.warning(f"Incident {incident_id} not found")
        await websocket.accept()
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
        return
    
    # Check if user has access to this incident
    has_access = (
        incident.client_id == user.id or 
        incident.taller_id == user.id or  # Workshop access
        incident.tecnico_id == user.id or
        user.user_type == "administrator"
    )
    
    logger.info(f"Access check: client_id={incident.client_id}, taller_id={incident.taller_id}, tecnico_id={incident.tecnico_id}, user_id={user.id}, has_access={has_access}")
    
    if not has_access:
        logger.warning(f"User {user.id} does not have access to incident {incident_id}")
        await websocket.accept()
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Accept WebSocket connection - all validations passed
    await websocket.accept()
    logger.info(f"✅ WebSocket connection accepted for user {user.id} on incident {incident_id}")
    
    # Connect user and join incident room with user type
    await manager.connect(websocket, user.id, user_type=user.user_type)
    await manager.join_incident_room(user.id, incident_id)
    
    try:
        while True:
            # Listen for messages from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                # Handle different message types
                if message_type == "pong":
                    # Client responded to ping
                    logger.debug(f"Received pong from user {user.id} in incident {incident_id}")
                    
                elif message_type == "location_update":
                    # Technician sending location update
                    if user.user_type == "technician" and incident.tecnico_id == user.id:
                        location = message.get("location", {})
                        latitude = location.get("latitude")
                        longitude = location.get("longitude")
                        
                        if latitude is not None and longitude is not None:
                            await manager.send_location_update(
                                incident_id=incident_id,
                                technician_id=user.id,
                                latitude=latitude,
                                longitude=longitude,
                                accuracy=location.get("accuracy"),
                                speed=location.get("speed"),
                                heading=location.get("heading")
                            )
                    else:
                        await manager.send_personal_message(user.id, {
                            "type": "error",
                            "message": "No autorizado para enviar ubicación"
                        })
                
                elif message_type == "chat_message":
                    # User sending chat message
                    message_text = message.get("message", "").strip()
                    if message_text:
                        await manager.send_message_notification(
                            incident_id=incident_id,
                            sender_id=user.id,
                            sender_name=f"{user.first_name} {user.last_name}",
                            message_text=message_text
                        )

                elif message_type == "typing_start":
                    # User started typing — broadcast to incident room excluding sender
                    await emit_to_incident_room(
                        incident_id=incident_id,
                        event_type=EventTypes.USER_TYPING,
                        data={
                            "user_id": user.id,
                            "user_name": f"{user.first_name} {user.last_name}",
                            "incident_id": incident_id,
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        exclude_user=user.id
                    )

                elif message_type == "typing_stop":
                    # User stopped typing — broadcast to incident room excluding sender
                    await emit_to_incident_room(
                        incident_id=incident_id,
                        event_type=EventTypes.USER_STOPPED_TYPING,
                        data={
                            "user_id": user.id,
                            "user_name": f"{user.first_name} {user.last_name}",
                            "incident_id": incident_id,
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        exclude_user=user.id
                    )

                elif message_type == "get_missed_events":
                    # Client requesting missed events (e.g., messages, status updates)
                    logger.debug(f"User {user.id} requesting missed events for incident {incident_id}")
                    
                    # Send acknowledgment that request was received
                    await manager.send_personal_message(user.id, {
                        "type": "missed_events_response",
                        "incident_id": incident_id,
                        "events": [],  # TODO: Implement actual missed events logic
                        "timestamp": datetime.utcnow().isoformat()
                    })

                elif message_type == "ping":
                    # Client sending ping for connection health check
                    logger.debug(f"Received ping from user {user.id} in incident {incident_id}")
                    
                    # Respond with pong
                    await manager.send_personal_message(user.id, {
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })

                else:
                    logger.warning(f"Unknown message type: {message_type} from user {user.id} in incident {incident_id}")
                    
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received from user {user.id} in incident {incident_id}: {data}")
            except Exception as e:
                logger.error(f"Error processing message from user {user.id} in incident {incident_id}: {str(e)}")
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user_id={user.id}, incident_id={incident_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user.id} in incident {incident_id}: {str(e)}")
    finally:
        manager.disconnect(user.id)


@router.get("/ws/status")
async def websocket_status():
    """
    Get WebSocket connection status and statistics.
    """
    return {
        "connected_users": manager.get_connected_users_count(),
        "active_incident_rooms": len(manager.incident_rooms),
        "incident_rooms": {
            str(incident_id): len(users) 
            for incident_id, users in manager.incident_rooms.items()
        }
    }


@router.get("/ws/incidents/{incident_id}/users")
async def get_incident_room_users(incident_id: int):
    """
    Get list of users connected to an incident room.
    """
    users = manager.get_incident_room_users(incident_id)
    return {
        "incident_id": incident_id,
        "connected_users": users,
        "user_count": len(users)
    }