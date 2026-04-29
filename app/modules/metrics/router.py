"""
Metrics and reporting endpoints.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.dependencies import get_current_user, require_permission
from ...core.permissions import Permission
from ...core.responses import success_response, error_response
from .services import MetricsService
from .reports_service import ReportsService
from .communication_metrics import CommunicationMetricsService
from ...models.user import User

router = APIRouter(prefix="/metrics", tags=["metrics-reporting"])


def normalize_dates(start_date: Optional[datetime], end_date: Optional[datetime]):
    """Normalize dates for consistent filtering (Naive UTC)."""
    if start_date:
        if start_date.tzinfo is not None:
            start_date = start_date.astimezone(timezone.utc).replace(tzinfo=None)
            
    if end_date:
        if end_date.tzinfo is not None:
            end_date = end_date.astimezone(timezone.utc).replace(tzinfo=None)
        # Set to end of day
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start_date, end_date


@router.get("/workshops/{workshop_id}")
async def get_workshop_metrics(
    workshop_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get metrics for a specific workshop.
    """
    start_date, end_date = normalize_dates(start_date, end_date)

    metrics_service = MetricsService(db)
    metrics = await metrics_service.get_workshop_metrics(
        workshop_id=workshop_id,
        start_date=start_date,
        end_date=end_date
    )
    return success_response(data=metrics, message="Workshop metrics retrieved successfully")


@router.get("/technicians/{technician_id}")
async def get_technician_metrics(
    technician_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get metrics for a specific technician.
    """
    if current_user.user_type not in ["admin", "workshop"] and current_user.id != technician_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only view your own metrics")

    metrics_service = MetricsService(db)
    start_date, end_date = normalize_dates(start_date, end_date)
    metrics = await metrics_service.get_technician_metrics(
        technician_id=technician_id,
        start_date=start_date,
        end_date=end_date
    )
    return success_response(data=metrics, message="Technician metrics retrieved successfully")


@router.get("/system")
async def get_system_metrics(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPORT_VIEW_ALL))
):
    """
    Get global system metrics.
    """
    start_date, end_date = normalize_dates(start_date, end_date)

    metrics_service = MetricsService(db)
    metrics = await metrics_service.get_system_metrics(
        start_date=start_date,
        end_date=end_date
    )
    return success_response(data=metrics, message="System metrics retrieved successfully")


@router.get("/reports/incidents")
async def get_incident_report(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    category_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    workshop_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed incident report with filters."""
    # Security: Workshop can only see their own
    if current_user.user_type == "workshop":
        workshop_id = current_user.id
    elif current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to view reports")

    start_date, end_date = normalize_dates(start_date, end_date)
    service = ReportsService(db)
    data = await service.get_incident_report(start_date, end_date, category_id, status, workshop_id)
    return success_response(data=data)


@router.get("/reports/financial")
async def get_financial_report(
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    workshop_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get financial summary report."""
    if current_user.user_type == "workshop":
        workshop_id = current_user.id
    elif current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    start_date, end_date = normalize_dates(start_date, end_date)
    service = ReportsService(db)
    data = await service.get_financial_report(start_date, end_date, workshop_id)
    return success_response(data=data)


@router.get("/reports/performance")
async def get_performance_report(
    workshop_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get workshop performance metrics."""
    # Security: Workshop can only see their own
    if current_user.user_type == "workshop":
        workshop_id = current_user.id
    elif current_user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to view performance reports")

    start_date, end_date = normalize_dates(start_date, end_date)
    service = ReportsService(db)
    data = await service.get_performance_report(workshop_id, start_date, end_date)
    return success_response(data=data)


@router.get("/reports/export/{export_format}")
async def export_report(
    export_format: str,
    report_type: str = Query(..., description="incident, financial, or performance"),
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    workshop_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export reports to PDF or Excel."""
    if current_user.user_type == "workshop":
        workshop_id = current_user.id

    start_date, end_date = normalize_dates(start_date, end_date)
    service = ReportsService(db)
    data = []
    title = f"Reporte de {report_type.capitalize()}"

    if report_type == "incident":
        data = await service.get_incident_report(start_date, end_date, workshop_id=workshop_id)
    elif report_type == "financial":
        res = await service.get_financial_report(start_date, end_date, workshop_id=workshop_id)
        data = [res["summary"]]
    elif report_type == "performance":
        data = await service.get_performance_report(workshop_id, start_date, end_date)

    if export_format == "pdf":
        content = await service.export_to_pdf(data, title)
        media_type = "application/pdf"
        filename = f"report_{report_type}_{datetime.now().strftime('%Y%m%d')}.pdf"
    else:
        content = await service.export_to_excel(data, report_type)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"report_{report_type}_{datetime.now().strftime('%Y%m%d')}.xlsx"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/incidents/by-category")
async def get_incidents_by_category(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get incident count grouped by category."""
    start_date, end_date = normalize_dates(start_date, end_date)
    metrics_service = MetricsService(db)
    categories = await metrics_service.get_incidents_by_category(start_date=start_date, end_date=end_date)
    return success_response(data={"categories": categories, "total": sum(c["count"] for c in categories)})


@router.get("/communication")
async def get_communication_metrics(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPORT_VIEW_ALL))
):
    """Get comprehensive communication metrics."""
    comm_metrics_service = CommunicationMetricsService(db)
    metrics = await comm_metrics_service.get_comprehensive_metrics(start_time=start_time, end_time=end_time)
    return success_response(data=metrics)
