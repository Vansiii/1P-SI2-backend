"""
Notification Filter - Sistema de filtrado inteligente de notificaciones.

Este módulo determina:
1. Qué usuarios deben recibir notificaciones
2. Qué modo de entrega usar (hybrid, websocket_only, silent)
3. Filtrado por perfil de usuario y relevancia

Objetivo: Reducir spam y enviar solo notificaciones relevantes y profesionales.
"""

from typing import Set, Optional
from enum import Enum


class DeliveryMode(str, Enum):
    """Modos de entrega de notificaciones."""
    HYBRID = "hybrid"  # WebSocket + Push (crítico)
    WEBSOCKET_ONLY = "websocket_only"  # Solo WebSocket (informativo)
    PUSH_ONLY = "push_only"  # Solo Push (offline)
    SILENT = "silent"  # No notificar (solo logs)


class NotificationFilter:
    """
    Filtro inteligente de notificaciones.
    
    Determina qué usuarios deben recibir notificaciones y cómo.
    """
    
    # Eventos CRÍTICOS que siempre generan notificación push
    CRITICAL_EVENTS = {
        "incident.created",
        "incident.assigned",
        "incident.technician_arrived",
        "incident.work_completed",
        "incident.cancelled",
        "incident.no_workshop_available",
        "incident.assignment_timeout",
        "chat.message_sent",
    }
    
    # Eventos INFORMATIVOS (solo WebSocket, no push)
    INFORMATIVE_EVENTS = {
        "incident.status_changed",
        "incident.updated",  # Actualizaciones de campos del incidente (ej: IA)
        "incident.searching_workshop",
        "incident.technician_on_way",
        "incident.work_started",
        "incident.assignment_accepted",
        "incident.assignment_rejected",
        "incident.reassignment_started",
        "tracking.started",
        "tracking.ended",
    }
    
    # Eventos TÉCNICOS (solo para admins)
    TECHNICAL_EVENTS = {
        "incident.ai_analysis_started",
        "incident.ai_analysis_completed",
        "incident.ai_analysis_failed",
        "incident.evidence_uploaded",
        "incident.evidence_image_uploaded",
        "incident.evidence_audio_uploaded",
        "incident.evidence_text_added",
        "incident.photos_uploaded",
        "dashboard.metrics_updated",
        "audit.action_logged",
    }
    
    # Eventos SILENCIOSOS (no notificar a nadie, solo logs)
    SILENT_EVENTS = {
        "tracking.location_updated",
        "tracking.updated",
        "chat.message_delivered",
        "chat.message_read",
        "chat.user_typing",
        "chat.user_stopped_typing",
        "chat.file_uploaded",  # Ya se notifica con message_sent
    }
    
    @staticmethod
    def should_notify_user(
        event_type: str,
        user_type: str,
        user_id: int,
        event_data: dict,
        incident_participants: dict
    ) -> bool:
        """
        Determina si un usuario específico debe recibir notificación.
        
        Args:
            event_type: Tipo de evento
            user_type: Tipo de usuario (client, workshop, technician, administrator)
            user_id: ID del usuario
            event_data: Datos del evento
            incident_participants: Dict con client_id, workshop_id, technician_id
            
        Returns:
            True si el usuario debe recibir notificación
        """
        # Eventos silenciosos no notifican a nadie
        if event_type in NotificationFilter.SILENT_EVENTS:
            return False
        
        # Eventos técnicos solo para administradores
        if event_type in NotificationFilter.TECHNICAL_EVENTS:
            return user_type == "administrator"
        
        # Dashboard events solo para administradores
        if event_type.startswith("dashboard."):
            return user_type == "administrator"
        
        # Audit events solo para administradores
        if event_type.startswith("audit."):
            return user_type == "administrator"
        
        # Chat messages: solo para participantes de la conversación
        if event_type == "chat.message_sent":
            sender_id = event_data.get("sender_id")
            # No notificar al remitente (ya recibió via WebSocket inmediato)
            if sender_id == user_id:
                return False
            # Notificar si es participante del incidente (excluir None)
            participants = [
                incident_participants.get("client_id"),
                incident_participants.get("workshop_id"),
                incident_participants.get("technician_id")
            ]
            # Filter out None values before checking
            valid_participants = [p for p in participants if p is not None]
            return user_id in valid_participants
        
        # Filtrado por tipo de usuario
        if user_type == "client":
            return NotificationFilter._should_notify_client(
                event_type, user_id, incident_participants
            )
        elif user_type == "workshop":
            return NotificationFilter._should_notify_workshop(
                event_type, user_id, incident_participants
            )
        elif user_type == "technician":
            return NotificationFilter._should_notify_technician(
                event_type, user_id, incident_participants
            )
        elif user_type == "administrator":
            return NotificationFilter._should_notify_admin(event_type)
        
        # Por defecto, no notificar
        return False
    
    @staticmethod
    def _should_notify_client(
        event_type: str,
        user_id: int,
        incident_participants: dict
    ) -> bool:
        """Determina si notificar a un cliente."""
        # Solo notificar si es SU incidente
        if incident_participants.get("client_id") != user_id:
            return False
        
        # Eventos relevantes para clientes
        client_events = {
            "incident.created",
            "incident.assigned",
            "incident.updated",  # Actualizaciones de campos (ej: análisis IA)
            "incident.technician_on_way",
            "incident.technician_arrived",
            "incident.work_started",
            "incident.work_completed",
            "incident.cancelled",
            "incident.no_workshop_available",
            "incident.searching_workshop",
            "incident.reassignment_started",
            "incident.assignment_timeout",
        }
        
        return event_type in client_events
    
    @staticmethod
    def _should_notify_workshop(
        event_type: str,
        user_id: int,
        incident_participants: dict
    ) -> bool:
        """Determina si notificar a un taller."""
        # Solo notificar si es SU incidente asignado
        if incident_participants.get("workshop_id") != user_id:
            return False
        
        # Eventos relevantes para talleres
        workshop_events = {
            "incident.assigned",
            "incident.assignment_timeout",
            "incident.cancelled",
            "incident.work_completed",
            "incident.technician_arrived",  # Informativo
            "incident.work_started",  # Informativo
        }
        
        return event_type in workshop_events
    
    @staticmethod
    def _should_notify_technician(
        event_type: str,
        user_id: int,
        incident_participants: dict
    ) -> bool:
        """Determina si notificar a un técnico."""
        # Solo notificar si es SU servicio asignado
        if incident_participants.get("technician_id") != user_id:
            return False
        
        # Eventos relevantes para técnicos
        technician_events = {
            "incident.technician_assigned",  # Cuando se le asigna
            "incident.cancelled",
            "incident.work_completed",  # Confirmación
        }
        
        return event_type in technician_events
    
    @staticmethod
    def _should_notify_admin(event_type: str) -> bool:
        """Determina si notificar a un administrador."""
        # Admins reciben eventos críticos del sistema
        admin_events = {
            "incident.no_workshop_available",
            "incident.assignment_timeout",
            "dashboard.critical_alert",
            "audit.security_event",
        }
        
        # También eventos técnicos (ya filtrados arriba)
        return event_type in admin_events or event_type in NotificationFilter.TECHNICAL_EVENTS
    
    @staticmethod
    def get_delivery_mode(event_type: str, user_type: str) -> DeliveryMode:
        """
        Determina el modo de entrega para un evento y tipo de usuario.
        
        Args:
            event_type: Tipo de evento
            user_type: Tipo de usuario
            
        Returns:
            DeliveryMode (hybrid, websocket_only, push_only, silent)
        """
        # Eventos silenciosos
        if event_type in NotificationFilter.SILENT_EVENTS:
            return DeliveryMode.SILENT
        
        # Eventos críticos → HYBRID (WebSocket + Push)
        if event_type in NotificationFilter.CRITICAL_EVENTS:
            return DeliveryMode.HYBRID
        
        # Eventos informativos → WEBSOCKET_ONLY
        if event_type in NotificationFilter.INFORMATIVE_EVENTS:
            return DeliveryMode.WEBSOCKET_ONLY
        
        # Eventos técnicos para admins → WEBSOCKET_ONLY
        if event_type in NotificationFilter.TECHNICAL_EVENTS:
            if user_type == "administrator":
                return DeliveryMode.WEBSOCKET_ONLY
            else:
                return DeliveryMode.SILENT
        
        # Dashboard events → WEBSOCKET_ONLY para admins
        if event_type.startswith("dashboard."):
            if user_type == "administrator":
                return DeliveryMode.WEBSOCKET_ONLY
            else:
                return DeliveryMode.SILENT
        
        # Por defecto: WEBSOCKET_ONLY (conservador)
        return DeliveryMode.WEBSOCKET_ONLY
    
    @staticmethod
    def get_filtered_recipients(
        event_type: str,
        candidate_recipients: Set[int],
        users_data: dict,  # {user_id: {"user_type": str, ...}}
        incident_participants: dict  # {"client_id": int, "workshop_id": int, "technician_id": int}
    ) -> Set[int]:
        """
        Filtra los destinatarios candidatos según reglas de negocio.
        
        Args:
            event_type: Tipo de evento
            candidate_recipients: Set de user_ids candidatos
            users_data: Diccionario con datos de usuarios {user_id: {"user_type": str}}
            incident_participants: Participantes del incidente
            
        Returns:
            Set de user_ids que deben recibir la notificación
        """
        filtered_recipients = set()
        
        for user_id in candidate_recipients:
            user_info = users_data.get(user_id, {})
            user_type = user_info.get("user_type", "unknown")
            
            # Aplicar filtro
            if NotificationFilter.should_notify_user(
                event_type=event_type,
                user_type=user_type,
                user_id=user_id,
                event_data={},  # Se puede pasar event_data si es necesario
                incident_participants=incident_participants
            ):
                filtered_recipients.add(user_id)
        
        return filtered_recipients
    
    @staticmethod
    def is_critical_for_user(event_type: str, user_type: str) -> bool:
        """
        Determina si un evento es crítico para un tipo de usuario.
        
        Usado para decidir si enviar push notification.
        
        Args:
            event_type: Tipo de evento
            user_type: Tipo de usuario
            
        Returns:
            True si es crítico y debe enviar push
        """
        # Eventos críticos generales
        if event_type in NotificationFilter.CRITICAL_EVENTS:
            return True
        
        # Eventos críticos específicos por tipo de usuario
        if user_type == "client":
            return event_type in {
                "incident.created",
                "incident.assigned",
                "incident.technician_arrived",
                "incident.work_completed",
                "incident.no_workshop_available",
            }
        elif user_type == "workshop":
            return event_type in {
                "incident.assigned",
                "incident.assignment_timeout",
                "incident.cancelled",
            }
        elif user_type == "technician":
            return event_type in {
                "incident.technician_assigned",
                "incident.cancelled",
            }
        elif user_type == "administrator":
            return event_type in {
                "incident.no_workshop_available",
                "dashboard.critical_alert",
            }
        
        return False
