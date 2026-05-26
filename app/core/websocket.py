"""
WebSocket connection manager for real-time communication.
"""
from typing import Dict, List, Set, Optional, Tuple
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime, timezone, timedelta
import json
import asyncio

from .logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """
    Gestiona conexiones WebSocket y rooms.

    Rooms disponibles:
    - incident_rooms: Participantes de un incidente (cliente, taller, técnico, admin)
    - workshop_rooms: Usuarios de un taller (owner + staff)
    - technician_rooms: Técnico individual (para eventos de asignación)
    - tracking_connections: Técnicos enviando ubicación
    - admin_user_ids: Administradores conectados (broadcast global admin)

    Seguimiento de eventos emitidos para evitar duplicados.
    """

    MAX_EMITTED_EVENT_IDS = 5000

    def __init__(self):
        # Multiple concurrent sockets per user (web + mobile, tracking + incident)
        self.active_connections: Dict[int, Set[WebSocket]] = {}

        self.incident_rooms: Dict[int, Set[int]] = {}
        self.workshop_rooms: Dict[int, Set[int]] = {}
        self.technician_rooms: Dict[int, Set[int]] = {}

        self.tracking_connections: Dict[int, WebSocket] = {}
        self.admin_user_ids: Set[int] = set()

        self.heartbeat_tasks: Dict[Tuple[int, int], asyncio.Task] = {}

        self._emitted_event_ids: Dict[str, Set[str]] = {}
        self._event_id_timestamps: Dict[str, datetime] = {}

    async def connect(self, websocket: WebSocket, user_id: int, user_type: str = None, workshop_id: int = None):
        """
        Registrar una conexión WebSocket ya aceptada.

        Args:
            websocket: Conexión WebSocket (ya aceptada)
            user_id: ID del usuario
            user_type: Tipo de usuario ('admin', 'workshop', 'client', 'technician')
            workshop_id: ID del taller (si aplica, para workshop_room)
        """
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)

        if user_type in ('admin', 'administrator'):
            self.admin_user_ids.add(user_id)

        # Join workshop room if user belongs to a workshop
        if workshop_id:
            await self.join_workshop_room(user_id, workshop_id)

        # Join technician room if user is a technician
        if user_type == 'technician':
            await self.join_technician_room(user_id)

        heartbeat_key = (user_id, id(websocket))
        self.heartbeat_tasks[heartbeat_key] = asyncio.create_task(
            self._heartbeat(websocket, user_id)
        )

        logger.info(
            f"WebSocket connected: user_id={user_id}, user_type={user_type}, "
            f"sockets={len(self.active_connections.get(user_id, set()))}"
        )

    def disconnect(self, user_id: int):
        """
        Desconectar un usuario del WebSocket y limpiar todos sus rooms.
        """
        sockets = list(self.active_connections.get(user_id, set()))
        for websocket in sockets:
            self.disconnect_socket(user_id, websocket, close_socket=False)
        self._cleanup_user_if_no_connections(user_id)
        logger.info(f"WebSocket disconnected (all sockets): user_id={user_id}")

    def disconnect_socket(self, user_id: int, websocket: WebSocket, close_socket: bool = False):
        """
        Disconnect only one socket for a user. Keeps other sockets alive.
        """
        heartbeat_key = (user_id, id(websocket))
        task = self.heartbeat_tasks.pop(heartbeat_key, None)
        if task:
            task.cancel()

        user_sockets = self.active_connections.get(user_id)
        if user_sockets and websocket in user_sockets:
            user_sockets.discard(websocket)
            if close_socket:
                try:
                    asyncio.create_task(websocket.close())
                except Exception:
                    pass
            if not user_sockets:
                self.active_connections.pop(user_id, None)

        self._cleanup_user_if_no_connections(user_id)

    def _cleanup_user_if_no_connections(self, user_id: int):
        """
        Remove user from rooms/admin sets only when no sockets remain.
        """
        if self.active_connections.get(user_id):
            return

        self.admin_user_ids.discard(user_id)

        if user_id in self.tracking_connections:
            del self.tracking_connections[user_id]

        for incident_id in list(self.incident_rooms.keys()):
            if user_id in self.incident_rooms[incident_id]:
                self.incident_rooms[incident_id].remove(user_id)
                if not self.incident_rooms[incident_id]:
                    del self.incident_rooms[incident_id]

        for workshop_id in list(self.workshop_rooms.keys()):
            if user_id in self.workshop_rooms[workshop_id]:
                self.workshop_rooms[workshop_id].remove(user_id)
                if not self.workshop_rooms[workshop_id]:
                    del self.workshop_rooms[workshop_id]

        if user_id in self.technician_rooms:
            del self.technician_rooms[user_id]

    async def join_incident_room(self, user_id: int, incident_id: int):
        """
        Unir un usuario a un room de incidente.
        """
        if incident_id not in self.incident_rooms:
            self.incident_rooms[incident_id] = set()

        self.incident_rooms[incident_id].add(user_id)

        logger.info(f"User {user_id} joined incident room {incident_id}")

    async def leave_incident_room(self, user_id: int, incident_id: int):
        """
        Remover un usuario de un room de incidente.
        """
        if incident_id in self.incident_rooms:
            self.incident_rooms[incident_id].discard(user_id)
            if not self.incident_rooms[incident_id]:
                del self.incident_rooms[incident_id]

        logger.info(f"User {user_id} left incident room {incident_id}")

    async def join_workshop_room(self, user_id: int, workshop_id: int):
        """
        Unir un usuario a un room de taller (para staff multi-usuario).
        """
        if workshop_id not in self.workshop_rooms:
            self.workshop_rooms[workshop_id] = set()
        self.workshop_rooms[workshop_id].add(user_id)
        logger.info(f"User {user_id} joined workshop room {workshop_id}")

    async def leave_workshop_room(self, user_id: int, workshop_id: int):
        """
        Remover un usuario de un room de taller.
        """
        if workshop_id in self.workshop_rooms:
            self.workshop_rooms[workshop_id].discard(user_id)
            if not self.workshop_rooms[workshop_id]:
                del self.workshop_rooms[workshop_id]
        logger.info(f"User {user_id} left workshop room {workshop_id}")

    async def join_technician_room(self, technician_id: int):
        """
        Crear room privado para un técnico.
        """
        self.technician_rooms[technician_id] = {technician_id}
        logger.info(f"Technician room created for technician {technician_id}")

    async def broadcast_to_workshop(self, workshop_id: int, message: dict, exclude_user: int = None):
        """
        Broadcast mensaje a todos los usuarios de un taller.
        Uses send_personal_message internally for dedup support.
        """
        if workshop_id not in self.workshop_rooms:
            return
        for user_id in self.workshop_rooms[workshop_id]:
            if exclude_user and user_id == exclude_user:
                continue
            await self.send_personal_message(user_id, message)

    async def send_to_technician(self, technician_id: int, message: dict):
        """
        Enviar mensaje al room de un técnico específico.
        """
        if technician_id in self.technician_rooms:
            for uid in self.technician_rooms[technician_id]:
                await self.send_personal_message(uid, message)
                break

    def was_event_emitted(self, event_id: str, user_id: int = None) -> bool:
        """
        Verificar si un evento ya fue emitido a un usuario específico (deduplicación server-side).
        
        La deduplicación es PER-USER para evitar que broadcasts a múltiples
        usuarios sean descartados para todos menos el primero.
        
        También limpia eventos expirados (> 5 min).
        """
        key = str(user_id) if user_id is not None else "__global__"
        
        if key not in self._emitted_event_ids:
            self._emitted_event_ids[key] = set()
        
        full_key = f"{key}:{event_id}"
        
        if full_key in self._emitted_event_ids[key]:
            return True
        
        self._emitted_event_ids[key].add(full_key)
        self._event_id_timestamps[full_key] = datetime.now(timezone.utc)

        # Limit per-user set size
        if len(self._emitted_event_ids[key]) > self.MAX_EMITTED_EVENT_IDS:
            oldest = min(
                self._emitted_event_ids[key],
                key=lambda eid: self._event_id_timestamps.get(eid, datetime.now(timezone.utc))
            )
            self._emitted_event_ids[key].discard(oldest)
            self._event_id_timestamps.pop(oldest, None)

        # Cleanup expired entries (> 5 minutes)
        expire_before = datetime.now(timezone.utc) - timedelta(minutes=5)
        for k in list(self._emitted_event_ids.keys()):
            expired = [
                eid for eid in self._emitted_event_ids[k]
                if self._event_id_timestamps.get(eid, datetime.min) < expire_before
            ]
            for eid in expired:
                self._emitted_event_ids[k].discard(eid)
                self._event_id_timestamps.pop(eid, None)
            if not self._emitted_event_ids[k]:
                del self._emitted_event_ids[k]

        return False

    async def send_personal_message(self, user_id: int, message: dict, check_dedup: bool = True):
        """
        Enviar mensaje a un usuario específico con deduplicación opcional.
        """
        sockets = list(self.active_connections.get(user_id, set()))
        if not sockets:
            logger.debug(f"User {user_id} not connected, skipping message")
            return

        if check_dedup:
            event_id = message.get("event_id")
            if event_id and self.was_event_emitted(event_id, user_id):
                logger.debug(f"Skipping duplicate event {event_id} for user {user_id}")
                return

        disconnected_sockets: List[WebSocket] = []
        for websocket in sockets:
            try:
                if websocket.client_state.name == 'CONNECTED':
                    await websocket.send_json(message)
                else:
                    logger.warning(
                        f"WebSocket for user {user_id} not CONNECTED: {websocket.client_state.name}"
                    )
                    disconnected_sockets.append(websocket)
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {type(e).__name__}: {str(e)}")
                disconnected_sockets.append(websocket)

        for socket in disconnected_sockets:
            self.disconnect_socket(user_id, socket)

    async def send_to_user(self, user_id: int, message: dict):
        """
        Alias for send_personal_message for compatibility with OutboxProcessor.
        
        Args:
            user_id: ID del usuario
            message: Diccionario con el mensaje
        """
        await self.send_personal_message(user_id, message)

    async def broadcast_to_incident(self, incident_id: int, message: dict, exclude_user: int = None):
        """
        Broadcast mensaje a todos los usuarios en un room de incidente.
        Uses send_personal_message internally for dedup support.
        """
        if incident_id not in self.incident_rooms:
            return
        
        for user_id in self.incident_rooms[incident_id]:
            if exclude_user and user_id == exclude_user:
                continue
            await self.send_personal_message(user_id, message)

    async def broadcast_to_all(self, message: dict):
        """
        Broadcast mensaje a todos los usuarios conectados.
        Uses send_personal_message for per-user dedup support.
        
        Args:
            message: Diccionario con el mensaje
        """
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(user_id, message)

    async def broadcast_to_admins(self, message: dict):
        """
        Broadcast mensaje a todos los administradores conectados.
        Uses send_personal_message for per-user dedup support.
        
        Args:
            message: Diccionario con el mensaje
        """
        for user_id in list(self.admin_user_ids):
            await self.send_personal_message(user_id, message)
        
        logger.debug(f"Broadcast to {len(self.admin_user_ids)} admins")

    # ═══════════════════════════════════════════════════════════════════════
    # DEPRECATED legacy methods — use EventPublisher + OutboxProcessor instead
    # These methods emit in legacy format without event_id for deduplication.
    # They will be removed in a future version.
    # ═══════════════════════════════════════════════════════════════════════

    async def send_location_update(
        self,
        incident_id: int,
        technician_id: int,
        latitude: float,
        longitude: float,
        accuracy: float = None,
        speed: float = None,
        heading: float = None
    ):
        """DEPRECATED: Use EventPublisher with TrackingLocationUpdatedEvent instead."""
        logger.warning(
            "DEPRECATED: send_location_update() called. "
            "Use EventPublisher with TrackingLocationUpdatedEvent."
        )
        message = {
            "type": "location_update",
            "incident_id": incident_id,
            "technician_id": technician_id,
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": accuracy,
                "speed": speed,
                "heading": heading
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.broadcast_to_incident(incident_id, message)

    async def send_incident_status_change(
        self,
        incident_id: int,
        new_status: str,
        changed_by: int = None
    ):
        """DEPRECATED: Use EventPublisher with IncidentStatusChangedEvent instead."""
        logger.warning(
            "DEPRECATED: send_incident_status_change() called. "
            "Use EventPublisher with IncidentStatusChangedEvent."
        )
        message = {
            "type": "incident_status_change",
            "incident_id": incident_id,
            "new_status": new_status,
            "changed_by": changed_by,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.broadcast_to_incident(incident_id, message)

    async def send_technician_assigned(
        self,
        incident_id: int,
        technician_id: int,
        technician_name: str,
        workshop_name: str
    ):
        """DEPRECATED: Use EventPublisher with IncidentTechnicianOnWayEvent instead."""
        logger.warning(
            "DEPRECATED: send_technician_assigned() called. "
            "Use EventPublisher with IncidentTechnicianOnWayEvent."
        )
        message = {
            "type": "technician_assigned",
            "incident_id": incident_id,
            "technician": {
                "id": technician_id,
                "name": technician_name,
                "workshop": workshop_name
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.broadcast_to_incident(incident_id, message)

    async def send_technician_arrived(
        self,
        incident_id: int,
        technician_id: int
    ):
        """DEPRECATED: Use EventPublisher with IncidentTechnicianArrivedEvent instead."""
        logger.warning(
            "DEPRECATED: send_technician_arrived() called. "
            "Use EventPublisher with IncidentTechnicianArrivedEvent."
        )
        message = {
            "type": "technician_arrived",
            "incident_id": incident_id,
            "technician_id": technician_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.broadcast_to_incident(incident_id, message)

    async def send_message_notification(
        self,
        incident_id: int,
        sender_id: int,
        sender_name: str,
        message_text: str,
        message_id: int = None,
        sender_role: str = None
    ):
        """DEPRECATED: Use EventPublisher with ChatMessageSentEvent instead."""
        logger.warning(
            "DEPRECATED: send_message_notification() called. "
            "Use EventPublisher with ChatMessageSentEvent."
        )
        message = {
            "type": "new_message",
            "incident_id": incident_id,
            "message": {
                "id": message_id,
                "incident_id": incident_id,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "sender_role": sender_role,
                "message": message_text,
                "message_type": "text",
                "is_read": False,
                "read_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": None
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.broadcast_to_incident(incident_id, message, exclude_user=sender_id)

    async def _heartbeat(self, websocket: WebSocket, user_id: int):
        """
        Enviar ping periódico para mantener conexión viva.
        
        Args:
            websocket: Conexión WebSocket
            user_id: ID del usuario
        """
        try:
            while True:
                await asyncio.sleep(30)  # Ping cada 30 segundos
                try:
                    # Check if user is still in active connections
                    user_sockets = self.active_connections.get(user_id, set())
                    if websocket not in user_sockets:
                        logger.debug(f"🛑 User {user_id} no longer in active connections, stopping heartbeat")
                        break
                    
                    if websocket.client_state.name != 'CONNECTED':
                        logger.warning(f"⚠️ Heartbeat: WebSocket for user {user_id} not in CONNECTED state: {websocket.client_state.name}")
                        break
                    
                    logger.debug(f"💓 Sending heartbeat ping to user {user_id}")
                    await websocket.send_json({"type": "ping"})
                    logger.debug(f"✅ Heartbeat ping sent to user {user_id}")
                except Exception as ping_error:
                    logger.error(f"❌ Heartbeat error for user {user_id}: {type(ping_error).__name__}: {str(ping_error)}")
                    # Don't disconnect here - let the main loop handle it
                    break
        except asyncio.CancelledError:
            logger.debug(f"🛑 Heartbeat cancelled for user {user_id}")
            pass

    def get_connected_users_count(self) -> int:
        """Obtener número de usuarios conectados."""
        return len(self.active_connections)

    def get_incident_room_users(self, incident_id: int) -> List[int]:
        """Obtener lista de usuarios en un room de incidente."""
        return list(self.incident_rooms.get(incident_id, set()))

    def is_user_connected(self, user_id: int) -> bool:
        """Verificar si un usuario está conectado."""
        return bool(self.active_connections.get(user_id))


# Instancia global del ConnectionManager
manager = ConnectionManager()
