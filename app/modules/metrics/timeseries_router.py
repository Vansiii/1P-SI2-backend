"""
API endpoints for time series metrics.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from typing import List, Optional

from ...core.database import get_db
from ...core.dependencies import get_current_user
from ...core.responses import success_response
from .timeseries_service import MetricsTimeSeriesService
from ...models.user import User

router = APIRouter(prefix="/stats/timeline", tags=["Stats Timeline"])


@router.get("/response-time")
async def get_response_time_series(
    days: int = Query(30, ge=1, le=365, description="Number of days to retrieve"),
    workshop_id: Optional[int] = Query(None, description="Filter by workshop ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get response time time series data.
    
    Returns daily average response times for the specified period.
    """
    service = MetricsTimeSeriesService(db)
    data = await service.get_response_time_series(days=days, workshop_id=workshop_id)
    
    return success_response(
        data=data,
        message="Response time series retrieved successfully"
    )


@router.get("/resolution-time")
async def get_resolution_time_series(
    days: int = Query(30, ge=1, le=365, description="Number of days to retrieve"),
    workshop_id: Optional[int] = Query(None, description="Filter by workshop ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get resolution time time series data.
    
    Returns daily average resolution times for the specified period.
    """
    service = MetricsTimeSeriesService(db)
    data = await service.get_resolution_time_series(days=days, workshop_id=workshop_id)
    
    return success_response(
        data=data,
        message="Resolution time series retrieved successfully"
    )


@router.get("/incidents-count")
async def get_incidents_count_series(
    days: int = Query(30, ge=1, le=365, description="Number of days to retrieve"),
    workshop_id: Optional[int] = Query(None, description="Filter by workshop ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get incidents count time series data.
    
    Returns daily incident counts for the specified period.
    """
    service = MetricsTimeSeriesService(db)
    data = await service.get_incidents_count_series(
        days=days,
        workshop_id=workshop_id,
        status=status
    )
    
    return success_response(
        data=data,
        message="Incidents count series retrieved successfully"
    )


@router.get("/technician-performance")
async def get_technician_performance(
    workshop_id: int = Query(..., description="Workshop ID"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    limit: int = Query(10, ge=1, le=50, description="Number of top technicians"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get technician performance data.
    
    Returns performance metrics for top technicians in a workshop.
    """
    service = MetricsTimeSeriesService(db)
    data = await service.get_technician_performance(
        workshop_id=workshop_id,
        days=days,
        limit=limit
    )
    
    return success_response(
        data=data,
        message="Technician performance retrieved successfully"
    )


@router.get("/category-trends")
async def get_category_trends(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    workshop_id: Optional[int] = Query(None, description="Filter by workshop ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get category trends over time.
    
    Returns incident counts by category over the specified period.
    """
    service = MetricsTimeSeriesService(db)
    data = await service.get_category_trends(days=days, workshop_id=workshop_id)
    
    return success_response(
        data=data,
        message="Category trends retrieved successfully"
    )


@router.get("/hourly-distribution")
async def get_hourly_distribution(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    workshop_id: Optional[int] = Query(None, description="Filter by workshop ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get hourly distribution of incidents.
    
    Returns incident counts by hour of day.
    """
    service = MetricsTimeSeriesService(db)
    data = await service.get_hourly_distribution(days=days, workshop_id=workshop_id)
    
    return success_response(
        data=data,
        message="Hourly distribution retrieved successfully"
    )


@router.get("/weekly-comparison")
async def get_weekly_comparison(
    weeks: int = Query(4, ge=2, le=12, description="Number of weeks to compare"),
    workshop_id: Optional[int] = Query(None, description="Filter by workshop ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get weekly comparison data.
    
    Returns metrics comparison across multiple weeks.
    """
    service = MetricsTimeSeriesService(db)
    data = await service.get_weekly_comparison(weeks=weeks, workshop_id=workshop_id)
    
    return success_response(
        data=data,
        message="Weekly comparison retrieved successfully"
    )
