"""
Modelos de base de datos del sistema.
Usa herencia de tabla (Table Per Type) para diferentes tipos de usuarios.
"""

# Modelos de autenticación y usuarios
from .administrator import Administrator
from .assignment_attempt import AssignmentAttempt
from .audit_log import AuditLog
from .base import Base
from .client import Client
from .login_attempt import LoginAttempt
from .password_reset_token import PasswordResetToken
from .refresh_token import RefreshToken
from .revoked_token import RevokedToken
from .technician import Technician
from .two_factor_auth import TwoFactorAuth
from .user import User
from .workshop import Workshop
from .workshop_schedule import WorkshopSchedule

# Modelos de eventos (Outbox Pattern)
from .outbox_event import OutboxEvent, EventPriority
from .event_log import EventLog

# Modelos de negocio (gestión de emergencias vehiculares)
from .cancellation_request import CancellationRequest
from .categoria import Categoria
from .configuracion import Configuracion
from .conversation import Conversation
from .especialidad import Especialidad
from .estados_servicio import EstadosServicio
from .evidencia import Evidencia
from .evidencia_audio import EvidenciaAudio
from .evidencia_imagen import EvidenciaImagen
from .historial_servicio import HistorialServicio
from .incidente import Incidente
from .incident_ai_analysis import IncidentAIAnalysis
from .message import Message
from .notification import Notification
from .push_token import PushToken
from .rechazo_taller import RechazoTaller
from .servicio import Servicio
from .servicio_taller import ServicioTaller
from .technician_especialidad import TechnicianEspecialidad
from .technician_location_history import TechnicianLocationHistory
from .tracking_session import TrackingSession
from .vehiculo import Vehiculo

# Modelos financieros (Módulo 6: Pagos y Comisiones)
from .transaction import Transaction
from .workshop_balance import WorkshopBalance, Withdrawal
from .financial_movement import WorkshopFinancialMovement
from .workshop_settlement import WorkshopSettlement
from .platform_commission import PlatformCommission
from .stripe_event_log import StripeEventLog

__all__ = [
    # Base
    "Base",
    # Usuarios y autenticación
    "User",
    "Client",
    "Workshop",
    "WorkshopSchedule",
    "Technician",
    "Administrator",
    "RefreshToken",
    "RevokedToken",
    "PasswordResetToken",
    "LoginAttempt",
    "AuditLog",
    "TwoFactorAuth",
    # Negocio
    "Vehiculo",
    "Incidente",
    "IncidentAIAnalysis",
    "Evidencia",
    "EvidenciaImagen",
    "EvidenciaAudio",
    "Servicio",
    "Categoria",
    "ServicioTaller",
    "EstadosServicio",
    "HistorialServicio",
    "RechazoTaller",
    "Configuracion",
    "Especialidad",
    "TechnicianEspecialidad",
    # Tiempo real y notificaciones
    "TechnicianLocationHistory",
    "TrackingSession",
    "Notification",
    "PushToken",
    # Chat
    "Message",
    "Conversation",
    "CancellationRequest",
    # Asignación inteligente
    "AssignmentAttempt",
    # Eventos (Outbox Pattern)
    "OutboxEvent",
    "EventLog",
    "EventPriority",
    # Financiero (Módulo 6: Pagos y Comisiones)
    "Transaction",
    "WorkshopBalance",
    "Withdrawal",
    "WorkshopFinancialMovement",
    "WorkshopSettlement",
    "PlatformCommission",
    "StripeEventLog",
]

