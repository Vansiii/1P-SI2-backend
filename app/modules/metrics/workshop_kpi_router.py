"""
Workshop KPI Router — endpoints para métricas avanzadas del taller.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.responses import success_response
from ...shared.dependencies.auth import get_current_user
from .workshop_kpi_service import WorkshopKPIService

router = APIRouter(prefix="/stats/workshop", tags=["Workshop KPIs"])

ADMIN_TYPES = ("admin", "administrator")


def _normalize_dates(start_date: Optional[datetime], end_date: Optional[datetime]):
    if start_date and start_date.tzinfo is not None:
        start_date = start_date.astimezone(timezone.utc).replace(tzinfo=None)
    if end_date:
        if end_date.tzinfo is not None:
            end_date = end_date.astimezone(timezone.utc).replace(tzinfo=None)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start_date, end_date


async def _resolve_workshop_id(
    workshop_id: int,
    current_user,
) -> int:
    if hasattr(current_user, 'user_type') and current_user.user_type in ADMIN_TYPES:
        return workshop_id
    if hasattr(current_user, 'id'):
        if current_user.id != workshop_id:
            raise HTTPException(403, "Solo puedes consultar las metricas de tu propio taller")
        return current_user.id
    raise HTTPException(403, "No autorizado")


# ------------------------------------------------------------------ #
# Endpoints individuales por KPI
# ------------------------------------------------------------------ #

@router.get("/{workshop_id}/kpis/assignment-time")
async def get_assignment_time(
    workshop_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """KPI 1: Tiempo promedio de asignación."""
    wid = await _resolve_workshop_id(workshop_id, current_user)
    start_date, end_date = _normalize_dates(start_date, end_date)
    svc = WorkshopKPIService(db)
    data = await svc.get_avg_assignment_time(wid, start_date, end_date)
    return success_response(data=data, message="Tiempo promedio de asignación")


@router.get("/{workshop_id}/kpis/arrival-time")
async def get_arrival_time(
    workshop_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """KPI 2: Tiempo promedio de llegada."""
    wid = await _resolve_workshop_id(workshop_id, current_user)
    start_date, end_date = _normalize_dates(start_date, end_date)
    svc = WorkshopKPIService(db)
    data = await svc.get_avg_arrival_time(wid, start_date, end_date)
    return success_response(data=data, message="Tiempo promedio de llegada")


@router.get("/{workshop_id}/kpis/by-type")
async def get_by_type(
    workshop_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """KPI 3: Incidentes por tipo."""
    wid = await _resolve_workshop_id(workshop_id, current_user)
    start_date, end_date = _normalize_dates(start_date, end_date)
    svc = WorkshopKPIService(db)
    data = await svc.get_incidents_by_type(wid, start_date, end_date)
    return success_response(data=data, message="Incidentes por tipo")


@router.get("/{workshop_id}/kpis/cancelled")
async def get_cancelled(
    workshop_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """KPI 6: Análisis de casos cancelados."""
    wid = await _resolve_workshop_id(workshop_id, current_user)
    start_date, end_date = _normalize_dates(start_date, end_date)
    svc = WorkshopKPIService(db)
    data = await svc.get_cancelled_analysis(wid, start_date, end_date)
    return success_response(data=data, message="Análisis de cancelados")


@router.get("/{workshop_id}/kpis/sla")
async def get_sla(
    workshop_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """KPI 7: Cumplimiento SLA."""
    wid = await _resolve_workshop_id(workshop_id, current_user)
    start_date, end_date = _normalize_dates(start_date, end_date)
    svc = WorkshopKPIService(db)
    data = await svc.get_sla_compliance(wid, start_date, end_date)
    return success_response(data=data, message="Cumplimiento SLA")


@router.get("/{workshop_id}/kpis/hotspots")
async def get_workshop_hotspots(
    workshop_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """KPI 5: Zonas con más incidentes del taller."""
    wid = await _resolve_workshop_id(workshop_id, current_user)
    start_date, end_date = _normalize_dates(start_date, end_date)
    svc = WorkshopKPIService(db)
    data = await svc.get_hotspots(wid, start_date, end_date, limit)
    return success_response(data=data, message="Zonas con más incidentes")


@router.get("/{workshop_id}/kpis/dashboard")
async def get_workshop_dashboard(
    workshop_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Dashboard unificado con todos los KPIs del taller."""
    import traceback
    try:
        wid = await _resolve_workshop_id(workshop_id, current_user)
        start_date, end_date = _normalize_dates(start_date, end_date)
        svc = WorkshopKPIService(db)
        data = await svc.get_dashboard(wid, start_date, end_date)
        return success_response(data=data, message="Dashboard de KPIs del taller")
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR en KPI dashboard: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


# ------------------------------------------------------------------ #
# Endpoints cross-taller (admin)
# ------------------------------------------------------------------ #

@router.get("/kpis/efficiency-ranking")
async def get_efficiency_ranking(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """KPI 4: Ranking de talleres más eficientes (admin o taller)."""
    if current_user.user_type not in ADMIN_TYPES and getattr(current_user, 'user_type', '') != "workshop":
        raise HTTPException(403, "No autorizado")
    start_date, end_date = _normalize_dates(start_date, end_date)
    svc = WorkshopKPIService(db)
    data = await svc.get_efficiency_ranking(start_date, end_date, limit)
    return success_response(data=data, message="Ranking de eficiencia")


@router.get("/kpis/hotspots")
async def get_global_hotspots(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """KPI 5: Zonas con más incidentes (global, admin)."""
    if getattr(current_user, 'user_type', '') not in ADMIN_TYPES:
        raise HTTPException(403, "Solo administradores pueden ver zonas globales")
    start_date, end_date = _normalize_dates(start_date, end_date)
    svc = WorkshopKPIService(db)
    data = await svc.get_hotspots(None, start_date, end_date, limit)
    return success_response(data=data, message="Zonas críticas globales")
