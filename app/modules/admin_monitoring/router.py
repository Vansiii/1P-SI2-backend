"""
Admin Monitoring Router

API endpoints for administrative monitoring and dashboard.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.responses import success_response, error_response
from app.models.user import User

from .service import AdminMonitoringService
from .schemas import (
    SystemMetrics,
    IncidentsResponse,
    WorkshopsResponse,
    ChartData
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/monitoring", tags=["Admin Monitoring"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency to ensure only admin users can access these endpoints.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User if admin
        
    Raises:
        HTTPException: If user is not admin
    """
    if current_user.user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can access this endpoint"
        )
    return current_user


@router.get(
    "/summary",
    response_model=dict,
    summary="Get System Metrics Summary",
    description="Get system-wide metrics for admin dashboard including incident counts, workshop availability, etc."
)
async def get_system_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get system-wide metrics summary.
    
    **Requires:** Admin role
    
    **Returns:**
    - active_incidents: Total active incidents
    - unassigned_incidents: Incidents without workshop
    - pending_incidents: Incidents pending assignment
    - assigned_incidents: Incidents assigned to workshop
    - in_progress_incidents: Incidents in progress
    - resolved_today: Incidents resolved today
    - available_workshops: Workshops available
    - busy_workshops: Workshops busy
    - offline_workshops: Workshops offline
    - updated_at: Last update timestamp
    """
    try:
        metrics = await AdminMonitoringService.get_system_summary(db)
        return success_response(
            data=metrics.model_dump(),
            message="System metrics retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Error getting system summary: {e}")
        return error_response(
            message="Error retrieving system metrics",
            code="SYSTEM_METRICS_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.get(
    "/incidents",
    response_model=dict,
    summary="Get All Incidents with Filters",
    description="Get all incidents with optional filters by status, priority, category, and search"
)
async def get_incidents(
    estado: Optional[str] = Query(None, description="Filter by status"),
    prioridad_ia: Optional[str] = Query(None, description="Filter by AI priority (alta, media, baja)"),
    categoria_ia: Optional[str] = Query(None, description="Filter by AI category"),
    search: Optional[str] = Query(None, description="Search by ID, client, workshop, or description"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get all incidents with optional filters.
    
    **Requires:** Admin role
    
    **Query Parameters:**
    - estado: Filter by status (pendiente, asignado, en_proceso, etc.)
    - prioridad_ia: Filter by AI priority (alta, media, baja)
    - categoria_ia: Filter by AI category
    - search: Search by ID, client name, workshop name, or description
    - limit: Maximum results to return (default: 100, max: 500)
    - offset: Offset for pagination (default: 0)
    
    **Returns:**
    - incidents: List of incidents with full details
    - total: Total count of incidents matching filters
    - by_status: Breakdown of incidents by status
    """
    try:
        response = await AdminMonitoringService.get_incidents_with_filters(
            db=db,
            estado=estado,
            prioridad_ia=prioridad_ia,
            categoria_ia=categoria_ia,
            search=search,
            limit=limit,
            offset=offset
        )
        return success_response(
            data=response.model_dump(),
            message="Incidents retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Error getting incidents: {e}")
        return error_response(
            message="Error retrieving incidents",
            code="INCIDENTS_RETRIEVAL_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.get(
    "/workshops",
    response_model=dict,
    summary="Get All Workshops with Status",
    description="Get all workshops with their availability status and technician counts"
)
async def get_workshops(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get all workshops with their availability status.
    
    **Requires:** Admin role
    
    **Returns:**
    - workshops: List of workshops with status and technician counts
    - total: Total count of workshops
    - by_status: Breakdown of workshops by availability status
    
    **Workshop Status:**
    - available: Workshop has at least one available technician
    - busy: All technicians are busy
    - offline: Workshop is inactive or has no technicians
    - out_of_service: Workshop is not verified
    """
    try:
        response = await AdminMonitoringService.get_workshops_with_status(db)
        return success_response(
            data=response.model_dump(),
            message="Workshops retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Error getting workshops: {e}")
        return error_response(
            message="Error retrieving workshops",
            code="WORKSHOPS_RETRIEVAL_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@router.get(
    "/charts",
    response_model=dict,
    summary="Get Chart Data",
    description="Get data for all charts in admin dashboard"
)
async def get_charts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get data for all charts in admin dashboard.
    
    **Requires:** Admin role
    
    **Returns:**
    - incidents_by_status: Pie chart data for incidents by status
    - incidents_by_category: Bar chart data for incidents by AI category
    - incidents_by_priority: Donut chart data for incidents by AI priority
    - workshops_by_status: Pie chart data for workshops by availability
    - incidents_timeline: Line chart data for incidents over last 24 hours
    """
    try:
        chart_data = await AdminMonitoringService.get_charts_data(db)
        return success_response(
            data=chart_data.model_dump(),
            message="Chart data retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Error getting chart data: {e}")
        return error_response(
            message="Error retrieving chart data",
            code="CHART_DATA_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
