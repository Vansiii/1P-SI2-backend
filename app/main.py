from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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


async def check_assignment_timeouts():
    """
    Background task to check for assignment timeouts and send reminders.
    Runs every minute to:
    1. Send reminders at 60% of timeout (e.g., 3 min for 5 min timeout)
    2. Detect workshops that didn't respond in time
    3. Trigger automatic reassignment
    """
    from .services.reassignment_service import ReassignmentService
    from .modules.push_notifications.services import PushNotificationService, PushNotificationData
    from .models.assignment_attempt import AssignmentAttempt
    from .models.workshop import Workshop
    from sqlalchemy import select, and_
    
    try:
        logger.info("⏰ Running assignment timeout check...")
        
        session_factory = get_session_factory()
        async with session_factory() as session:
            now = datetime.utcnow()
            
            # 1. Check for reminders (60% of timeout elapsed)
            reminder_result = await session.execute(
                select(AssignmentAttempt)
                .where(
                    and_(
                        AssignmentAttempt.status == 'pending',
                        AssignmentAttempt.timeout_at.isnot(None),
                        # Reminder at 60% of timeout
                        AssignmentAttempt.attempted_at + 
                        (AssignmentAttempt.timeout_at - AssignmentAttempt.attempted_at) * 0.6 <= now,
                        AssignmentAttempt.timeout_at > now,  # Not yet timed out
                        # Only send reminder once (check if response_message doesn't contain 'reminder')
                        ~AssignmentAttempt.response_message.like('%reminder sent%')
                    )
                )
            )
            
            reminder_attempts = list(reminder_result.scalars().all())
            
            if reminder_attempts:
                logger.info(f"📢 Sending {len(reminder_attempts)} timeout reminders...")
                push_service = PushNotificationService(session)
                
                for attempt in reminder_attempts:
                    try:
                        # Get workshop
                        workshop = await session.get(Workshop, attempt.workshop_id)
                        if not workshop:
                            continue
                        
                        # Calculate remaining time
                        remaining_seconds = (attempt.timeout_at - now).total_seconds()
                        remaining_minutes = int(remaining_seconds / 60)
                        
                        # Send reminder notification
                        await push_service.send_to_user(
                            user_id=workshop.id,
                            notification_data=PushNotificationData(
                                title="⏰ Recordatorio: Incidente pendiente",
                                body=f"Tienes {remaining_minutes} minutos para responder al incidente #{attempt.incident_id}",
                                data={
                                    "type": "assignment_reminder",
                                    "incident_id": str(attempt.incident_id),
                                    "remaining_minutes": str(remaining_minutes),
                                    "action": "view_incident",
                                    "action_url": f"/workshop/incidents/{attempt.incident_id}"
                                }
                            )
                        )
                        
                        # Mark reminder as sent
                        attempt.response_message = (
                            f"Reminder sent at {now.isoformat()} "
                            f"({remaining_minutes} min remaining)"
                        )
                        
                        logger.info(
                            f"📢 Sent reminder to workshop {workshop.workshop_name} "
                            f"for incident {attempt.incident_id}"
                        )
                        
                    except Exception as e:
                        logger.error(f"Failed to send reminder: {str(e)}")
                
                await session.commit()
            
            # 2. Check for actual timeouts
            reassignment_service = ReassignmentService(session)
            timed_out_incidents = await reassignment_service.check_timeouts()
            
            if timed_out_incidents:
                logger.warning(
                    f"⏰ Found {len(timed_out_incidents)} timed out incidents: {timed_out_incidents}"
                )
                
                # Reassign each timed out incident
                for incident_id in timed_out_incidents:
                    logger.info(f"🔄 Reassigning timed out incident {incident_id}...")
                    result = await reassignment_service.reassign_to_next_candidate(incident_id)
                    
                    if result.success:
                        logger.info(
                            f"✅ Successfully reassigned incident {incident_id} to "
                            f"{result.assigned_workshop.workshop_name if result.assigned_workshop else 'unknown'}"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Failed to reassign incident {incident_id}: {result.error_message}"
                        )
            else:
                logger.debug("✅ No timed out assignments found")
                
    except Exception as e:
        logger.error(f"❌ Error in timeout check task: {str(e)}", exc_info=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan manager."""
    # Startup
    await test_database_connection()
    if settings.environment == "development":
        await create_database_tables()
    
    # Start scheduler for background tasks
    logger.info("🚀 Starting assignment timeout scheduler...")
    scheduler.add_job(
        check_assignment_timeouts,
        trigger=IntervalTrigger(seconds=30),  # Changed from 1 minute to 30 seconds for better precision
        id="check_assignment_timeouts",
        name="Check Assignment Timeouts",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping executions
    )
    scheduler.start()
    logger.info("✅ Assignment timeout scheduler started (runs every 30 seconds)")
    
    yield
    
    # Shutdown
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
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
