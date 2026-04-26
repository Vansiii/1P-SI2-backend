"""
WebSocket connection manager for real-time communication.
"""
from typing import Dict, List, Set
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime
import json
import asyncio

from .logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """
    Gestiona conexiones WebSocket y rooms por incidente.
    Permite broadcast de eventos a usuarios específicos o a todos en un room.
    """

    def __init__(self):
        # Conexiones activas por user_id
        self.active_connections: Dict[int, WebSocket] = {}
        
        # Rooms por incidente_id (set de user_ids)
        self.incident_rooms: Dict[int, Set[int]] = {}
        
        # Tracking rooms por technician_id
        self.tracking_connections: Dict[int, WebSocket] = {}
        
        # Admin user IDs for admin-only broadcasts
        self.admin_user_ids: Set[int] = set()
        
        # Heartbeat tasks
        self.heartbeat_tasks: Dict[int, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, user_id: int, user_type: str = None):
        """
        Registrar una conexión WebSocket ya aceptada.
        El endpoint es responsable de llamar websocket.accept() antes de invocar este método.
        
        Args:
            websocket: Conexión WebSocket (ya aceptada)
            user_id: ID del usuario
            user_type: Tipo de usuario ('admin', 'workshop', 'client', 'technician')
        """
        # Si ya existe una conexión, cerrar la anterior
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].close()
            except Exception:
                pass
        
        self.active_connections[user_id] = websocket
        
        # Track admin users for admin-only broadcasts
        if user_type in ('admin', 'administrator'):  # ✅ Corregido: aceptar ambos tipos
            self.admin_user_ids.add(user_id)
        
        # Iniciar heartbeat
        self.heartbeat_tasks[user_id] = asyncio.create_task(
            self._heartbeat(websocket, user_id)
        )
        
        logger.info(f"WebSocket connected: user_id={user_id}, user_type={user_type}")

    def disconnect(self, user_id: int):
        """
        Desconectar un usuario del WebSocket.
        
        Args:
            user_id: ID del usuario
        """
        # Cancelar heartbeat
        if user_id in self.heartbeat_tasks:
            self.heartbeat_tasks[user_id].cancel()
            del self.heartbeat_tasks[user_id]
        
        # Remover de conexiones activas
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        
        # Remover de admin users
        self.admin_user_ids.discard(user_id)
        
        # Remover de tracking
        if user_id in self.tracking_connections:
            del self.tracking_connections[user_id]
        
        # Remover de todos los rooms
        for incident_id in list(self.incident_rooms.keys()):
            if user_id in self.incident_rooms[incident_id]:
                self.incident_rooms[incident_id].remove(user_id)
                if not self.incident_rooms[incident_id]:
                    del self.incident_rooms[incident_id]
        
        logger.info(f"WebSocket disconnected: user_id={user_id}")

    async def join_incident_room(self, user_id: int, incident_id: int):
        """
        Unir un usuario a un room de incidente.
        
        Args:
            user_id: ID del usuario
            incident_id: ID del incidente
        """
        if incident_id not in self.incident_rooms:
            self.incident_rooms[incident_id] = set()
        
        self.incident_rooms[incident_id].add(user_id)
        
        logger.info(f"User {user_id} joined incident room {incident_id}")

    async def leave_incident_room(self, user_id: int, incident_id: int):
        """
        Remover un usuario de un room de incidente.
        
        Args:
            user_id: ID del usuario
            incident_id: ID del incidente
        """
        if incident_id in self.incident_rooms:
            self.incident_rooms[incident_id].discard(user_id)
            if not self.incident_rooms[incident_id]:
                del self.incident_rooms[incident_id]
        
        logger.info(f"User {user_id} left incident room {incident_id}")

    async def send_personal_message(self, user_id: int, message: dict):
        """
        Enviar mensaje a un usuario específico.
        
        Args:
            user_id: ID del usuario
            message: Diccionario con el mensaje
        """
        if user_id not in self.active_connections:
            logger.debug(f"User {user_id} not connected, skipping message")
            return
            
        try:
            websocket = self.active_connections[user_id]
            # Verificar que el WebSocket esté en estado correcto
            if websocket.client_state.name == 'CONNECTED':
                logger.debug(f"📤 Sending message to user {user_id}: type={message.get('type')}")
                await websocket.send_json(message)
                logger.debug(f"✅ Message sent successfully to user {user_id}")
            else:
                logger.warning(f"⚠️ WebSocket for user {user_id} is not in CONNECTED state: {websocket.client_state.name}")
                # Don't disconnect immediately - the connection might recover
        except Exception as e:
            logger.error(f"❌ Error sending message to user {user_id}: {type(e).__name__}: {str(e)}")
            # Solo desconectar si es un error crítico de conexión cerrada
            error_msg = str(e).lower()
            if "not connected" in error_msg or "closed" in error_msg or "disconnected" in error_msg:
                logger.info(f"🔌 Disconnecting user {user_id} due to connection error")
                self.disconnect(user_id)

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
        
        Args:
            incident_id: ID del incidente
            message: Diccionario con el mensaje
            exclude_user: ID de usuario a excluir (opcional)
        """
        if incident_id not in self.incident_rooms:
            return
        
        disconnected_users = []
        
        for user_id in self.incident_rooms[incident_id]:
            if exclude_user and user_id == exclude_user:
                continue
            
            if user_id in self.active_connections:
                try:
                    await self.active_connections[user_id].send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to user {user_id}: {str(e)}")
                    disconnected_users.append(user_id)
        
        # Limpiar usuarios desconectados
        for user_id in disconnected_users:
            self.disconnect(user_id)

    async def broadcast_to_all(self, message: dict):
        """
        Broadcast mensaje a todos los usuarios conectados.
        
        Args:
            message: Diccionario con el mensaje
        """
        disconnected_users = []
        
        for user_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to user {user_id}: {str(e)}")
                disconnected_users.append(user_id)
        
        # Limpiar usuarios desconectados
        for user_id in disconnected_users:
            self.disconnect(user_id)

    async def broadcast_to_admins(self, message: dict):
        """
        Broadcast mensaje a todos los administradores conectados.
        
        Args:
            message: Diccionario con el mensaje
        """
        disconnected_users = []
        
        for user_id in list(self.admin_user_ids):
            if user_id in self.active_connections:
                try:
                    await self.active_connections[user_id].send_json(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to admin {user_id}: {str(e)}")
                    disconnected_users.append(user_id)
        
        # Limpiar usuarios desconectados
        for user_id in disconnected_users:
            self.disconnect(user_id)
        
        logger.debug(f"Broadcast to {len(self.admin_user_ids)} admins")

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
        """
        Enviar actualización de ubicación de técnico a todos en el incidente.
        
        Args:
            incident_id: ID del incidente
            technician_id: ID del técnico
            latitude: Latitud
            longitude: Longitud
            accuracy: Precisión en metros
            speed: Velocidad en km/h
            heading: Dirección en grados
        """
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
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_incident(incident_id, message)

    async def send_incident_status_change(
        self,
        incident_id: int,
        new_status: str,
        changed_by: int = None
    ):
        """
        Notificar cambio de estado de incidente.
        
        Args:
            incident_id: ID del incidente
            new_status: Nuevo estado
            changed_by: ID del usuario que cambió el estado
        """
        message = {
            "type": "incident_status_change",
            "incident_id": incident_id,
            "new_status": new_status,
            "changed_by": changed_by,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_incident(incident_id, message)

    async def send_technician_assigned(
        self,
        incident_id: int,
        technician_id: int,
        technician_name: str,
        workshop_name: str
    ):
        """
        Notificar asignación de técnico.
        
        Args:
            incident_id: ID del incidente
            technician_id: ID del técnico
            technician_name: Nombre del técnico
            workshop_name: Nombre del taller
        """
        message = {
            "type": "technician_assigned",
            "incident_id": incident_id,
            "technician": {
                "id": technician_id,
                "name": technician_name,
                "workshop": workshop_name
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_incident(incident_id, message)

    async def send_technician_arrived(
        self,
        incident_id: int,
        technician_id: int
    ):
        """
        Notificar que el técnico llegó al lugar.
        
        Args:
            incident_id: ID del incidente
            technician_id: ID del técnico
        """
        message = {
            "type": "technician_arrived",
            "incident_id": incident_id,
            "technician_id": technician_id,
            "timestamp": datetime.utcnow().isoformat()
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
        """
        Notificar nuevo mensaje en chat.
        
        Args:
            incident_id: ID del incidente
            sender_id: ID del remitente
            sender_name: Nombre del remitente
            message_text: Texto del mensaje
            message_id: ID del mensaje (opcional)
            sender_role: Rol del remitente (opcional)
        """
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
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": None
            },
            "timestamp": datetime.utcnow().isoformat()
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
                    if user_id not in self.active_connections:
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
        return user_id in self.active_connections


# Instancia global del ConnectionManager
manager = ConnectionManager()
