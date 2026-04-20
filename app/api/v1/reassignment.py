"""
Reassignment API endpoints for manual intervention and monitoring.
"""
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from ...core.database import get_db_session
from ...core.dependencies import get_current_user, require_permission
from ...core.permissions import Permission
from ...core.responses import create_success_response
from ...core.logging import get_logger
from ...models.user import User
from ...models.assignment_attempt import AssignmentAttempt
from ...models.workshop import Workshop
from ...models.technician import Technician
from ...schemas.reassignment import (
    ReassignmentRequest,
    ReassignmentResponse,
    AssignmentHistoryResponse,
    AssignmentHistoryItem,
    TimeoutCheckResponse,
)
from ...services.reassignment_service import ReassignmentService

logger = get_logger(__name__)
router = APIRouter(prefix="/reassignment", tags=["Reassignment"])


@router.post(
    "/incidents/{incident_id}/force-reassign",
    response_model=ReassignmentResponse,
    summary="Force manual reassignment",
    description="Administrator can manually force reassignment of an incident",
    dependencies=[Depends(require_permission(Permission.ADMIN_FORCE_REASSIGN))],
)
async def force_reassign_incident(
    incident_id: int,
    request: ReassignmentRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Force manual reassignment of an incident.
    
    This endpoint allows administrators to manually trigger reassignment
    even if the incident is already assigned or has not timed out yet.
    
    Use cases:
    - Workshop is not responding but timeout hasn't occurred yet
    - Need to reassign due to workshop capacity issues
    - Emergency reassignment for high priority incidents
    """
    logger.info(
        f"🔧 Manual reassignment requested by admin {current_user.email} "
        f"for incident {incident_id}"
    )
    
    reassignment_service = ReassignmentService(session)
    
    # Force reassignment by recalculating candidates
    result = await reassignment_service.reassign_to_next_candidate(incident_id)
    
    # Get excluded workshops count
    excluded = await reassignment_service.assignment_service._get_excluded_workshops(incident_id)
    
    response = ReassignmentResponse(
        success=result.success,
        incident_id=incident_id,
        assigned_workshop_id=result.assigned_workshop.id if result.assigned_workshop else None,
        assigned_workshop_name=result.assigned_workshop.workshop_name if result.assigned_workshop else None,
        assigned_technician_id=result.assigned_technician.id if result.assigned_technician else None,
        assigned_technician_name=(
            f"{result.assigned_technician.first_name} {result.assigned_technician.last_name}"
            if result.assigned_technician else None
        ),
        strategy_used=result.strategy_used.value if result.strategy_used else None,
        candidates_evaluated=result.candidates_evaluated,
        excluded_workshops_count=len(excluded),
        reasoning=result.reasoning or request.reason,
        error_message=result.error_message,
        requires_manual_intervention=not result.success,
    )
    
    if result.success:
        logger.info(
            f"✅ Manual reassignment successful: incident {incident_id} → "
            f"workshop {response.assigned_workshop_name}"
        )
        return create_success_response(
            data=response.model_dump(),
            message=f"Incident successfully reassigned to {response.assigned_workshop_name}",
        )
    else:
        logger.warning(
            f"⚠️ Manual reassignment failed for incident {incident_id}: {result.error_message}"
        )
        return create_success_response(
            data=response.model_dump(),
            message=f"Reassignment failed: {result.error_message}",
        )


@router.get(
    "/incidents/{incident_id}/assignment-history",
    response_model=AssignmentHistoryResponse,
    summary="Get assignment history",
    description="Get complete assignment history for an incident",
    dependencies=[Depends(require_permission(Permission.EMERGENCY_VIEW_OWN))],
)
async def get_assignment_history(
    incident_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get complete assignment history for an incident.
    
    Shows all assignment attempts including:
    - Successful assignments
    - Rejections with reasons
    - Timeouts
    - Pending assignments
    """
    # Get all assignment attempts for this incident
    result = await session.execute(
        select(AssignmentAttempt)
        .where(AssignmentAttempt.incident_id == incident_id)
        .order_by(AssignmentAttempt.attempted_at.desc())
    )
    attempts = list(result.scalars().all())
    
    if not attempts:
        return create_success_response(
            data=AssignmentHistoryResponse(
                incident_id=incident_id,
                total_attempts=0,
                successful_attempts=0,
                rejected_attempts=0,
                timeout_attempts=0,
                pending_attempts=0,
                attempts=[],
            ).model_dump(),
            message="No assignment attempts found for this incident",
        )
    
    # Get workshop and technician details
    history_items = []
    for attempt in attempts:
        # Get workshop
        workshop = await session.get(Workshop, attempt.workshop_id)
        
        # Get technician if assigned
        technician = None
        if attempt.technician_id:
            technician = await session.get(Technician, attempt.technician_id)
        
        history_items.append(
            AssignmentHistoryItem(
                id=attempt.id,
                workshop_id=attempt.workshop_id,
                workshop_name=workshop.workshop_name if workshop else "Unknown",
                technician_id=attempt.technician_id,
                technician_name=(
                    f"{technician.first_name} {technician.last_name}"
                    if technician else None
                ),
                algorithmic_score=float(attempt.algorithmic_score),
                ai_score=float(attempt.ai_score) if attempt.ai_score else None,
                final_score=float(attempt.final_score),
                assignment_strategy=attempt.assignment_strategy,
                distance_km=float(attempt.distance_km),
                status=attempt.status,
                response_message=attempt.response_message,
                attempted_at=attempt.attempted_at,
                responded_at=attempt.responded_at,
                timeout_at=attempt.timeout_at,
            )
        )
    
    # Calculate statistics
    status_counts = {
        "accepted": 0,
        "rejected": 0,
        "timeout": 0,
        "pending": 0,
    }
    
    for attempt in attempts:
        if attempt.status in status_counts:
            status_counts[attempt.status] += 1
    
    response = AssignmentHistoryResponse(
        incident_id=incident_id,
        total_attempts=len(attempts),
        successful_attempts=status_counts["accepted"],
        rejected_attempts=status_counts["rejected"],
        timeout_attempts=status_counts["timeout"],
        pending_attempts=status_counts["pending"],
        attempts=history_items,
    )
    
    return create_success_response(
        data=response.model_dump(),
        message=f"Found {len(attempts)} assignment attempts",
    )


@router.post(
    "/check-timeouts",
    response_model=TimeoutCheckResponse,
    summary="Manually check for timeouts",
    description="Manually trigger timeout check (normally runs automatically every minute)",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANUAL_INTERVENTION))],
)
async def manual_timeout_check(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Manually trigger timeout check.
    
    This endpoint allows administrators to manually check for timed out
    assignments without waiting for the background task.
    
    Useful for:
    - Testing the timeout system
    - Immediate response to urgent situations
    - Debugging timeout issues
    """
    logger.info(f"⏰ Manual timeout check requested by admin {current_user.email}")
    
    reassignment_service = ReassignmentService(session)
    timed_out_incidents = await reassignment_service.check_timeouts()
    
    if timed_out_incidents:
        logger.warning(f"⏰ Found {len(timed_out_incidents)} timed out incidents")
        
        # Trigger reassignment for each
        for incident_id in timed_out_incidents:
            logger.info(f"🔄 Reassigning timed out incident {incident_id}...")
            result = await reassignment_service.reassign_to_next_candidate(incident_id)
            
            if result.success:
                logger.info(f"✅ Reassigned incident {incident_id}")
            else:
                logger.warning(f"⚠️ Failed to reassign incident {incident_id}")
    
    response = TimeoutCheckResponse(
        timed_out_incidents=timed_out_incidents,
        count=len(timed_out_incidents),
    )
    
    return create_success_response(
        data=response.model_dump(),
        message=f"Found and processed {len(timed_out_incidents)} timed out incidents",
    )


@router.get(
    "/statistics",
    summary="Get reassignment statistics",
    description="Get overall statistics about the reassignment system",
    dependencies=[Depends(require_permission(Permission.ADMIN_MANUAL_INTERVENTION))],
)
async def get_reassignment_statistics(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get overall statistics about the reassignment system.
    
    Provides insights into:
    - Total assignment attempts
    - Success/failure rates
    - Average attempts per incident
    - Timeout rates
    - Rejection rates
    """
    # Total attempts
    total_result = await session.execute(
        select(func.count(AssignmentAttempt.id))
    )
    total_attempts = total_result.scalar_one()
    
    # Attempts by status
    status_result = await session.execute(
        select(
            AssignmentAttempt.status,
            func.count(AssignmentAttempt.id)
        )
        .group_by(AssignmentAttempt.status)
    )
    status_counts = {row[0]: row[1] for row in status_result.all()}
    
    # Average attempts per incident
    avg_result = await session.execute(
        select(
            func.count(AssignmentAttempt.id).label('attempts'),
            AssignmentAttempt.incident_id
        )
        .group_by(AssignmentAttempt.incident_id)
    )
    attempt_counts = [row[0] for row in avg_result.all()]
    avg_attempts = sum(attempt_counts) / len(attempt_counts) if attempt_counts else 0
    
    # Calculate rates
    success_rate = (
        (status_counts.get('accepted', 0) / total_attempts * 100)
        if total_attempts > 0 else 0
    )
    rejection_rate = (
        (status_counts.get('rejected', 0) / total_attempts * 100)
        if total_attempts > 0 else 0
    )
    timeout_rate = (
        (status_counts.get('timeout', 0) / total_attempts * 100)
        if total_attempts > 0 else 0
    )
    
    statistics = {
        "total_attempts": total_attempts,
        "status_breakdown": status_counts,
        "average_attempts_per_incident": round(avg_attempts, 2),
        "success_rate_percent": round(success_rate, 2),
        "rejection_rate_percent": round(rejection_rate, 2),
        "timeout_rate_percent": round(timeout_rate, 2),
        "incidents_with_multiple_attempts": len([c for c in attempt_counts if c > 1]),
        "max_attempts_for_single_incident": max(attempt_counts) if attempt_counts else 0,
    }
    
    return create_success_response(
        data=statistics,
        message="Reassignment statistics retrieved successfully",
    )
