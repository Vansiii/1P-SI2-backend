"""
Schemas para endpoints administrativos de incidentes.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class WorkshopInfo(BaseModel):
    """Información básica de un taller."""
    id: int
    workshop_name: str
    workshop_phone: Optional[str]
    address: Optional[str]


class AssignmentAttemptInfo(BaseModel):
    """Información de un intento de asignación."""
    id: int
    workshop_id: int
    workshop_name: str
    attempted_at: datetime
    response_status: str  # 'accepted', 'rejected', 'no_response', 'timeout'
    rejection_reason: Optional[str]
    responded_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class RejectionInfo(BaseModel):
    """Información de un rechazo de taller."""
    id: int
    taller_id: int
    workshop_name: str
    motivo: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class StateHistoryInfo(BaseModel):
    """Información del historial de estados."""
    id: int
    estado_nombre: str
    estado_descripcion: Optional[str]
    changed_by_user_name: Optional[str]
    comentario: Optional[str]
    fecha: datetime
    
    class Config:
        from_attributes = True


class ClientInfo(BaseModel):
    """Información del cliente."""
    id: int
    first_name: str
    last_name: str
    email: str
    phone: str


class VehicleInfo(BaseModel):
    """Información del vehículo."""
    id: int
    marca: Optional[str]
    modelo: str
    anio: int
    matricula: str
    color: Optional[str]


class IncidentDetailAdminResponse(BaseModel):
    """Respuesta con detalles completos del incidente para admin."""
    
    # Información del incidente
    id: int
    estado_actual: str
    descripcion: str
    latitude: float
    longitude: float
    direccion_referencia: Optional[str]
    categoria_ia: Optional[str]
    prioridad_ia: Optional[str]
    resumen_ia: Optional[str]
    es_ambiguo: bool
    created_at: datetime
    updated_at: datetime
    assigned_at: Optional[datetime]
    resolved_at: Optional[datetime]
    
    # Información del cliente
    client: ClientInfo
    
    # Información del vehículo
    vehiculo: VehicleInfo
    
    # Taller asignado actualmente (si existe)
    current_workshop: Optional[WorkshopInfo]
    
    # Historial de intentos de asignación
    assignment_attempts: List[AssignmentAttemptInfo]
    
    # Rechazos de talleres
    rejections: List[RejectionInfo]
    
    # Historial de estados
    state_history: List[StateHistoryInfo]
    
    # Estadísticas
    total_attempts: int
    total_rejections: int
    total_no_responses: int
    
    class Config:
        from_attributes = True
