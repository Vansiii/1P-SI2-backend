"""
State Machine Timeout Handlers.

This module implements automatic timeout detection and reassignment
for incidents based on AI-determined priority levels.

TIMEOUT LOGIC - CASCADING ASSIGNMENT (AUTO MODE):
- AI assigns priority (alta/media/baja) to each incident
- Each priority has different response time:
  * ALTA: 3 minutes
  * MEDIA: 5 minutes  
  * BAJA: 10 minutes
  

CASCADING FLOW (AUTO):
1. System assigns to Workshop A → waits X minutes
2. If A doesn't respond → timeout → assigns to Workshop B → waits X minutes
3. ... continues through ALL available workshops
4. If NO workshop responds → 'sin_taller_disponible'

MANUAL MODE TIMEOUT (CU27):
- Client selects workshop manually → timer starts
- If workshop doesn't respond → timeout
- Backend clears taller_id (incident returns to pendiente without workshop)
- Client notified to reselect or choose another
- NO automatic reassignment (client decides)

IMPORTANT:
- Auto and manual modes are completely separated
- Manual timeout does NOT trigger cascading reassignment
"""

from datetime import datetime, timedelta, UTC
from typing import List, Optional

from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging import get_logger
from ..core.database import get_session_factory
from ..core.event_publisher import EventPublisher
from ..shared.schemas.events.incident import (
    IncidentAssignmentTimeoutEvent,
    IncidentStatusChangedEvent
)
from ..models.incidente import Incidente
from ..models.assignment_attempt import AssignmentAttempt
from ..models.tracking_session import TrackingSession
from ..models.technician import Technician

logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION - Timeout by Priority
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION - Timeouts
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# 1. ASSIGNMENT TIMEOUT (Workshop Response Time)
# ═══════════════════════════════════════════════════════════════════════════
# How long the WORKSHOP has to ACCEPT or REJECT an incident assignment
# Timeline: From system assigns incident → until workshop accepts/rejects
# If timeout expires: System reassigns to next available workshop

TIMEOUT_BY_PRIORITY = {
    "alta": 3,      # High priority: Workshop has 3 minutes to respond
    "media": 5,     # Medium priority: Workshop has 5 minutes to respond
    "baja": 10,     # Low priority: Workshop has 10 minutes to respond
}

DEFAULT_TIMEOUT_MINUTES = 5  # Default if priority not set

# ═══════════════════════════════════════════════════════════════════════════
# 2. TRACKING TIMEOUT (Technician Service Completion Time)
# ═══════════════════════════════════════════════════════════════════════════
# How long the TECHNICIAN has to COMPLETE the service
# Timeline: From workshop assigns technician → until service is completed
# Formula: Travel Time + Service Duration + Buffer
# If timeout expires: System auto-closes session and frees technician

# Service duration by incident category (actual work time, excluding travel)
SERVICE_DURATION_BY_CATEGORY = {
    # Quick services (15-30 minutes)
    "bateria": 30,           # Battery jump-start or replacement
    "llanta": 30,            # Tire change or repair
    "combustible": 20,       # Fuel delivery
    "llave": 25,             # Key replacement/lockout
    
    # Medium services (45-90 minutes)
    "electrico": 60,         # Electrical diagnostics
    "frenos": 90,            # Brake inspection/repair
    "suspension": 75,        # Suspension check
    "transmision": 90,       # Transmission diagnostics
    
    # Long services (2-4 hours)
    "motor": 180,            # Engine diagnostics/repair
    "choque_leve": 120,      # Minor collision assessment
    "remolque": 240,         # Towing service (depends on distance)
    "diagnostico": 120,      # General diagnostics
    
    # Default for unknown categories
    "otros": 90,             # 1.5 hours default
    "ambiguo": 120,          # 2 hours for ambiguous cases
}

DEFAULT_SERVICE_DURATION_MINUTES = 90  # Default if category not set or unknown

# Travel time calculation
# Average speed in urban areas: 30 km/h (considering traffic, stops, etc.)
AVERAGE_SPEED_KMH = 30
# Add buffer time for parking, finding location, etc.
TRAVEL_BUFFER_MINUTES = 10


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def calculate_dynamic_timeout(
    distance_km: float,
    category: str,
    priority: str
) -> int:
    """
    Calculate dynamic timeout based on distance and incident category.
    
    Formula:
    Total Timeout = Travel Time + Service Duration + Buffer
    
    Where:
    - Travel Time = (distance_km / AVERAGE_SPEED_KMH) * 60 minutes
    - Service Duration = SERVICE_DURATION_BY_CATEGORY[category]
    - Buffer = TRAVEL_BUFFER_MINUTES (for parking, finding location, etc.)
    
    Args:
        distance_km: Distance from technician to incident in kilometers
        category: Incident category (bateria, motor, etc.)
        priority: Incident priority (alta, media, baja) - for logging only
        
    Returns:
        Total timeout in minutes
        
    Examples:
        - 5 km distance + bateria (30 min) = 10 min travel + 30 min service + 10 min buffer = 50 min
        - 15 km distance + motor (180 min) = 30 min travel + 180 min service + 10 min buffer = 220 min
        - 2 km distance + llanta (30 min) = 4 min travel + 30 min service + 10 min buffer = 44 min
    """
    # Calculate travel time in minutes
    travel_time_minutes = (distance_km / AVERAGE_SPEED_KMH) * 60
    
    # Get service duration for category
    service_duration = SERVICE_DURATION_BY_CATEGORY.get(
        category,
        DEFAULT_SERVICE_DURATION_MINUTES
    )
    
    # Total timeout = travel + service + buffer
    total_timeout = int(travel_time_minutes + service_duration + TRAVEL_BUFFER_MINUTES)
    
    logger.debug(
        f"📊 Dynamic timeout calculated: "
        f"distance={distance_km:.2f}km, category={category}, priority={priority} → "
        f"travel={int(travel_time_minutes)}min + service={service_duration}min + buffer={TRAVEL_BUFFER_MINUTES}min = {total_timeout}min"
    )
    
    return total_timeout


async def check_assignment_timeouts() -> List[int]:
    """
    Check for assignment attempts that have timed out based on incident priority.
    
    IMPORTANT: This does NOT reject the incident or prevent workshop from accepting.
    Instead, it:
    1. Marks assignment_attempt as 'timeout' (workshop can still accept)
    2. Emits IncidentAssignmentTimeoutEvent
    3. Triggers automatic reassignment to another workshop
    4. Both workshops can now accept (first one wins)
    
    Returns:
        List of incident IDs that timed out and need reassignment
    """
    session_factory = get_session_factory()
    timed_out_incidents = []
    
    try:
        async with session_factory() as session:
            now = datetime.now(UTC)
            
            # Find pending assignment attempts
            # ✅ EXCLUIR incidentes que ya están en 'sin_taller_disponible'
            result = await session.execute(
                select(AssignmentAttempt, Incidente)
                .join(Incidente, AssignmentAttempt.incident_id == Incidente.id)
                .where(
                    and_(
                        AssignmentAttempt.status == 'pending',
                        Incidente.estado_actual == 'pendiente',
                    )
                )
            )
            
            attempts_with_incidents = result.all()
            
            if not attempts_with_incidents:
                return timed_out_incidents
            
            logger.debug(f"🔍 Checking {len(attempts_with_incidents)} pending assignment attempts for timeout")
            
            for attempt, incident in attempts_with_incidents:
                try:
                    # Get timeout duration based on incident priority
                    priority = incident.prioridad_ia or "media"  # Default to media if not set
                    timeout_minutes = TIMEOUT_BY_PRIORITY.get(priority, DEFAULT_TIMEOUT_MINUTES)
                    
                    timeout_threshold = attempt.timeout_at
                    if timeout_threshold is None and attempt.attempted_at is not None:
                        timeout_threshold = attempt.attempted_at + timedelta(minutes=timeout_minutes)

                    if timeout_threshold is None:
                        logger.warning(
                            f"⚠️ Skipping timeout check for attempt {attempt.id} - no timeout reference available"
                        )
                        continue
                    
                    # Check if timed out
                    if now >= timeout_threshold:
                        # ✅ Mark assignment attempt as 'timeout' (NOT rejected)
                        # Workshop can still accept, but we'll try another workshop too
                        attempt.status = 'timeout'
                        attempt.responded_at = now
                        attempt.response_message = f'Timeout after {timeout_minutes} minutes (priority: {priority})'
                        incident.taller_id = None
                        
                        logger.info(
                            f"⏰ Assignment timeout: incident {incident.id}, workshop {attempt.workshop_id}, "
                            f"priority={priority}, timeout={timeout_minutes}min, mode={incident.assignment_mode}"
                        )
                        
                        # Publish timeout event
                        timeout_event = IncidentAssignmentTimeoutEvent(
                            incident_id=incident.id,
                            workshop_id=attempt.workshop_id,
                            workshop_name=f"Workshop {attempt.workshop_id}",
                            timeout_minutes=timeout_minutes,
                            assignment_mode=incident.assignment_mode,
                        )
                        await EventPublisher.publish(session, timeout_event)
                        
                        # MODO MANUAL: no reasignar automáticamente, solo limpiar taller y notificar
                        if incident.assignment_mode == 'manual':
                            logger.info(
                                f"📋 Manual mode timeout for incident {incident.id} — "
                                f"clearing workshop and notifying client"
                            )
                            incident.taller_id = None
                            continue
                        
                        # MODO AUTO: añadir a lista para reasignación automática
                        timed_out_incidents.append(incident.id)
                        
                except Exception as e:
                    logger.error(
                        f"Error processing timeout for attempt {attempt.id}: {str(e)}",
                        exc_info=True
                    )
                    continue
            
            # Commit all timeout status changes
            await session.commit()
            
            if timed_out_incidents:
                logger.info(
                    f"✅ Marked {len(timed_out_incidents)} assignment attempts as timeout: {timed_out_incidents}"
                )
                logger.info(
                    f"🔄 These incidents will be reassigned to other workshops automatically"
                )
            
            return timed_out_incidents
            
    except Exception as e:
        logger.error(f"❌ Error in check_assignment_timeouts: {str(e)}", exc_info=True)
        return []


async def trigger_reassignment_for_timeouts(incident_ids: List[int]) -> None:
    """
    Trigger automatic reassignment for incidents that timed out.
    
    CASCADING LOGIC:
    - Tries to assign to the NEXT available workshop in the list
    - If successful → workshop gets X minutes to respond
    - If no more workshops available → marks as 'sin_taller_disponible'
    - Notifies ADMIN when incident reaches 'sin_taller_disponible'
    
    Args:
        incident_ids: List of incident IDs that need reassignment
    """
    if not incident_ids:
        return
    
    session_factory = get_session_factory()
    
    try:
        async with session_factory() as session:
            from ..modules.assignment.reassignment_service import ReassignmentService
            
            for incident_id in incident_ids:
                try:
                    logger.info(f"🔄 Attempting cascading reassignment for incident {incident_id} after timeout")

                    incident = await session.get(Incidente, incident_id)
                    if not incident:
                        logger.warning(f"⚠️ Incident {incident_id} not found during timeout reassignment")
                        continue

                    if incident.estado_actual != 'pendiente':
                        logger.info(
                            f"⏭️ Skipping timeout reassignment for incident {incident_id} - "
                            f"state is '{incident.estado_actual}'"
                        )
                        continue

                    timeout_attempt_result = await session.execute(
                        select(AssignmentAttempt)
                        .where(
                            and_(
                                AssignmentAttempt.incident_id == incident_id,
                                AssignmentAttempt.status == 'timeout',
                            )
                        )
                        .order_by(
                            AssignmentAttempt.responded_at.desc(),
                            AssignmentAttempt.attempted_at.desc(),
                            AssignmentAttempt.created_at.desc(),
                        )
                        .limit(1)
                    )
                    timeout_attempt = timeout_attempt_result.scalar_one_or_none()
                    if not timeout_attempt:
                        logger.info(
                            f"⏭️ Skipping timeout reassignment for incident {incident_id} - "
                            f"no timeout attempt found"
                        )
                        continue

                    reassignment_service = ReassignmentService(session)
                    result = await reassignment_service.handle_timeout(
                        incident_id=incident_id,
                        workshop_id=timeout_attempt.workshop_id,
                    )
                    
                    if result.success:
                        logger.info(
                            f"✅ Cascading reassignment successful for incident {incident_id}: "
                            f"next workshop={result.assigned_workshop.workshop_name}"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Cascading reassignment failed for incident {incident_id}: {result.error_message}"
                        )

                        refreshed_incident = await session.get(Incidente, incident_id)
                        if refreshed_incident and refreshed_incident.estado_actual == 'sin_taller_disponible':
                            logger.info(
                                f"ℹ️ Incident {incident_id} already marked as sin_taller_disponible"
                            )
                            continue

                        if result.error_message and (
                            "No available workshops" in result.error_message
                            or "after exclusions" in result.error_message
                        ):
                            await _mark_incident_no_workshop_available(session, incident_id)
                            await _notify_admin_no_workshop(session, incident_id)
                        
                except Exception as e:
                    logger.error(
                        f"❌ Error in cascading reassignment for incident {incident_id}: {str(e)}",
                        exc_info=True
                    )
                    continue
                    
    except Exception as e:
        logger.error(f"❌ Error in trigger_reassignment_for_timeouts: {str(e)}", exc_info=True)


async def find_dangling_timeout_incidents() -> List[int]:
    """
    Recover incidents stuck in auto mode with a timeout attempt but no new pending attempt.

    This covers races where a timeout was already marked/published, but reassignment
    did not continue afterward.
    """
    session_factory = get_session_factory()
    try:
        async with session_factory() as session:
            timeout_result = await session.execute(
                select(AssignmentAttempt.incident_id)
                .join(Incidente, AssignmentAttempt.incident_id == Incidente.id)
                .where(
                    and_(
                        AssignmentAttempt.status == 'timeout',
                        Incidente.estado_actual == 'pendiente',
                        Incidente.assignment_mode == 'auto',
                    )
                )
                .distinct()
            )
            timeout_incident_ids = [row[0] for row in timeout_result.all()]
            if not timeout_incident_ids:
                return []

            pending_result = await session.execute(
                select(AssignmentAttempt.incident_id)
                .where(
                    and_(
                        AssignmentAttempt.incident_id.in_(timeout_incident_ids),
                        AssignmentAttempt.status == 'pending',
                    )
                )
                .distinct()
            )
            pending_incident_ids = {row[0] for row in pending_result.all()}

            dangling_ids = [
                incident_id
                for incident_id in timeout_incident_ids
                if incident_id not in pending_incident_ids
            ]

            if dangling_ids:
                logger.warning(
                    f"🔄 Found {len(dangling_ids)} dangling timeout incident(s) pending reassignment: {dangling_ids}"
                )

            return dangling_ids
    except Exception as e:
        logger.error(f"❌ Error finding dangling timeout incidents: {str(e)}", exc_info=True)
        return []


async def _mark_incident_no_workshop_available(session: AsyncSession, incident_id: int) -> None:
    """
    Mark incident as 'sin_taller_disponible' when ALL workshops have been tried.
    
    This state means:
    - ALL available workshops were contacted
    - NONE of them accepted within timeout
    - Only ADMIN can see and manually assign these incidents
    
    Args:
        session: Database session
        incident_id: ID of the incident
    """
    try:
        result = await session.execute(
            select(Incidente).where(Incidente.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        
        if not incident:
            return
        
        # Change state to 'sin_taller_disponible'
        old_state = incident.estado_actual
        incident.estado_actual = "sin_taller_disponible"
        incident.taller_id = None
        incident.tecnico_id = None
        incident.updated_at = datetime.now(UTC)
        
        # ✅ CANCELAR todos los assignment attempts pendientes y en timeout
        await session.execute(
            update(AssignmentAttempt)
            .where(
                and_(
                    AssignmentAttempt.incident_id == incident_id,
                    AssignmentAttempt.status.in_(['pending', 'timeout'])
                )
            )
            .values(
                status='cancelled',
                response_message='Incident marked as sin_taller_disponible - no workshops available'
            )
        )
        
        logger.info(
            f"✅ Cancelled all pending/timeout assignment attempts for incident {incident_id}"
        )
        
        # Publish status change event
        status_event = IncidentStatusChangedEvent(
            incident_id=incident_id,
            old_status=old_state,
            new_status="sin_taller_disponible",
            changed_by=0,  # System
            changed_by_role="admin",
            reason="All available workshops were contacted but none accepted within timeout"
        )
        await EventPublisher.publish(session, status_event)
        
        await session.commit()
        
        logger.warning(
            f"⚠️ Incident {incident_id} marked as 'sin_taller_disponible' - "
            f"ALL workshops tried, NONE accepted. Admin notification sent."
        )
        
    except Exception as e:
        logger.error(
            f"Error marking incident {incident_id} as no workshop available: {str(e)}",
            exc_info=True
        )


async def _notify_admin_no_workshop(session: AsyncSession, incident_id: int) -> None:
    """
    Notify ADMIN when incident reaches 'sin_taller_disponible' state.
    
    Only administrators can see and manually handle these incidents.
    
    Args:
        session: Database session
        incident_id: ID of the incident
    """
    try:
        # Get incident details
        result = await session.execute(
            select(Incidente).where(Incidente.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        
        if not incident:
            return
        
        # Create admin notification event
        from ..shared.schemas.events.dashboard import DashboardAlertTriggeredEvent
        
        alert_event = DashboardAlertTriggeredEvent(
            alert_type="no_workshop_available",
            severity="critical",
            message=f"Incident #{incident_id} has NO available workshops. Manual assignment required.",
            data={
                "incident_id": incident_id,
                "client_id": incident.client_id,
                "priority": incident.prioridad_ia or "unknown",
                "location": {
                    "latitude": float(incident.latitude),
                    "longitude": float(incident.longitude)
                },
                "description": incident.descripcion[:100] + "..." if len(incident.descripcion) > 100 else incident.descripcion
            }
        )
        
        await EventPublisher.publish(session, alert_event)
        await session.commit()
        
        logger.critical(
            f"🚨 ADMIN ALERT: Incident {incident_id} has no available workshops! "
            f"Priority: {incident.prioridad_ia}, Client: {incident.client_id}"
        )
        
    except Exception as e:
        logger.error(
            f"Error notifying admin for incident {incident_id}: {str(e)}",
            exc_info=True
        )


# ═══════════════════════════════════════════════════════════════════════════
# TRACKING TIMEOUTS
# ═══════════════════════════════════════════════════════════════════════════

async def check_tracking_timeouts() -> List[int]:
    """
    Check for active tracking sessions that exceed their DYNAMIC timeout.
    
    DYNAMIC TIMEOUT CALCULATION:
    - Gets distance from assignment_attempt (distance_km)
    - Gets category from incident AI analysis (categoria_ia)
    - Calculates: Travel Time + Service Duration + Buffer
    - Example: 5km + bateria = 10min travel + 30min service + 10min buffer = 50min total
    
    This function:
    1. Finds active tracking sessions
    2. Gets distance and category for each incident
    3. Calculates dynamic timeout based on distance + category
    4. Auto-closes sessions that exceed their calculated timeout
    5. Frees technician and updates incident status
    
    Returns:
        List of incident IDs that were auto-closed due to timeout
    """
    session_factory = get_session_factory()
    auto_closed_incidents = []
    
    try:
        async with session_factory() as session:
            now = datetime.now(UTC)
            
            # Find all active tracking sessions with incident and assignment data
            result = await session.execute(
                select(TrackingSession, Incidente, AssignmentAttempt)
                .join(Incidente, TrackingSession.incidente_id == Incidente.id)
                .outerjoin(
                    AssignmentAttempt,
                    and_(
                        AssignmentAttempt.incident_id == Incidente.id,
                        AssignmentAttempt.technician_id == TrackingSession.technician_id,
                        AssignmentAttempt.status == 'accepted'
                    )
                )
                .where(
                    and_(
                        TrackingSession.is_active == True,
                        TrackingSession.started_at.isnot(None),
                        TrackingSession.ended_at.is_(None)  # Not yet ended
                    )
                )
            )
            
            sessions_data = result.all()
            
            if not sessions_data:
                return auto_closed_incidents
            
            logger.debug(f"🔍 Checking {len(sessions_data)} active tracking sessions for dynamic timeout")
            
            for tracking_session, incident, assignment_attempt in sessions_data:
                session_id = tracking_session.id
                incident_id = incident.id
                try:
                    # Get incident details
                    category = incident.categoria_ia or "otros"
                    priority = incident.prioridad_ia or "media"
                    
                    # Get distance from assignment_attempt (if available)
                    distance_km = 0.0
                    if assignment_attempt and assignment_attempt.distance_km:
                        distance_km = float(assignment_attempt.distance_km)
                    else:
                        # Fallback: estimate based on average urban distance
                        distance_km = 5.0  # Default 5km if no distance data
                        logger.debug(
                            f"⚠️ No distance data for incident {incident.id}, using default {distance_km}km"
                        )
                    
                    # ✅ CALCULATE DYNAMIC TIMEOUT
                    timeout_minutes = calculate_dynamic_timeout(
                        distance_km=distance_km,
                        category=category,
                        priority=priority
                    )
                    
                    # Calculate timeout threshold for this specific incident
                    timeout_threshold = tracking_session.started_at + timedelta(minutes=timeout_minutes)
                    
                    # Check if session has exceeded its dynamic timeout
                    if now >= timeout_threshold:
                        # Calculate how long session has been running
                        time_since_start = now - tracking_session.started_at
                        minutes_since_start = int(time_since_start.total_seconds() / 60)
                        
                        logger.warning(
                            f"⏰ TRACKING TIMEOUT: Incident {incident.id} "
                            f"(category: {category}, distance: {distance_km:.2f}km, priority: {priority}), "
                            f"technician {tracking_session.technician_id}, "
                            f"session running for {minutes_since_start} minutes "
                            f"(dynamic timeout: {timeout_minutes} min). AUTO-CLOSING..."
                        )
                        
                        # ✅ AUTO-CLOSE: End tracking session
                        tracking_session.is_active = False
                        tracking_session.ended_at = now
                        
                        # ✅ FREE TECHNICIAN: Mark as available again
                        if tracking_session.technician_id:
                            technician = await session.get(Technician, tracking_session.technician_id)
                            if technician:
                                technician.is_on_duty = False
                                technician.is_available = True
                                technician.updated_at = now
                                
                                logger.info(
                                    f"✅ Technician {tracking_session.technician_id} freed "
                                    f"(is_on_duty=False, is_available=True) due to tracking timeout"
                                )
                        
                        # ✅ UPDATE INCIDENT: Mark as resolved if still in progress
                        # NOTE: "completado" is not a persisted DB state in this schema.
                        if incident.estado_actual in ["en_camino", "en_proceso"]:
                            old_status = incident.estado_actual
                            incident.estado_actual = "resuelto"
                            incident.updated_at = now
                            
                            logger.info(
                                f"✅ Incident {incident.id} auto-resolved due to tracking timeout "
                                f"({old_status} → resuelto)"
                            )
                            
                            # Publish status change event
                            from ..shared.schemas.events.incident import IncidentStatusChangedEvent
                            status_event = IncidentStatusChangedEvent(
                                incident_id=incident.id,
                                old_status=old_status,
                                new_status="resuelto",
                                changed_by=0,  # System
                                changed_by_role="admin",
                                reason=(
                                    f"Auto-completed after {minutes_since_start} minutes "
                                    f"(dynamic timeout: {timeout_minutes} min for {distance_km:.2f}km + {category})"
                                )
                            )
                            await EventPublisher.publish(session, status_event)
                        
                        auto_closed_incidents.append(incident.id)
                        
                        # TODO: Send notification to workshop/technician about auto-closure
                        # TODO: Send notification to client that service is complete
                        
                    else:
                        # Session is still within timeout - log progress for monitoring
                        time_since_start = now - tracking_session.started_at
                        minutes_since_start = int(time_since_start.total_seconds() / 60)
                        remaining_minutes = timeout_minutes - minutes_since_start
                        
                        if remaining_minutes <= 15 and minutes_since_start % 5 == 0:
                            # Log warning when close to timeout (every 5 minutes in last 15 minutes)
                            logger.debug(
                                f"⚠️ Tracking session for incident {incident.id} "
                                f"(category: {category}, distance: {distance_km:.2f}km) "
                                f"has {remaining_minutes} minutes remaining before auto-close "
                                f"(dynamic timeout: {timeout_minutes} min)"
                            )
                    
                except Exception as e:
                    # Reset failed transaction state so next iterations can continue safely.
                    await session.rollback()
                    logger.error(
                        f"Error processing tracking timeout for session {session_id} (incident {incident_id}): {str(e)}",
                        exc_info=True
                    )
                    continue
            
            # Commit all changes (session closures, technician updates, incident updates)
            await session.commit()
            
            if auto_closed_incidents:
                logger.warning(
                    f"🔒 AUTO-CLOSED {len(auto_closed_incidents)} tracking sessions due to dynamic timeout: {auto_closed_incidents}"
                )
            else:
                logger.debug("✅ All tracking sessions are within their dynamic timeouts")
            
            return auto_closed_incidents
            
    except Exception as e:
        logger.error(f"❌ Error in check_tracking_timeouts: {str(e)}", exc_info=True)
        return []


# ═══════════════════════════════════════════════════════════════════════════
# COMBINED TIMEOUT CHECK (for scheduler)
# ═══════════════════════════════════════════════════════════════════════════

async def check_all_timeouts():
    """
    Combined timeout check function for scheduler.
    
    This function:
    1. Checks for assignment timeouts (workshop response time)
       - Based on incident priority (alta: 3min, media: 5min, baja: 10min)
       - Triggers automatic reassignment to next workshop
    
    2. Checks for tracking timeouts (service duration)
       - Based on incident category (bateria: 30min, motor: 180min, etc.)
       - Auto-closes sessions that exceed category-specific timeout
       - Frees technician and marks incident as completed
    
    Should be called periodically by APScheduler (every 30 seconds recommended).
    """
    logger.debug("🔍 Running state machine timeout checks...")
    
    try:
        # Check assignment timeouts (workshop response)
        timed_out_incident_ids = await check_assignment_timeouts()
        dangling_timeout_incident_ids = await find_dangling_timeout_incidents()
        incident_ids_to_reassign = list(
            dict.fromkeys(timed_out_incident_ids + dangling_timeout_incident_ids)
        )
        
        # Trigger reassignment for timed out incidents
        if incident_ids_to_reassign:
            await trigger_reassignment_for_timeouts(incident_ids_to_reassign)
        
        # Check tracking timeouts (service duration) with auto-close
        auto_closed_incidents = await check_tracking_timeouts()
        
        if incident_ids_to_reassign or auto_closed_incidents:
            logger.info(
                f"✅ Timeout check complete: "
                f"{len(incident_ids_to_reassign)} assignment timeouts/recoveries (reassigned), "
                f"{len(auto_closed_incidents)} tracking sessions auto-closed"
            )
        
    except Exception as e:
        logger.error(f"❌ Error in check_all_timeouts: {str(e)}", exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULER CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# NOTE: Scheduler is configured in app/main.py using check_all_timeouts()
# This unified approach runs both assignment and tracking checks every 30 seconds
# for better precision and simpler maintenance.
#
# The old separate scheduler configuration has been removed to avoid duplication.
