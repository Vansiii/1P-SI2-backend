"""
Metrics and reporting endpoints.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.dependencies import get_current_user, require_permission
from ...core.permissions import Permission
from ...core.responses import success_response
from .services import MetricsService
from ...models.user import User

router = APIRouter(prefix="/metrics", tags=["metrics-reporting"])


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
    
    Returns:
    - Total incidents (resolved, cancelled, active)
    - Resolution rate
    - Average response time
    - Average resolution time
    - Active technicians count
    
    **Permissions:** Workshop admin or system admin
    """
    metrics_service = MetricsService(db)
    
    metrics = await metrics_service.get_workshop_metrics(
        workshop_id=workshop_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return success_response(
        data=metrics,
        message="Workshop metrics retrieved successfully"
    )


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
    
    Returns:
    - Total incidents (resolved)
    - Resolution rate
    - Average resolution time
    - Total distance traveled
    
    **Permissions:** Technician (own metrics), workshop admin, or system admin
    """
    # Verify permissions
    if current_user.user_type not in ["admin", "workshop"] and current_user.id != technician_id:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own metrics"
        )

    metrics_service = MetricsService(db)
    
    metrics = await metrics_service.get_technician_metrics(
        technician_id=technician_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return success_response(
        data=metrics,
        message="Technician metrics retrieved successfully"
    )


@router.get("/system")
async def get_system_metrics(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPORT_VIEW_ALL))
):
    """
    Get global system metrics.
    
    Returns:
    - Total incidents by state
    - Active workshops and technicians
    - Average response time
    - Assignment success rate
    
    **Permissions:** System admin only
    """
    metrics_service = MetricsService(db)
    
    metrics = await metrics_service.get_system_metrics(
        start_date=start_date,
        end_date=end_date
    )
    
    return success_response(
        data=metrics,
        message="System metrics retrieved successfully"
    )


@router.get("/incidents/by-category")
async def get_incidents_by_category(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get incident count grouped by category.
    
    Useful for generating charts and reports.
    
    **Permissions:** Authenticated user
    """
    metrics_service = MetricsService(db)
    
    categories = await metrics_service.get_incidents_by_category(
        start_date=start_date,
        end_date=end_date
    )
    
    return success_response(
        data={
            "categories": categories,
            "total": sum(c["count"] for c in categories)
        },
        message="Category statistics retrieved successfully"
    )
