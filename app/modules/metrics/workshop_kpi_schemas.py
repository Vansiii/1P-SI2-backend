"""
Schemas for Workshop KPI endpoints.
"""
from typing import List
from pydantic import BaseModel


class KPIAssignmentTime(BaseModel):
    promedio_minutos: float
    total_incidentes: int


class KPIArrivalTime(BaseModel):
    promedio_minutos: float
    total_con_llegada: int


class KPIByType(BaseModel):
    tipo: str
    total: int
    porcentaje: float


class KPIEfficiencyRanking(BaseModel):
    workshop_id: int
    workshop_name: str
    total_incidentes: int
    resueltos: int
    avg_respuesta_min: float
    avg_resolucion_min: float
    tasa_resolucion_pct: float
    score_eficiencia: float


class KPIHotspot(BaseModel):
    latitud: float
    longitud: float
    total: int
    categorias: str


class KPICancelMotivo(BaseModel):
    motivo: str
    total: int


class KPICancelledAnalysis(BaseModel):
    total_cancelados: int
    total_no_atendidos: int
    tasa_cancelacion_pct: float
    motivos: List[KPICancelMotivo]


class KPISLA(BaseModel):
    total_evaluables: int
    dentro_de_sla: int
    fuera_de_sla: int
    cumplimiento_sla_pct: float
    tiempo_promedio_real_min: float
    tiempo_esperado_promedio_min: float
    brecha_min: float


class PeriodRange(BaseModel):
    desde: str
    hasta: str


class WorkshopKPIDashboard(BaseModel):
    workshop_id: int
    periodo: PeriodRange
    kpi_asignacion: KPIAssignmentTime
    kpi_llegada: KPIArrivalTime
    kpi_tipos: List[KPIByType]
    kpi_cancelados: KPICancelledAnalysis
    kpi_sla: KPISLA
    kpi_zonas: List[KPIHotspot]
