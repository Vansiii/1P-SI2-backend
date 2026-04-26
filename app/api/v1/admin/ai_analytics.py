"""
Admin AI Analytics Router

Provides endpoints for monitoring AI analysis performance metrics.
Only accessible by administrators.
"""
from datetime import datetime, timedelta, UTC
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from ....core import get_db_session, get_logger
from ....core.responses import create_success_response
from ....core.permissions import Permission
from ....core.dependencies import require_permission
from ....shared.dependencies.auth import get_current_user
from ....models.user import User
from ....models.incident_ai_analysis import IncidentAIAnalysis

logger = get_logger(__name__)

router = APIRouter(prefix="/ai-analytics", tags=["Admin - AI Analytics"])


class AIAnalyticsResponse(BaseModel):
    """Response with AI analysis performance metrics."""
    
    # Time period
    period_days: int = Field(..., description="Number of days analyzed")
    start_date: datetime = Field(..., description="Start of analysis period")
    end_date: datetime = Field(..., description="End of analysis period")
    
    # Count metrics
    total_analyses: int = Field(..., description="Total number of analyses")
    completed_count: int = Field(..., description="Number of completed analyses")
    failed_count: int = Field(..., description="Number of failed analyses")
    timeout_count: int = Field(..., description="Number of timed out analyses")
    pending_count: int = Field(..., description="Number of pending analyses")
    processing_count: int = Field(..., description="Number of currently processing analyses")
    
    # Success rate
    success_rate: float = Field(..., ge=0, le=100, description="Success rate percentage")
    timeout_rate: float = Field(..., ge=0, le=100, description="Timeout rate percentage")
    failure_rate: float = Field(..., ge=0, le=100, description="Failure rate percentage")
    
    # Latency metrics (in milliseconds)
    average_latency_ms: Optional[float] = Field(None, description="Average latency")
    min_latency_ms: Optional[int] = Field(None, description="Minimum latency")
    max_latency_ms: Optional[int] = Field(None, description="Maximum latency")
    p50_latency_ms: Optional[float] = Field(None, description="50th percentile (median) latency")
    p95_latency_ms: Optional[float] = Field(None, description="95th percentile latency")
    p99_latency_ms: Optional[float] = Field(None, description="99th percentile latency")
    
    # Model usage
    models_used: dict = Field(default_factory=dict, description="Count of analyses per model")
    
    # Category distribution
    categories: dict = Field(default_factory=dict, description="Count of analyses per category")
    
    # Priority distribution
    priorities: dict = Field(default_factory=dict, description="Count of analyses per priority")


@router.get(
    "",
    response_model=AIAnalyticsResponse,
    summary="Get AI analysis performance metrics",
    description="Get comprehensive AI analysis performance metrics for monitoring (Admin only)",
    dependencies=[Depends(require_permission(Permission.ADMIN_MONITOR_SYSTEM))],
)
async def get_ai_analytics(
    days: int = Query(default=7, ge=1, le=90, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get AI analysis performance metrics.
    
    Provides comprehensive metrics including:
    - Success/failure/timeout rates
    - Latency statistics (avg, min, max, percentiles)
    - Model usage distribution
    - Category and priority distributions
    
    Only accessible by administrators.
    """
    # Calculate time period
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)
    
    # Query all analyses in the period
    result = await session.execute(
        select(IncidentAIAnalysis)
        .where(
            and_(
                IncidentAIAnalysis.created_at >= start_date,
                IncidentAIAnalysis.created_at <= end_date
            )
        )
    )
    analyses = result.scalars().all()
    
    total_analyses = len(analyses)
    
    if total_analyses == 0:
        return create_success_response(
            data={
                "period_days": days,
                "start_date": start_date,
                "end_date": end_date,
                "total_analyses": 0,
                "completed_count": 0,
                "failed_count": 0,
                "timeout_count": 0,
                "pending_count": 0,
                "processing_count": 0,
                "success_rate": 0.0,
                "timeout_rate": 0.0,
                "failure_rate": 0.0,
                "average_latency_ms": None,
                "min_latency_ms": None,
                "max_latency_ms": None,
                "p50_latency_ms": None,
                "p95_latency_ms": None,
                "p99_latency_ms": None,
                "models_used": {},
                "categories": {},
                "priorities": {}
            },
            message=f"No AI analyses found in the last {days} days"
        )
    
    # Count by status
    completed_count = sum(1 for a in analyses if a.status == "completed")
    failed_count = sum(1 for a in analyses if a.status == "failed")
    timeout_count = sum(1 for a in analyses if a.status == "timeout")
    pending_count = sum(1 for a in analyses if a.status == "pending")
    processing_count = sum(1 for a in analyses if a.status == "processing")
    
    # Calculate rates
    success_rate = (completed_count / total_analyses * 100) if total_analyses > 0 else 0.0
    timeout_rate = (timeout_count / total_analyses * 100) if total_analyses > 0 else 0.0
    failure_rate = (failed_count / total_analyses * 100) if total_analyses > 0 else 0.0
    
    # Calculate latency metrics (only for completed analyses with latency data)
    latencies = [a.latency_ms for a in analyses if a.latency_ms is not None and a.status == "completed"]
    
    if latencies:
        latencies_sorted = sorted(latencies)
        average_latency_ms = sum(latencies) / len(latencies)
        min_latency_ms = min(latencies)
        max_latency_ms = max(latencies)
        
        # Calculate percentiles
        def percentile(data, p):
            """Calculate percentile of sorted data."""
            k = (len(data) - 1) * (p / 100)
            f = int(k)
            c = f + 1
            if c >= len(data):
                return data[-1]
            d0 = data[f]
            d1 = data[c]
            return d0 + (d1 - d0) * (k - f)
        
        p50_latency_ms = percentile(latencies_sorted, 50)
        p95_latency_ms = percentile(latencies_sorted, 95)
        p99_latency_ms = percentile(latencies_sorted, 99)
    else:
        average_latency_ms = None
        min_latency_ms = None
        max_latency_ms = None
        p50_latency_ms = None
        p95_latency_ms = None
        p99_latency_ms = None
    
    # Model usage distribution
    models_used = {}
    for analysis in analyses:
        if analysis.model_name:
            models_used[analysis.model_name] = models_used.get(analysis.model_name, 0) + 1
    
    # Category distribution (only completed analyses)
    categories = {}
    for analysis in analyses:
        if analysis.status == "completed" and analysis.category:
            categories[analysis.category] = categories.get(analysis.category, 0) + 1
    
    # Priority distribution (only completed analyses)
    priorities = {}
    for analysis in analyses:
        if analysis.status == "completed" and analysis.priority:
            priorities[analysis.priority] = priorities.get(analysis.priority, 0) + 1
    
    analytics_data = {
        "period_days": days,
        "start_date": start_date,
        "end_date": end_date,
        "total_analyses": total_analyses,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "timeout_count": timeout_count,
        "pending_count": pending_count,
        "processing_count": processing_count,
        "success_rate": round(success_rate, 2),
        "timeout_rate": round(timeout_rate, 2),
        "failure_rate": round(failure_rate, 2),
        "average_latency_ms": round(average_latency_ms, 2) if average_latency_ms else None,
        "min_latency_ms": min_latency_ms,
        "max_latency_ms": max_latency_ms,
        "p50_latency_ms": round(p50_latency_ms, 2) if p50_latency_ms else None,
        "p95_latency_ms": round(p95_latency_ms, 2) if p95_latency_ms else None,
        "p99_latency_ms": round(p99_latency_ms, 2) if p99_latency_ms else None,
        "models_used": models_used,
        "categories": categories,
        "priorities": priorities
    }
    
    logger.info(
        f"AI analytics retrieved for {days} days: "
        f"{total_analyses} total, {completed_count} completed, "
        f"{timeout_count} timeouts, {failed_count} failed"
    )
    
    return create_success_response(
        data=analytics_data,
        message=f"AI analytics for the last {days} days retrieved successfully"
    )
