"""
Schemas for client reports endpoints.
"""
from typing import Optional, List
from pydantic import BaseModel


class ClientReportSummary(BaseModel):
    total_incidentes: int
    total_gastado: float
    total_vehiculos: int
    incidentes_activos: int
    rating_promedio: Optional[float] = None


class SpendingByMonth(BaseModel):
    mes: str
    total: float
    cantidad: int


class ClientSpendingReport(BaseModel):
    total_gastado: float
    total_transacciones: int
    por_mes: List[SpendingByMonth]


class VehicleServiceEntry(BaseModel):
    incidente_id: int
    fecha: str
    categoria: Optional[str]
    estado: str
    costo: Optional[float]
    taller_nombre: Optional[str]


class VehicleHistoryReport(BaseModel):
    vehiculo_id: int
    matricula: str
    total_servicios: int
    servicios: List[VehicleServiceEntry]
