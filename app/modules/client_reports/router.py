"""
Client reports endpoints — consulta y exportación PDF/Excel para clientes.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.responses import success_response
from ...shared.dependencies.auth import get_current_client
from .service import ClientReportsService

router = APIRouter(prefix="/client/reports", tags=["Client Reports"])


@router.get("/summary")
async def get_summary(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_client),
):
    svc = ClientReportsService(db)
    data = await svc.get_summary(current_user.id)
    return success_response(data=data, message="Resumen del cliente")


@router.get("/spending")
async def get_spending(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_client),
):
    svc = ClientReportsService(db)
    data = await svc.get_spending(current_user.id)
    return success_response(data=data, message="Reporte de gastos")


@router.get("/vehicle/{vehiculo_id}/history")
async def get_vehicle_history(
    vehiculo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_client),
):
    svc = ClientReportsService(db)
    data = await svc.get_vehicle_history(vehiculo_id, current_user.id)
    return success_response(data=data, message="Historial del vehículo")


# ---- Export endpoints ----

def _filename(prefix: str, fmt: str) -> str:
    from datetime import datetime
    dt = datetime.utcnow().strftime('%Y%m%d_%H%M')
    ext = 'pdf' if fmt == 'pdf' else 'xlsx'
    return f"mecanicoya_{prefix}_{dt}.{ext}"


@router.get("/summary/download/{fmt}")
async def download_summary(
    fmt: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_client),
):
    if fmt not in ('pdf', 'excel'):
        raise HTTPException(400, "Formato inválido. Usa 'pdf' o 'excel'")
    svc = ClientReportsService(db)
    content, mime, prefix = await svc.export_summary(current_user.id, fmt)
    return Response(content=content, media_type=mime,
                    headers={"Content-Disposition": f"attachment; filename={_filename(prefix, fmt)}"})


@router.get("/spending/download/{fmt}")
async def download_spending(
    fmt: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_client),
):
    if fmt not in ('pdf', 'excel'):
        raise HTTPException(400, "Formato inválido. Usa 'pdf' o 'excel'")
    svc = ClientReportsService(db)
    content, mime, prefix = await svc.export_spending(current_user.id, fmt)
    return Response(content=content, media_type=mime,
                    headers={"Content-Disposition": f"attachment; filename={_filename(prefix, fmt)}"})


@router.get("/vehicle/{vehiculo_id}/history/download/{fmt}")
async def download_vehicle_history(
    vehiculo_id: int,
    fmt: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_client),
):
    if fmt not in ('pdf', 'excel'):
        raise HTTPException(400, "Formato inválido. Usa 'pdf' o 'excel'")
    svc = ClientReportsService(db)
    content, mime, prefix = await svc.export_vehicle_history(vehiculo_id, current_user.id, fmt)
    return Response(content=content, media_type=mime,
                    headers={"Content-Disposition": f"attachment; filename={_filename(prefix, fmt)}"})
