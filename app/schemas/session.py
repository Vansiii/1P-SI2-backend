from datetime import datetime
from pydantic import BaseModel


class SessionResponse(BaseModel):
    """Información de una sesión activa"""
    jti: str
    device_name: str
    device_type: str
    ip_address: str | None
    location: str
    last_active: datetime
    is_current: bool

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """Lista de sesiones activas"""
    current_session: SessionResponse
    other_sessions: list[SessionResponse]
    total_sessions: int
