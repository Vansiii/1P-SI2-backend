"""
WebSocket endpoints for real-time communication.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Dict
import json
from datetime import datetime, timedelta

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


# Rate limiting for failed authentication attempts
# Structure: {user_id: {"count": int, "first_attempt": datetime, "blocked_until": datetime}}
_auth_failure_tracker: Dict[int, Dict] = {}

# Rate limiting configuration
MAX_AUTH_FAILURES = 5  # Maximum failed attempts
AUTH_FAILURE_WINDOW = 60  # Time window in seconds (1 minute)
BLOCK_DURATION = 300  # Block duration in seconds (5 minutes)


def check_rate_limit(user_id: int) -> tuple[bool, Optional[int]]:
    """
    Check if user is rate limited due to repeated authentication failures.
    
    Args:
        user_id: User ID to check
        
    Returns:
        Tuple of (is_allowed, seconds_until_unblock)
        - is_allowed: True if user can attempt connection, False if blocked
        - seconds_until_unblock: Seconds remaining in block, or None if not blocked
    """
    now = datetime.utcnow()
    
    if user_id not in _auth_failure_tracker:
        return True, None
    
    tracker = _auth_failure_tracker[user_id]
    
    # Check if user is currently blocked
    if "blocked_until" in tracker:
        if now < tracker["blocked_until"]:
            seconds_remaining = int((tracker["blocked_until"] - now).total_seconds())
            logger.warning(
                f"🚫 User {user_id} is rate limited. "
                f"Blocked for {seconds_remaining} more seconds"
            )
            return False, seconds_remaining
        else:
            # Block expired, reset tracker
            del _auth_failure_tracker[user_id]
            return True, None
    
    # Check if failure window has expired
    if now - tracker["first_attempt"] > timedelta(seconds=AUTH_FAILURE_WINDOW):
        # Window expired, reset tracker
        del _auth_failure_tracker[user_id]
        return True, None
    
    return True, None


def record_auth_failure(user_id: int):
    """
    Record an authentication failure and apply rate limiting if threshold exceeded.
    
    Args:
        user_id: User ID that failed authentication
    """
    now = datetime.utcnow()
    
    if user_id not in _auth_failure_tracker:
        _auth_failure_tracker[user_id] = {
            "count": 1,
            "first_attempt": now
        }
        logger.info(f"⚠️ Auth failure 1/{MAX_AUTH_FAILURES} for user {user_id}")
        return
    
    tracker = _auth_failure_tracker[user_id]
    
    # Check if we're in a new window
    if now - tracker["first_attempt"] > timedelta(seconds=AUTH_FAILURE_WINDOW):
        # Reset counter for new window
        tracker["count"] = 1
        tracker["first_attempt"] = now
        logger.info(f"⚠️ Auth failure 1/{MAX_AUTH_FAILURES} for user {user_id} (new window)")
        return
    
    # Increment failure count
    tracker["count"] += 1
    logger.warning(
        f"⚠️ Auth failure {tracker['count']}/{MAX_AUTH_FAILURES} for user {user_id}"
    )
    
    # Check if threshold exceeded
    if tracker["count"] >= MAX_AUTH_FAILURES:
        tracker["blocked_until"] = now + timedelta(seconds=BLOCK_DURATION)
        logger.error(
            f"🚫 User {user_id} BLOCKED for {BLOCK_DURATION} seconds "
            f"due to {tracker['count']} failed auth attempts"
        )


def reset_auth_failures(user_id: int):
    """
    Reset authentication failure tracking for a user (called on successful auth).
    
    Args:
        user_id: User ID to reset
    """
    if user_id in _auth_failure_tracker:
        del _auth_failure_tracker[user_id]
        logger.debug(f"✅ Reset auth failure tracker for user {user_id}")


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
):
    """
    WebSocket endpoint for general user tracking and notifications.
    
    Handles:
    - General notifications
    - Connection management
    - Heartbeat/ping-pong
    - Technician status updates (for workshops)
    - Rate limiting for failed authentication attempts
    
    Query Parameters:
        token: JWT authentication token
    
    NOTE: Database session is created per-message, not per-connection,
    to avoid holding a connection for the entire WebSocket lifetime.
    """
    # ✅ IMPORTANT: Accept connection FIRST, then authenticate
    # This prevents Uvicorn from rejecting the connection with 403
    await websocket.accept()
    
    # Check rate limiting AFTER accepting connection
    is_allowed, seconds_remaining = check_rate_limit(user_id)
    if not is_allowed:
        logger.warning(
            f"🚫 WebSocket connection BLOCKED for user {user_id} due to rate limiting. "
            f"Retry in {seconds_remaining} seconds"
        )
        await websocket.send_json({
            "type": "error",
            "code": "rate_limited",
            "message": f"Demasiados intentos fallidos. Intenta de nuevo en {seconds_remaining} segundos.",
            "retry_after": seconds_remaining
        })
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # Create a temporary session just for authentication
    async for session in get_db_session():
        # Authenticate user
        user = await authenticate_websocket(token, session)
        if user is None:
            logger.warning(f"WebSocket authentication failed for user_id={user_id}")
            
            # Don't record rate limit failure for expired tokens - let client refresh
            # Only record for invalid tokens (malformed, wrong signature, etc.)
            # This prevents blocking users who just need to refresh their token
            
            await websocket.send_json({
                "type": "error",
                "code": "authentication_failed",
                "message": "Token inválido o expirado. Por favor, inicia sesión nuevamente.",
                "action": "refresh_token"  # Hint to client to refresh token
            })
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Verificar que el user_id del token coincida con el user_id de la ruta
        # O que sea un administrador que puede conectarse a cualquier tracking
        # IMPORTANTE: Para workshops, permitir acceso a su propio user_id
        has_access = (
            user.id == user_id or 
            user.user_type == "administrator" or
            (user.user_type == "workshop" and user.id == user_id)
        )
        
        if not has_access:
            logger.warning(f"User {user.id} ({user.user_type}) does not have access to tracking endpoint for user_id={user_id}")
            
            # Record as authentication failure
            record_auth_failure(user.id)
            
            await websocket.send_json({
                "type": "error",
                "code": "access_denied",
                "message": "No tienes acceso a este recurso."
            })
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # ✅ Authentication successful - reset failure tracker
        reset_auth_failures(user_id)
        
        logger.info(f"✅ WebSocket tracking connection authenticated for user {user.id} ({user.user_type})")
        
        # Store user type for later use
        user_type = user.user_type
        
        # Break out of the session context - we don't need it anymore
        break
    
    # Connect user with user type
    await manager.connect(websocket, user_id, user_type=user_type)
    
    try:
        while True:
            # Listen for messages from client
            try:
                data = await websocket.receive_text()
                logger.debug(f"📨 Received message from user {user_id}: {data[:100]}...")
            except Exception as receive_error:
                logger.error(f"❌ Error receiving message from user {user_id}: {type(receive_error).__name__}: {str(receive_error)}")
                raise
            
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                # Handle different message types
                if message_type == "pong":
                    # Client responded to ping
                    logger.debug(f"Received pong from user {user_id}")
                
                elif message_type == "ping":
                    # Client sent ping, respond with pong
                    logger.debug(f"Received ping from user {user_id}, responding with pong")
                    await manager.send_personal_message(user_id, {
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                elif message_type == "get_missed_events":
                    # Client is requesting missed events (mobile feature)
                    # For now, just acknowledge the request
                    # TODO: Implement missed events recovery from database
                    logger.info(f"📥 Received get_missed_events from user {user_id}, responding with empty list")
                    try:
                        await manager.send_personal_message(user_id, {
                            "type": "missed_events_response",
                            "events": [],  # Empty for now
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        logger.info(f"✅ Sent missed_events_response to user {user_id}")
                    except Exception as send_error:
                        logger.error(f"❌ Error sending missed_events_response to user {user_id}: {str(send_error)}")
                        raise
                    
                elif message_type == "join_incident":
                    # User wants to join an incident room
                    incident_id = message.get("incident_id")
                    if incident_id:
                        # Create a session just for this query
                        async for db_session in get_db_session():
                            # Verify user has access to this incident
                            incident = await db_session.scalar(
                                select(Incidente).where(Incidente.id == incident_id)
                            )
                            if incident and (
                                incident.client_id == user_id or 
                                incident.tecnico_id == user_id or
                                incident.taller_id == user_id or  # Workshop access
                                user_type in ("administrator", "workshop")
                            ):
                                await manager.join_incident_room(user_id, incident_id)
                            else:
                                await manager.send_personal_message(user_id, {
                                    "type": "error",
                                    "message": "No tienes acceso a este incidente"
                                })
                            break  # Exit the session context
                
                elif message_type == "leave_incident":
                    # User wants to leave an incident room
                    incident_id = message.get("incident_id")
                    if incident_id:
                        await manager.leave_incident_room(user_id, incident_id)
                
                else:
                    logger.warning(f"Unknown message type: {message_type} from user {user_id}")
                    
            except json.JSONDecodeError as json_error:
                logger.warning(f"Invalid JSON received from user {user_id}: {data}, error: {str(json_error)}")
            except Exception as processing_error:
                logger.error(f"❌ Error processing message from user {user_id}: {type(processing_error).__name__}: {str(processing_error)}", exc_info=True)
                # No re-raise aquí para mantener la conexión viva
                
    except WebSocketDisconnect as disconnect_error:
        logger.info(f"WebSocket disconnected normally: user_id={user_id}, code={getattr(disconnect_error, 'code', 'unknown')}, reason={getattr(disconnect_error, 'reason', 'unknown')}")
    except Exception as e:
        logger.error(f"❌ WebSocket error for user {user_id}: {type(e).__name__}: {str(e)}", exc_info=True)
    finally:
        logger.info(f"🔌 Cleaning up WebSocket connection for user {user_id}")
        manager.disconnect(user_id)


@router.websocket("/ws/incidents/{incident_id}")
async def websocket_incident_endpoint(
    websocket: WebSocket,
    incident_id: int,
    token: str = Query(..., description="JWT token for authentication"),
):
    """
    WebSocket endpoint for incident-specific communication.
    
    Handles:
    - Real-time location updates
    - Incident status changes
    - Chat messages
    - Technician updates
    - Rate limiting for failed authentication attempts
    
    Query Parameters:
        token: JWT authentication token
    
    NOTE: Database session is created per-message, not per-connection,
    to avoid holding a connection for the entire WebSocket lifetime.
    """
    logger.info(f"WebSocket connection attempt for incident {incident_id}")
    logger.info(f"Token received: {token[:20] if token else 'NO TOKEN'}...")
    
    # ✅ IMPORTANT: Accept connection FIRST, then authenticate
    # This prevents Uvicorn from rejecting the connection with 403
    await websocket.accept()
    
    # Create a temporary session just for authentication and authorization
    async for session in get_db_session():
        # Authenticate user AFTER accepting connection
        user = await authenticate_websocket(token, session)
        if user is None:
            logger.warning(f"WebSocket authentication failed for incident {incident_id}")
            
            # Don't record rate limit failure for expired tokens
            # This prevents blocking users who just need to refresh their token
            
            # Connection already accepted, just send error and close
            await websocket.send_json({
                "type": "error",
                "code": "authentication_failed",
                "message": "Token inválido o expirado. Por favor, inicia sesión nuevamente.",
                "action": "refresh_token"  # Hint to client to refresh token
            })
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        logger.info(f"User authenticated: {user.id} ({user.user_type})")
        
        # Check rate limiting for this user
        is_allowed, seconds_remaining = check_rate_limit(user.id)
        if not is_allowed:
            logger.warning(
                f"🚫 WebSocket connection BLOCKED for user {user.id} on incident {incident_id} "
                f"due to rate limiting. Retry in {seconds_remaining} seconds"
            )
            await websocket.send_json({
                "type": "error",
                "code": "rate_limited",
                "message": f"Demasiados intentos fallidos. Intenta de nuevo en {seconds_remaining} segundos.",
                "retry_after": seconds_remaining
            })
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Verify user has access to this incident AFTER accepting connection
        incident = await session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )
        
        if incident is None:
            logger.warning(f"Incident {incident_id} not found")
            await websocket.send_json({
                "type": "error",
                "code": "not_found",
                "message": "Incidente no encontrado."
            })
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
            await websocket.send_json({
                "type": "error",
                "code": "access_denied",
                "message": "No tienes acceso a este incidente."
            })
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # ✅ Authentication and authorization successful - reset failure tracker
        reset_auth_failures(user.id)
        # No need to reset incident-based tracker since we're not using it anymore
        
        # Store user info for later use
        user_id = user.id
        user_type = user.user_type
        user_first_name = user.first_name
        user_last_name = user.last_name
        
        # Break out of the session context
        break
    
    # Connection already accepted, log success
    logger.info(f"✅ WebSocket connection authenticated for user {user_id} on incident {incident_id}")
    
    # Connect user and join incident room with user type
    await manager.connect(websocket, user_id, user_type=user_type)
    await manager.join_incident_room(user_id, incident_id)
    
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
                    if user_type == "technician":
                        # Verify this technician is assigned to this incident
                        async for db_session in get_db_session():
                            incident = await db_session.scalar(
                                select(Incidente).where(Incidente.id == incident_id)
                            )
                            if incident and incident.tecnico_id == user_id:
                                location = message.get("location", {})
                                latitude = location.get("latitude")
                                longitude = location.get("longitude")
                                
                                if latitude is not None and longitude is not None:
                                    await manager.send_location_update(
                                        incident_id=incident_id,
                                        technician_id=user_id,
                                        latitude=latitude,
                                        longitude=longitude,
                                        accuracy=location.get("accuracy"),
                                        speed=location.get("speed"),
                                        heading=location.get("heading")
                                    )
                            else:
                                await manager.send_personal_message(user_id, {
                                    "type": "error",
                                    "message": "No autorizado para enviar ubicación"
                                })
                            break
                    else:
                        await manager.send_personal_message(user_id, {
                            "type": "error",
                            "message": "No autorizado para enviar ubicación"
                        })
                
                elif message_type == "chat_message":
                    # User sending chat message
                    message_text = message.get("message", "").strip()
                    if message_text:
                        await manager.send_message_notification(
                            incident_id=incident_id,
                            sender_id=user_id,
                            sender_name=f"{user_first_name} {user_last_name}",
                            message_text=message_text
                        )

                elif message_type == "typing_start":
                    # User started typing — broadcast to incident room excluding sender
                    await emit_to_incident_room(
                        incident_id=incident_id,
                        event_type=EventTypes.USER_TYPING,
                        data={
                            "user_id": user_id,
                            "user_name": f"{user_first_name} {user_last_name}",
                            "incident_id": incident_id,
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        exclude_user=user_id
                    )

                elif message_type == "typing_stop":
                    # User stopped typing — broadcast to incident room excluding sender
                    await emit_to_incident_room(
                        incident_id=incident_id,
                        event_type=EventTypes.USER_STOPPED_TYPING,
                        data={
                            "user_id": user_id,
                            "user_name": f"{user_first_name} {user_last_name}",
                            "incident_id": incident_id,
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        exclude_user=user_id
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


@router.get("/ws/rate-limit/status")
async def rate_limit_status():
    """
    Get rate limiting status for all tracked users.
    Useful for debugging and monitoring.
    """
    now = datetime.utcnow()
    status_list = []
    
    for user_id, tracker in _auth_failure_tracker.items():
        status_entry = {
            "user_id": user_id,
            "failure_count": tracker["count"],
            "first_attempt": tracker["first_attempt"].isoformat(),
        }
        
        if "blocked_until" in tracker:
            seconds_remaining = int((tracker["blocked_until"] - now).total_seconds())
            status_entry["blocked"] = True
            status_entry["blocked_until"] = tracker["blocked_until"].isoformat()
            status_entry["seconds_remaining"] = max(0, seconds_remaining)
        else:
            status_entry["blocked"] = False
        
        status_list.append(status_entry)
    
    return {
        "tracked_users": len(_auth_failure_tracker),
        "rate_limit_config": {
            "max_failures": MAX_AUTH_FAILURES,
            "failure_window_seconds": AUTH_FAILURE_WINDOW,
            "block_duration_seconds": BLOCK_DURATION
        },
        "users": status_list
    }


@router.post("/ws/rate-limit/reset/{user_id}")
async def reset_rate_limit(user_id: int):
    """
    Reset rate limiting for a specific user.
    Useful for unblocking users manually.
    """
    if user_id in _auth_failure_tracker:
        del _auth_failure_tracker[user_id]
        return {
            "success": True,
            "message": f"Rate limit reset for user {user_id}"
        }
    else:
        return {
            "success": False,
            "message": f"No rate limit tracking found for user {user_id}"
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