"""
Modelos de base de datos del sistema.
Usa herencia de tabla (Table Per Type) para diferentes tipos de usuarios.
"""

# Modelos de autenticación y usuarios
from .administrator import Administrator
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

# Modelos de negocio (gestión de emergencias vehiculares)
from .categoria import Categoria
from .configuracion import Configuracion
from .especialidad import Especialidad
from .estados_servicio import EstadosServicio
from .evidencia import Evidencia
from .evidencia_audio import EvidenciaAudio
from .evidencia_imagen import EvidenciaImagen
from .historial_servicio import HistorialServicio
from .incidente import Incidente
from .servicio import Servicio
from .servicio_taller import ServicioTaller
from .technician_especialidad import TechnicianEspecialidad
from .vehiculo import Vehiculo

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
    "Evidencia",
    "EvidenciaImagen",
    "EvidenciaAudio",
    "Servicio",
    "Categoria",
    "ServicioTaller",
    "EstadosServicio",
    "HistorialServicio",
    "Configuracion",
    "Especialidad",
    "TechnicianEspecialidad",
]

