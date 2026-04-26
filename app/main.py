from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .api.v1.router import api_router
from .core import (
    close_database_connection,
    create_database_tables,
    get_settings,
    test_database_connection,
    configure_logging,
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    RequestIDMiddleware,
    AuditMiddleware,
)
from .core.logging import get_logger
from .core.database import get_session_factory

# Configure logging first
configure_logging()

settings = get_settings()
logger = get_logger(__name__)

# Create scheduler for background tasks
scheduler = AsyncIOScheduler()

# Global OutboxProcessor instance for health checks
outbox_processor_instance: Optional['OutboxProcessor'] = None


# NOTE: Assignment timeout checking is now handled by State Machine in tasks/state_timeouts.py
# The old check_assignment_timeouts function has been removed to avoid duplication


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan manager."""
    # Startup
    await test_database_connection()
    if settings.environment == "development":
        await create_database_tables()
    
    # Initialize OutboxProcessor
    from .core.websocket import manager as ws_manager
    from .modules.outbox import OutboxProcessor
    
    global outbox_processor_instance
    outbox_processor_instance = OutboxProcessor(
        ws_manager=ws_manager,
        batch_size=100,
        poll_interval=1.0,  # Process every second
        max_retries=3
    )
    
    # Start OutboxProcessor
    logger.info("🚀 Starting OutboxProcessor...")
    await outbox_processor_instance.start()
    logger.info("✅ OutboxProcessor started")
    
    # ✅ Start State Machine timeout jobs (replaces old check_assignment_timeouts)
    logger.info("🚀 Starting State Machine timeout scheduler...")
    from .tasks.state_timeouts import check_all_timeouts
    
    # Single unified timeout check that handles both assignment and tracking
    scheduler.add_job(
        check_all_timeouts,
        trigger=IntervalTrigger(seconds=30),  # Check every 30 seconds for precision
        id="state_machine_all_timeouts",
        name="State Machine: All Timeouts",
        replace_existing=True,
        max_instances=1  # Prevent overlapping executions
    )
    
    # ✅ Start tracking cleanup job
    logger.info("🚀 Starting tracking cleanup scheduler...")
    from .tasks.tracking_cleanup import cleanup_old_locations
    
    # Clean up old location records every 6 hours at 2 AM, 8 AM, 2 PM, 8 PM
    scheduler.add_job(
        cleanup_old_locations,
        trigger='cron',
        hour='2,8,14,20',  # Run at 2 AM, 8 AM, 2 PM, 8 PM
        minute=0,
        id="tracking_cleanup",
        name="Tracking: Cleanup Old Locations",
        replace_existing=True,
        max_instances=1  # Prevent overlapping executions
    )
    
    # ✅ Start dashboard metrics job
    logger.info("🚀 Starting dashboard metrics scheduler...")
    from .tasks.dashboard_metrics import update_dashboard_metrics
    
    # Publish dashboard metrics every 1 minute
    scheduler.add_job(
        update_dashboard_metrics,
        trigger=IntervalTrigger(minutes=1),
        id="dashboard_metrics",
        name="Dashboard: Metrics Update",
        replace_existing=True,
        max_instances=1  # Prevent overlapping executions
    )
    
    # ✅ Start dashboard alerts job
    logger.info("🚀 Starting dashboard alerts scheduler...")
    from .tasks.dashboard_alerts import check_alerts
    
    # Check for dashboard alerts every 5 minutes
    scheduler.add_job(
        check_alerts,
        trigger=IntervalTrigger(minutes=5),
        id="dashboard_alerts",
        name="Dashboard: Alert Checking",
        replace_existing=True,
        max_instances=1  # Prevent overlapping executions
    )
    
    scheduler.start()
    logger.info("✅ State Machine timeout scheduler started (runs every 30 seconds)")
    logger.info("✅ Tracking cleanup scheduler started (runs every 6 hours)")
    logger.info("✅ Dashboard metrics scheduler started (runs every 1 minute)")
    logger.info("✅ Dashboard alerts scheduler started (runs every 5 minutes)")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down OutboxProcessor...")
    if outbox_processor_instance:
        await outbox_processor_instance.stop()
    logger.info("✅ OutboxProcessor shut down")
    
    logger.info("🛑 Shutting down assignment timeout scheduler...")
    scheduler.shutdown(wait=True)
    logger.info("✅ Scheduler shut down")
    
    await close_database_connection()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="MecánicoYa - API REST",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)

# Add middleware (order matters - first added is outermost)

# Apply CORS middleware for HTTP requests
# TEMPORARY: Allow all origins for WebSocket development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ TEMPORAL: Permitir todos los orígenes para desarrollo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom middleware
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(AuditMiddleware, audit_all_methods=False)  # Only audit POST, PUT, PATCH, DELETE

# Include API router
app.include_router(api_router)


# Root endpoint
@app.get("/", tags=["Root"])
def read_root() -> dict[str, str]:
    """Root endpoint with basic API information."""
    return {
        "message": "MecánicoYa - API REST",
        "version": settings.app_version,
        "docs": "/docs" if settings.environment != "production" else "disabled",
        "health": "/api/v1/health",
    }


def get_outbox_processor():
    """Get the global OutboxProcessor instance."""
    return outbox_processor_instance