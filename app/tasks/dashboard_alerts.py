"""
Periodic task for checking and triggering dashboard alerts.

This task runs every 5 minutes to check for alert conditions and publish
alert events when thresholds are exceeded.
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

from sqlalchemy import select, func, and_

from ..core.database import get_session_factory
from ..core.logging import get_logger
from ..core.event_publisher import EventPublisher
from ..shared.schemas.events.dashboard import DashboardAlertTriggeredEvent
from ..models.incidente import Incidente
from ..models.technician import Technician
from ..models.tracking_session import TrackingSession

logger = get_logger(__name__)


async def check_unassigned_incidents() -> List[Dict[str, Any]]:
    """
    Check for incidents that have been unassigned for more than 10 minutes.
    
    Returns:
        List of alert data dictionaries
    """
    alerts = []
    session_factory = get_session_factory()
    
    async with session_factory() as session:
        try:
            threshold_time = datetime.utcnow() - timedelta(minutes=10)
            
            # Find incidents in 'pendiente' state for more than 10 minutes
            result = await session.execute(
                select(Incidente.id, Incidente.created_at)
                .where(
                    and_(
                        Incidente.estado_actual == "pendiente",
                        Incidente.created_at < threshold_time
                    )
                )
            )
            
            unassigned_incidents = result.all()
            
            if unassigned_incidents:
                incident_ids = [inc.id for inc in unassigned_incidents]
                alerts.append({
                    "alert_type": "unassigned_incidents",
                    "severity": "warning",
                    "message": f"{len(unassigned_incidents)} incident(s) unassigned for more than 10 minutes",
                    "data": {
                        "count": len(unassigned_incidents),
                        "incident_ids": incident_ids,
                        "threshold_minutes": 10
                    }
                })
                
                logger.warning(
                    f"⚠️ Alert: {len(unassigned_incidents)} incidents unassigned >10 min: {incident_ids}"
                )
                
        except Exception as e:
            logger.error(f"Error checking unassigned incidents: {str(e)}", exc_info=True)
    
    return alerts


async def check_technician_location_updates() -> List[Dict[str, Any]]:
    """
    Check for technicians who haven't updated their location in more than 15 minutes.
    
    Returns:
        List of alert data dictionaries
    """
    alerts = []
    session_factory = get_session_factory()
    
    async with session_factory() as session:
        # TODO: Fix this query - TrackingSession doesn't have last_location_update field
        # Need to join with location updates table or add the field to the model
        logger.warning("Technician location check temporarily disabled - model field missing")
        return []  # Return empty list instead of None
        
        try:
            threshold_time = datetime.utcnow() - timedelta(minutes=15)
            
            # Find active tracking sessions without recent location updates
            result = await session.execute(
                select(
                    TrackingSession.technician_id,
                    TrackingSession.incidente_id,
                    TrackingSession.last_location_update
                )
                .where(
                    and_(
                        TrackingSession.is_active == True,
                        TrackingSession.last_location_update < threshold_time
                    )
                )
            )
            
            stale_sessions = result.all()
            
            if stale_sessions:
                technician_ids = [session.technician_id for session in stale_sessions]
                alerts.append({
                    "alert_type": "stale_technician_location",
                    "severity": "warning",
                    "message": f"{len(stale_sessions)} technician(s) without location update for more than 15 minutes",
                    "data": {
                        "count": len(stale_sessions),
                        "technician_ids": technician_ids,
                        "threshold_minutes": 15
                    }
                })
                
                logger.warning(
                    f"⚠️ Alert: {len(stale_sessions)} technicians without location update >15 min"
                )
                
        except Exception as e:
            logger.error(f"Error checking technician locations: {str(e)}", exc_info=True)
    
    return alerts


async def check_average_response_time() -> List[Dict[str, Any]]:
    """
    Check if average response time in the last hour exceeds 30 minutes.
    
    Returns:
        List of alert data dictionaries
    """
    alerts = []
    session_factory = get_session_factory()
    
    async with session_factory() as session:
        try:
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            
            # Calculate average response time for last hour
            avg_response_time = await session.scalar(
                select(func.avg(
                    func.extract('epoch', Incidente.assigned_at - Incidente.created_at) / 60
                ))
                .where(
                    and_(
                        Incidente.assigned_at.isnot(None),
                        Incidente.created_at >= one_hour_ago
                    )
                )
            )
            
            if avg_response_time and avg_response_time > 30:
                alerts.append({
                    "alert_type": "high_response_time",
                    "severity": "error",
                    "message": f"Average response time is {avg_response_time:.1f} minutes (threshold: 30 min)",
                    "data": {
                        "avg_response_time_minutes": round(avg_response_time, 2),
                        "threshold_minutes": 30,
                        "period_hours": 1
                    }
                })
                
                logger.error(
                    f"🚨 Alert: High average response time: {avg_response_time:.1f} min (threshold: 30 min)"
                )
                
        except Exception as e:
            logger.error(f"Error checking response time: {str(e)}", exc_info=True)
    
    return alerts


async def check_alerts():
    """
    Check all alert conditions and publish alert events.
    
    This function checks:
    - Incidents unassigned for more than 10 minutes
    - Technicians without location update for more than 15 minutes
    - Average response time exceeding 30 minutes
    """
    session_factory = get_session_factory()
    
    try:
        # Collect all alerts
        all_alerts = []
        
        all_alerts.extend(await check_unassigned_incidents())
        
        # Check technician locations (may return None if disabled)
        location_alerts = await check_technician_location_updates()
        if location_alerts:
            all_alerts.extend(location_alerts)
            
        all_alerts.extend(await check_average_response_time())
        
        # Publish alert events
        if all_alerts:
            async with session_factory() as session:
                for alert in all_alerts:
                    try:
                        alert_event = DashboardAlertTriggeredEvent(
                            alert_type=alert["alert_type"],
                            severity=alert["severity"],
                            message=alert["message"],
                            data=alert["data"]
                        )
                        
                        await EventPublisher.publish(session, alert_event)
                        
                        logger.info(
                            f"✅ Alert published: {alert['alert_type']} - {alert['message']}"
                        )
                        
                    except Exception as e:
                        logger.error(
                            f"Error publishing alert {alert['alert_type']}: {str(e)}",
                            exc_info=True
                        )
                
                await session.commit()
                
                logger.info(f"Published {len(all_alerts)} dashboard alerts")
        else:
            logger.debug("No dashboard alerts triggered")
            
    except Exception as e:
        logger.error(f"Error in check_alerts: {str(e)}", exc_info=True)


async def start_dashboard_alerts_task():
    """
    Start the periodic dashboard alerts checking task.
    
    This task runs every 5 minutes (300 seconds) to check for alert conditions.
    """
    logger.info("🚀 Starting dashboard alerts task (interval: 300s)")
    
    while True:
        try:
            await check_alerts()
            await asyncio.sleep(300)  # Run every 5 minutes
            
        except asyncio.CancelledError:
            logger.info("Dashboard alerts task cancelled")
            break
        except Exception as e:
            logger.error(
                f"Error in dashboard alerts task loop: {str(e)}",
                exc_info=True
            )
            # Continue despite errors
            await asyncio.sleep(300)
