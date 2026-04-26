"""
Periodic task for updating dashboard metrics.

This task runs every 1 minute to calculate and publish dashboard metrics
for real-time updates without polling.
"""
import asyncio
from datetime import datetime

from ..core.database import get_session_factory
from ..core.logging import get_logger
from ..modules.metrics.services import MetricsService

logger = get_logger(__name__)


async def update_dashboard_metrics():
    """
    Calculate and publish dashboard metrics.
    
    This function should be called periodically (every 1 minute) to update
    dashboard metrics in real-time.
    """
    session_factory = get_session_factory()
    
    async with session_factory() as session:
        try:
            metrics_service = MetricsService(session)
            await metrics_service.publish_metrics_update()
            
            logger.debug("Dashboard metrics updated successfully")
            
        except Exception as e:
            logger.error(
                f"Error updating dashboard metrics: {str(e)}",
                exc_info=True
            )


async def start_dashboard_metrics_task():
    """
    Start the periodic dashboard metrics update task.
    
    This task runs every 60 seconds (1 minute) to update dashboard metrics.
    """
    logger.info("🚀 Starting dashboard metrics update task (interval: 60s)")
    
    while True:
        try:
            await update_dashboard_metrics()
            await asyncio.sleep(60)  # Run every 1 minute
            
        except asyncio.CancelledError:
            logger.info("Dashboard metrics task cancelled")
            break
        except Exception as e:
            logger.error(
                f"Error in dashboard metrics task loop: {str(e)}",
                exc_info=True
            )
            # Continue despite errors
            await asyncio.sleep(60)
