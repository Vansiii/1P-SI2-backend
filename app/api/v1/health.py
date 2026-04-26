"""
Health check endpoints.
"""
import asyncio
import platform
import sys
from datetime import datetime, UTC
from typing import Dict, Any

import psutil
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core import get_db_session, get_database_health, get_logger
from ...core.responses import create_success_response

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "",
    summary="Basic health check",
    description="Basic health check endpoint that returns system status",
)
async def health_check():
    """Basic health check endpoint."""
    return create_success_response(
        data={
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "1.0.0",
        },
        message="System is healthy",
    )


@router.get(
    "/detailed",
    summary="Detailed health check",
    description="Detailed health check with database and system metrics",
)
async def detailed_health_check(
    session: AsyncSession = Depends(get_db_session),
):
    """Detailed health check with database and system information."""
    try:
        # Check database health
        db_health = await get_database_health(session)
        
        # Get system information
        system_info = {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "python_version": sys.version,
            "cpu_count": psutil.cpu_count(),
            "memory_total": psutil.virtual_memory().total,
            "memory_available": psutil.virtual_memory().available,
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": {
                "total": psutil.disk_usage('/').total,
                "used": psutil.disk_usage('/').used,
                "free": psutil.disk_usage('/').free,
                "percent": psutil.disk_usage('/').percent,
            },
        }
        
        # Overall health status
        overall_status = "healthy" if db_health["status"] == "healthy" else "unhealthy"
        
        return create_success_response(
            data={
                "status": overall_status,
                "timestamp": datetime.now(UTC).isoformat(),
                "version": "1.0.0",
                "database": db_health,
                "system": system_info,
            },
            message=f"System is {overall_status}",
            status_code=status.HTTP_200_OK if overall_status == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return create_success_response(
            data={
                "status": "unhealthy",
                "timestamp": datetime.now(UTC).isoformat(),
                "error": str(e),
            },
            message="Health check failed",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@router.get(
    "/database",
    summary="Database health check",
    description="Check database connectivity and performance",
)
async def database_health_check(
    session: AsyncSession = Depends(get_db_session),
):
    """Database-specific health check."""
    try:
        db_health = await get_database_health(session)
        
        return create_success_response(
            data=db_health,
            message="Database health check completed",
            status_code=status.HTTP_200_OK if db_health["status"] == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return create_success_response(
            data={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            },
            message="Database health check failed",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@router.get(
    "/readiness",
    summary="Readiness probe",
    description="Kubernetes readiness probe endpoint",
)
async def readiness_probe(
    session: AsyncSession = Depends(get_db_session),
):
    """Readiness probe for Kubernetes."""
    try:
        # Quick database connectivity check
        await session.execute("SELECT 1")
        
        return create_success_response(
            data={"ready": True},
            message="Service is ready",
        )
        
    except Exception as e:
        logger.error("Readiness probe failed", error=str(e))
        return create_success_response(
            data={"ready": False, "error": str(e)},
            message="Service is not ready",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@router.get(
    "/liveness",
    summary="Liveness probe",
    description="Kubernetes liveness probe endpoint",
)
async def liveness_probe():
    """Liveness probe for Kubernetes."""
    return create_success_response(
        data={"alive": True},
        message="Service is alive",
    )


@router.get(
    "/outbox",
    summary="Outbox Processor health check",
    description="Check health status of the Outbox Processor for event delivery",
)
async def outbox_health_check(
    session: AsyncSession = Depends(get_db_session),
):
    """Outbox Processor health check endpoint."""
    try:
        # Import here to avoid circular imports
        from ...main import get_outbox_processor
        
        outbox_processor = get_outbox_processor()
        
        if not outbox_processor:
            return create_success_response(
                data={
                    "status": "unhealthy",
                    "error": "OutboxProcessor not initialized",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                message="OutboxProcessor not available",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        
        # Get health status
        health_status = outbox_processor.get_health_status()
        
        # Get pending events count
        pending_stats = await outbox_processor.get_pending_events_count()
        
        # Combine health data
        health_data = {
            "processor": health_status,
            "pending_events": pending_stats,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        
        # Determine overall status
        is_healthy = (
            health_status.get("status") == "healthy" and
            pending_stats.get("is_backlog_healthy", False) and
            not pending_stats.get("error")
        )
        
        return create_success_response(
            data=health_data,
            message=f"OutboxProcessor is {'healthy' if is_healthy else 'unhealthy'}",
            status_code=status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        
    except Exception as e:
        logger.error("OutboxProcessor health check failed", error=str(e))
        return create_success_response(
            data={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            },
            message="OutboxProcessor health check failed",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )