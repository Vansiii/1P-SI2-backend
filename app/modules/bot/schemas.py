from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List, Any


class BotMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, description="Contenido de la pregunta del usuario")
    latitude: Optional[float] = Field(default=None, description="Latitud actual del dispositivo (para buscar talleres cercanos)")
    longitude: Optional[float] = Field(default=None, description="Longitud actual del dispositivo (para buscar talleres cercanos)")


class BotMessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: datetime
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    response_time_ms: Optional[int] = None
    tool_calls: Optional[Any] = None

    class Config:
        from_attributes = True


class BotConversationCreate(BaseModel):
    first_message: str = Field(..., min_length=1, description="Primer mensaje para iniciar la conversación")
    vehicle_id: Optional[int] = Field(default=None, description="Vehículo de contexto (opcional)")
    latitude: Optional[float] = Field(default=None, description="Latitud actual del dispositivo (para buscar talleres cercanos)")
    longitude: Optional[float] = Field(default=None, description="Longitud actual del dispositivo (para buscar talleres cercanos)")


class BotConversationResponse(BaseModel):
    id: int
    user_id: int
    title: str
    vehicle_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    messages: Optional[List[BotMessageResponse]] = None

    class Config:
        from_attributes = True


class BotSuggestionResponse(BaseModel):
    id: str
    text: str
