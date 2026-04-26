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
from .communication_metrics import CommunicationMetricsService
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


@router.get("/communication")
async def get_communication_metrics(
    start_time: Optional[datetime] = Query(None, description="Start time for metrics (default: 24 hours ago)"),
    end_time: Optional[datetime] = Query(None, description="End time for metrics (default: now)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPORT_VIEW_ALL))
):
    """
    Get comprehensive communication metrics.
    
    Returns metrics about:
    - Event processing and delivery (outbox pattern)
    - GPS location tracking
    - WebSocket reconnection attempts
    
    **Permissions:** System admin only
    """
    comm_metrics_service = CommunicationMetricsService(db)
    
    metrics = await comm_metrics_service.get_comprehensive_metrics(
        start_time=start_time,
        end_time=end_time
    )
    
    return success_response(
        data=metrics,
        message="Communication metrics retrieved successfully"
    )


@router.get("/communication/events")
async def get_event_metrics(
    start_time: Optional[datetime] = Query(None, description="Start time for metrics (default: 24 hours ago)"),
    end_time: Optional[datetime] = Query(None, description="End time for metrics (default: now)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPORT_VIEW_ALL))
):
    """
    Get event processing and delivery metrics.
    
    Returns:
    - Total events published
    - Events processed/pending/failed
    - Success rate
    - Delivery rate (WebSocket vs FCM)
    
    **Permissions:** System admin only
    """
    comm_metrics_service = CommunicationMetricsService(db)
    
    metrics = await comm_metrics_service.get_event_metrics(
        start_time=start_time,
        end_time=end_time
    )
    
    return success_response(
        data=metrics,
        message="Event metrics retrieved successfully"
    )


@router.get("/communication/locations")
async def get_location_metrics(
    start_time: Optional[datetime] = Query(None, description="Start time for metrics (default: 24 hours ago)"),
    end_time: Optional[datetime] = Query(None, description="End time for metrics (default: now)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPORT_VIEW_ALL))
):
    """
    Get GPS location tracking metrics.
    
    Returns:
    - Total location updates
    - Unique technicians tracked
    - Updates per hour
    - Average accuracy
    
    **Permissions:** System admin only
    """
    comm_metrics_service = CommunicationMetricsService(db)
    
    metrics = await comm_metrics_service.get_location_metrics(
        start_time=start_time,
        end_time=end_time
    )
    
    return success_response(
        data=metrics,
        message="Location metrics retrieved successfully"
    )
