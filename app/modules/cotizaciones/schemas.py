from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ServicioCotizadoItem(BaseModel):
    servicio_id: int
    nombre: str
    precio: Decimal
    tiempo_minutos: int


class SolicitarCotizacionRequest(BaseModel):
    vehiculo_id: int
    latitud: float
    longitud: float
    direccion_referencia: str | None = None
    descripcion_dano: str = Field(min_length=10, max_length=2000)
    imagenes_dano: list[str] = Field(default_factory=list)
    audio_diagnostico: str | None = None
    radio_busqueda_km: float = Field(default=15.0, ge=1, le=200)


class ResponderCotizacionRequest(BaseModel):
    servicios: list[ServicioCotizadoItem] = Field(min_length=1)
    costo_total: Decimal = Field(gt=0)
    tiempo_estimado_minutos: int = Field(gt=0)
    tiempo_estimado_texto: str = Field(min_length=1, max_length=200)
    notas: str | None = Field(default=None, max_length=1000)
    validez_horas: int = Field(default=48, ge=1, le=720)


class SeleccionarTallerRequest(BaseModel):
    cotizacion_respuesta_id: int


class IniciarPagoCotizacionRequest(BaseModel):
    cotizacion_id: int


class CotizacionRespuestaResponse(BaseModel):
    id: int
    workshop_id: int
    workshop_name: str = ""
    servicios: list[dict] | None = None
    costo_total: Decimal
    tiempo_estimado_minutos: int
    tiempo_estimado_texto: str
    notas: str | None = None
    valida_hasta: datetime | None = None
    estado: str
    created_at: datetime | None = None


class CotizacionResponse(BaseModel):
    id: int
    tenant_id: int | None = None
    client_id: int
    vehiculo_id: int
    workshop_id: int | None = None
    latitud: float
    longitud: float
    direccion_referencia: str | None = None
    descripcion_dano: str
    imagenes_dano: list[str] | None = None
    audio_diagnostico: str | None = None
    categoria_ia: str | None = None
    prioridad_ia: str | None = None
    resumen_ia: str | None = None
    es_ambiguo: bool = False
    servicios_cotizados: dict | None = None
    costo_total_estimado: Decimal | None = None
    tiempo_total_estimado_minutos: int | None = None
    notas_cotizacion: str | None = None
    estado: str
    stripe_payment_intent_id: str | None = None
    monto_pagado: Decimal | None = None
    respuestas: list[CotizacionRespuestaResponse] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CotizacionListItem(BaseModel):
    id: int
    vehiculo_id: int
    vehiculo_matricula: str = ""
    vehiculo_marca: str = ""
    vehiculo_modelo: str = ""
    descripcion_dano: str
    categoria_ia: str | None = None
    prioridad_ia: str | None = None
    estado: str
    costo_total_estimado: Decimal | None = None
    taller_nombre: str | None = None
    respuestas_count: int = 0
    created_at: datetime | None = None


class PagoCotizacionResponse(BaseModel):
    cotizacion_id: int
    client_secret: str
    stripe_payment_intent_id: str
    amount: float
    publishable_key: str
