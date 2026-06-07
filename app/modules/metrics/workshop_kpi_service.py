"""
Workshop KPI Service — métricas avanzadas para el dashboard de taller.

KPIs implementados:
1. Tiempo promedio de asignación (created_at → assigned_at)
2. Tiempo promedio de llegada (assigned_at → arrived_at)
3. Incidentes por tipo (categoria_ia)
4. Ranking de talleres más eficientes (tasa resolución + tiempo respuesta)
5. Zonas con más incidentes (agrupación geográfica)
6. Análisis de casos cancelados (motivos, tendencias)
7. Cumplimiento SLA (tiempo real vs tiempo estimado del servicio)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text

from ...core.logging import get_logger
from ...models.incidente import Incidente
from ...models.workshop import Workshop
from ...models.rechazo_taller import RechazoTaller
from ...models.servicio_taller import ServicioTaller

logger = get_logger(__name__)


class WorkshopKPIService:
    """Servicio para KPIs avanzados del taller."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _dates(self, start_date: Optional[datetime], end_date: Optional[datetime]):
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)
        if start_date.tzinfo is not None:
            start_date = start_date.astimezone(timezone.utc).replace(tzinfo=None)
        if end_date.tzinfo is not None:
            end_date = end_date.astimezone(timezone.utc).replace(tzinfo=None)
        return start_date, end_date

    def _minutes_between(self, later_col, earlier_col):
        return func.extract('epoch', later_col - earlier_col) / 60

    # ------------------------------------------------------------------ #
    # KPI 1: Tiempo promedio de asignación
    # ------------------------------------------------------------------ #
    async def get_avg_assignment_time(
        self, workshop_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
        start_date, end_date = self._dates(start_date, end_date)
        total = await self.session.scalar(
            select(func.count(Incidente.id)).where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.assigned_at.isnot(None),
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date,
                )
            )
        ) or 0
        avg_min = await self.session.scalar(
            select(func.avg(self._minutes_between(Incidente.assigned_at, Incidente.created_at))).where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.assigned_at.isnot(None),
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date,
                )
            )
        )
        return {
            "promedio_minutos": round(float(avg_min), 2) if avg_min else 0.0,
            "total_incidentes": total,
        }

    # ------------------------------------------------------------------ #
    # KPI 2: Tiempo promedio de llegada
    # ------------------------------------------------------------------ #
    async def get_avg_arrival_time(
        self, workshop_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
        start_date, end_date = self._dates(start_date, end_date)
        total = await self.session.scalar(
            select(func.count(Incidente.id)).where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.arrived_at.isnot(None),
                    Incidente.assigned_at.isnot(None),
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date,
                )
            )
        ) or 0
        avg_min = await self.session.scalar(
            select(func.avg(self._minutes_between(Incidente.arrived_at, Incidente.assigned_at))).where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.arrived_at.isnot(None),
                    Incidente.assigned_at.isnot(None),
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date,
                )
            )
        )
        return {
            "promedio_minutos": round(float(avg_min), 2) if avg_min else 0.0,
            "total_con_llegada": total,
        }

    # ------------------------------------------------------------------ #
    # KPI 3: Incidentes por tipo
    # ------------------------------------------------------------------ #
    async def get_incidents_by_type(
        self, workshop_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict]:
        start_date, end_date = self._dates(start_date, end_date)
        result = await self.session.execute(
            select(
                func.coalesce(Incidente.categoria_ia, 'sin_clasificar').label('tipo'),
                func.count(Incidente.id).label('total'),
            )
            .where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date,
                )
            )
            .group_by(text('1'))
            .order_by(text('total DESC'))
        )
        grand_total = sum(r.total for r in result.all()) or 1
        return [
            {
                "tipo": row.tipo,
                "total": row.total,
                "porcentaje": round(row.total / grand_total * 100, 1),
            }
            for row in result.all()
        ]

    # ------------------------------------------------------------------ #
    # KPI 4: Ranking de talleres más eficientes
    # ------------------------------------------------------------------ #
    async def get_efficiency_ranking(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> List[Dict]:
        start_date, end_date = self._dates(start_date, end_date)
        result = await self.session.execute(
            select(
                Workshop.id.label('workshop_id'),
                Workshop.workshop_name,
                func.count(Incidente.id).label('total_incidentes'),
                func.sum(
                    func.case((Incidente.estado_actual == 'resuelto', 1), else_=0)
                ).label('resueltos'),
                func.round(
                    func.avg(
                        func.case(
                            (Incidente.assigned_at.isnot(None), self._minutes_between(Incidente.assigned_at, Incidente.created_at)),
                            else_=None,
                        )
                    ).cast(func.Numeric), 2
                ).label('avg_respuesta_min'),
                func.round(
                    func.avg(
                        func.case(
                            (Incidente.resolved_at.isnot(None), self._minutes_between(Incidente.resolved_at, Incidente.assigned_at)),
                            else_=None,
                        )
                    ).cast(func.Numeric), 2
                ).label('avg_resolucion_min'),
            )
            .select_from(Workshop)
            .outerjoin(Incidente, and_(
                Incidente.taller_id == Workshop.id,
                Incidente.created_at >= start_date,
                Incidente.created_at <= end_date,
            ))
            .group_by(Workshop.id, Workshop.workshop_name)
            .having(func.count(Incidente.id) > 0)
            .order_by(text('resueltos DESC'), text('avg_respuesta_min ASC NULLS LAST'))
            .limit(limit)
        )
        return [
            {
                "workshop_id": row.workshop_id,
                "workshop_name": row.workshop_name,
                "total_incidentes": row.total_incidentes or 0,
                "resueltos": row.resueltos or 0,
                "avg_respuesta_min": float(row.avg_respuesta_min) if row.avg_respuesta_min else 0.0,
                "avg_resolucion_min": float(row.avg_resolucion_min) if row.avg_resolucion_min else 0.0,
                "tasa_resolucion_pct": round((row.resueltos or 0) / (row.total_incidentes or 1) * 100, 1),
                "score_eficiencia": round(
                    ((row.resueltos or 0) / (row.total_incidentes or 1) * 50)
                    + (1.0 / (1.0 + max(float(row.avg_respuesta_min or 60), 1) / 60.0) * 50),
                    1,
                ),
            }
            for row in result.all()
        ]

    # ------------------------------------------------------------------ #
    # KPI 5: Zonas con más incidentes (hotspots)
    # ------------------------------------------------------------------ #
    async def get_hotspots(
        self,
        workshop_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 20,
    ) -> List[Dict]:
        start_date, end_date = self._dates(start_date, end_date)
        conditions = [
            Incidente.latitude.isnot(None),
            Incidente.longitude.isnot(None),
            Incidente.created_at >= start_date,
            Incidente.created_at <= end_date,
        ]
        if workshop_id is not None:
            conditions.append(Incidente.taller_id == workshop_id)
        result = await self.session.execute(
            select(
                func.round(Incidente.latitude.cast(func.Numeric), 3).label('lat'),
                func.round(Incidente.longitude.cast(func.Numeric), 3).label('lng'),
                func.count(Incidente.id).label('total'),
                func.string_agg(
                    func.distinct(func.coalesce(Incidente.categoria_ia, 'sin_clasificar')),
                    ', ',
                ).label('categorias'),
            )
            .where(and_(*conditions))
            .group_by(text('1'), text('2'))
            .order_by(text('total DESC'))
            .limit(limit)
        )
        return [
            {
                "latitud": float(row.lat),
                "longitud": float(row.lng),
                "total": row.total,
                "categorias": row.categorias or '',
            }
            for row in result.all()
        ]

    # ------------------------------------------------------------------ #
    # KPI 6: Análisis de casos cancelados
    # ------------------------------------------------------------------ #
    async def get_cancelled_analysis(
        self, workshop_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
        start_date, end_date = self._dates(start_date, end_date)

        total_incidentes = await self.session.scalar(
            select(func.count(Incidente.id)).where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date,
                )
            )
        ) or 1

        total_cancelados = await self.session.scalar(
            select(func.count(Incidente.id)).where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.estado_actual == 'cancelado',
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date,
                )
            )
        ) or 0

        total_no_atendidos = await self.session.scalar(
            select(func.count(Incidente.id)).where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.estado_actual == 'sin_taller_disponible',
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date,
                )
            )
        ) or 0

        motivos_result = await self.session.execute(
            select(
                func.coalesce(RechazoTaller.motivo, 'No especificado').label('motivo'),
                func.count(RechazoTaller.id).label('total'),
            )
            .join(Incidente, Incidente.id == RechazoTaller.incidente_id)
            .where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.estado_actual == 'cancelado',
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date,
                )
            )
            .group_by(text('1'))
            .order_by(text('total DESC'))
        )
        motivos = [
            {"motivo": row.motivo, "total": row.total}
            for row in motivos_result.all()
        ]

        return {
            "total_cancelados": total_cancelados,
            "total_no_atendidos": total_no_atendidos,
            "tasa_cancelacion_pct": round(total_cancelados / total_incidentes * 100, 1),
            "motivos": motivos,
        }

    # ------------------------------------------------------------------ #
    # KPI 7: Cumplimiento SLA
    # ------------------------------------------------------------------ #
    async def get_sla_compliance(
        self, workshop_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
        start_date, end_date = self._dates(start_date, end_date)

        tiempo_esperado_result = await self.session.scalar(
            select(func.round(func.avg(ServicioTaller.tiempo_estimado).cast(func.Numeric), 2))
            .where(
                and_(
                    ServicioTaller.taller_id == workshop_id,
                    ServicioTaller.is_active.is_(True),
                )
            )
        )
        tiempo_esperado = float(tiempo_esperado_result) if tiempo_esperado_result else 60.0

        resolucion_stats = await self.session.execute(
            select(
                func.count(Incidente.id).label('total_evaluables'),
                func.sum(
                    func.case((
                        and_(
                            Incidente.resolved_at.isnot(None),
                            Incidente.assigned_at.isnot(None),
                            self._minutes_between(Incidente.resolved_at, Incidente.assigned_at) <= tiempo_esperado,
                        ), 1,
                    ), else_=0)
                ).label('dentro_de_sla'),
                func.round(
                    func.avg(
                        func.case(
                            (and_(Incidente.resolved_at.isnot(None), Incidente.assigned_at.isnot(None)),
                             self._minutes_between(Incidente.resolved_at, Incidente.assigned_at)),
                            else_=None,
                        )
                    ).cast(func.Numeric), 2
                ).label('avg_tiempo_real_min'),
            )
            .where(
                and_(
                    Incidente.taller_id == workshop_id,
                    Incidente.estado_actual == 'resuelto',
                    Incidente.resolved_at.isnot(None),
                    Incidente.assigned_at.isnot(None),
                    Incidente.created_at >= start_date,
                    Incidente.created_at <= end_date,
                )
            )
        ).one()

        total_evaluables = int(resolucion_stats.total_evaluables or 0)
        dentro_sla = int(resolucion_stats.dentro_de_sla or 0)
        avg_real = float(resolucion_stats.avg_tiempo_real_min) if resolucion_stats.avg_tiempo_real_min else 0.0

        return {
            "total_evaluables": total_evaluables,
            "dentro_de_sla": dentro_sla,
            "fuera_de_sla": total_evaluables - dentro_sla,
            "cumplimiento_sla_pct": round(dentro_sla / total_evaluables * 100, 1) if total_evaluables > 0 else 0.0,
            "tiempo_promedio_real_min": round(avg_real, 2),
            "tiempo_esperado_promedio_min": tiempo_esperado,
            "brecha_min": round(avg_real - tiempo_esperado, 2),
        }

    # ------------------------------------------------------------------ #
    # Dashboard unificado (todos los KPIs en una llamada)
    # ------------------------------------------------------------------ #
    async def get_dashboard(
        self, workshop_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict:
        return {
            "workshop_id": workshop_id,
            "periodo": {
                "desde": (start_date or datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
                "hasta": (end_date or datetime.now(timezone.utc)).isoformat(),
            },
            "kpi_asignacion": await self.get_avg_assignment_time(workshop_id, start_date, end_date),
            "kpi_llegada": await self.get_avg_arrival_time(workshop_id, start_date, end_date),
            "kpi_tipos": await self.get_incidents_by_type(workshop_id, start_date, end_date),
            "kpi_cancelados": await self.get_cancelled_analysis(workshop_id, start_date, end_date),
            "kpi_sla": await self.get_sla_compliance(workshop_id, start_date, end_date),
            "kpi_zonas": await self.get_hotspots(workshop_id=workshop_id, start_date=start_date, end_date=end_date),
        }
