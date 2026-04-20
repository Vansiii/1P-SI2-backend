"""
Assignment API endpoints for intelligent workshop assignment.
Provides automatic assignment capabilities using hybrid AI approach.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user_payload
from ...core.database import get_db_session
from ...shared.dependencies.auth import get_current_user
from ...core.logging import get_logger
from ...models.user import User
from ...models.assignment_attempt import AssignmentAttempt
from .services import IntelligentAssignmentService, AssignmentResult, AssignmentStrategy
from ...modules.incidentes.ai_service import IncidentAIService

logger = get_logger(__name__)
router = APIRouter(prefix="/assignment", tags=["assignment"])


class AutoAssignmentRequest(BaseModel):
    """Request for automatic assignment."""
    force_ai_analysis: bool = Field(
        default=False,
        description="Force AI analysis even for simple cases"
    )


class AssignmentAttemptResponse(BaseModel):
    """Response model for assignment attempt."""
    id: int
    incident_id: int
    workshop_id: int
    technician_id: Optional[int]
    algorithmic_score: float
    ai_score: Optional[float]
    final_score: float
    assignment_strategy: str
    distance_km: float
    ai_reasoning: Optional[str]
    status: str
    response_message: Optional[str]
    attempted_at: datetime
    responded_at: Optional[datetime]
    timeout_at: Optional[datetime]


class AssignmentResultResponse(BaseModel):
    """Response model for assignment result."""
    success: bool
    assigned_workshop_id: Optional[int] = None
    assigned_technician_id: Optional[int] = None
    workshop_name: Optional[str] = None
    technician_name: Optional[str] = None
    strategy_used: Optional[str] = None
    candidates_evaluated: int = 0
    ai_analysis_used: bool = False
    reasoning: Optional[str] = None
    error_message: Optional[str] = None
    assignment_attempt_id: Optional[int] = None


class AssignmentStatisticsResponse(BaseModel):
    """Response model for assignment statistics."""
    assignments_last_24h: int
    pending_assignments: int
    available_workshops: int
    ai_enabled: bool
    max_distance_km: float
    timestamp: str


@router.post("/incidents/{incident_id}/assign-automatically")
async def assign_incident_automatically(
    incident_id: int,
    request: AutoAssignmentRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> AssignmentResultResponse:
    """
    Automatically assign incident to best available workshop using hybrid AI approach.
    
    This endpoint uses the intelligent assignment service to:
    1. Find available workshops within coverage area
    2. Score candidates using algorithmic factors (distance, availability, specialization)
    3. Apply AI analysis for complex cases (multiple similar candidates, ambiguous incidents)
    4. Select best candidate and execute assignment
    5. Send real-time notifications to all parties
    
    The system automatically determines when to use AI based on:
    - Multiple candidates with similar scores
    - Ambiguous or high-priority incidents
    - Force flag in request
    """
    try:
        assignment_service = IntelligentAssignmentService(session)
        
        # Execute automatic assignment
        result = await assignment_service.assign_incident_automatically(
            incident_id=incident_id,
            force_ai_analysis=request.force_ai_analysis
        )
        
        # Log assignment attempt for tracking
        if result.success:
            assignment_attempt = await _log_assignment_attempt(
                session=session,
                incident_id=incident_id,
                result=result
            )
            assignment_attempt_id = assignment_attempt.id if assignment_attempt else None
        else:
            assignment_attempt_id = None
        
        # Build response
        response = AssignmentResultResponse(
            success=result.success,
            assigned_workshop_id=result.assigned_workshop.id if result.assigned_workshop else None,
            assigned_technician_id=result.assigned_technician.id if result.assigned_technician else None,
            workshop_name=result.assigned_workshop.workshop_name if result.assigned_workshop else None,
            technician_name=f"{result.assigned_technician.first_name} {result.assigned_technician.last_name}" if result.assigned_technician else None,
            strategy_used=result.strategy_used.value if result.strategy_used else None,
            candidates_evaluated=result.candidates_evaluated,
            ai_analysis_used=result.ai_analysis_used,
            reasoning=result.reasoning,
            error_message=result.error_message,
            assignment_attempt_id=assignment_attempt_id
        )
        
        if result.success:
            logger.info(
                f"Automatic assignment successful for incident {incident_id}: "
                f"workshop={result.assigned_workshop.workshop_name}, "
                f"technician={result.assigned_technician.first_name} {result.assigned_technician.last_name}, "
                f"strategy={result.strategy_used.value}"
            )
        else:
            logger.warning(
                f"Automatic assignment failed for incident {incident_id}: {result.error_message}"
            )
        
        return response
        
    except Exception as e:
        logger.error(f"Assignment API error for incident {incident_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Assignment process failed: {str(e)}"
        )


@router.get("/incidents/{incident_id}/attempts")
async def get_assignment_attempts(
    incident_id: int,
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of attempts to return"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> List[AssignmentAttemptResponse]:
    """
    Get assignment attempts history for an incident.
    
    Returns chronological list of assignment attempts including:
    - Scoring details (algorithmic, AI, final)
    - Assignment strategy used
    - Status and response information
    - Timing information
    """
    try:
        from sqlalchemy import select, desc
        
        result = await session.execute(
            select(AssignmentAttempt)
            .where(AssignmentAttempt.incident_id == incident_id)
            .order_by(desc(AssignmentAttempt.attempted_at))
            .limit(limit)
        )
        attempts = list(result.scalars().all())
        
        return [
            AssignmentAttemptResponse(
                id=attempt.id,
                incident_id=attempt.incident_id,
                workshop_id=attempt.workshop_id,
                technician_id=attempt.technician_id,
                algorithmic_score=float(attempt.algorithmic_score),
                ai_score=float(attempt.ai_score) if attempt.ai_score else None,
                final_score=float(attempt.final_score),
                assignment_strategy=attempt.assignment_strategy,
                distance_km=float(attempt.distance_km),
                ai_reasoning=attempt.ai_reasoning,
                status=attempt.status,
                response_message=attempt.response_message,
                attempted_at=attempt.attempted_at,
                responded_at=attempt.responded_at,
                timeout_at=attempt.timeout_at
            )
            for attempt in attempts
        ]
        
    except Exception as e:
        logger.error(f"Error fetching assignment attempts for incident {incident_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch assignment attempts"
        )


@router.get("/statistics")
async def get_assignment_statistics(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> AssignmentStatisticsResponse:
    """
    Get assignment system statistics for monitoring and analytics.
    
    Returns:
    - Recent assignment activity (last 24 hours)
    - Current pending assignments
    - Available workshops count
    - AI system status
    - Configuration parameters
    """
    try:
        assignment_service = IntelligentAssignmentService(session)
        stats = await assignment_service.get_assignment_statistics()
        
        return AssignmentStatisticsResponse(
            assignments_last_24h=stats.get("assignments_last_24h", 0),
            pending_assignments=stats.get("pending_assignments", 0),
            available_workshops=stats.get("available_workshops", 0),
            ai_enabled=stats.get("ai_enabled", False),
            max_distance_km=stats.get("max_distance_km", 50.0),
            timestamp=stats.get("timestamp", datetime.utcnow().isoformat())
        )
        
    except Exception as e:
        logger.error(f"Error fetching assignment statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch assignment statistics"
        )


@router.post("/incidents/{incident_id}/trigger-ai-classification")
async def trigger_ai_classification(
    incident_id: int,
    force_reprocess: bool = Query(default=False, description="Force reprocessing even if already classified"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Manually trigger AI classification for an incident.
    
    This endpoint allows manual triggering of AI classification, useful for:
    - Reprocessing incidents with new evidence
    - Handling cases that failed automatic classification
    - Testing and debugging AI classification
    """
    try:
        ai_service = IncidentAIService(session)
        
        # Queue and process AI analysis
        analysis = await ai_service.queue_incident_processing(
            incident_id=incident_id,
            force_reprocess=force_reprocess
        )
        
        if analysis.status == "pending":
            # Process immediately
            analysis = await ai_service.process_analysis_by_id(analysis.id)
        
        return {
            "message": "AI classification completed",
            "incident_id": incident_id,
            "analysis_id": analysis.id,
            "status": analysis.status,
            "category": analysis.category,
            "priority": analysis.priority,
            "is_ambiguous": analysis.is_ambiguous,
            "confidence": float(analysis.confidence) if analysis.confidence else None,
            "error_message": analysis.error_message
        }
        
    except Exception as e:
        logger.error(f"Error triggering AI classification for incident {incident_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI classification failed: {str(e)}"
        )


async def _log_assignment_attempt(
    session: AsyncSession,
    incident_id: int,
    result: AssignmentResult
) -> Optional[AssignmentAttempt]:
    """Log successful assignment attempt for tracking."""
    try:
        if not result.success or not result.assigned_workshop or not result.assigned_technician:
            return None
        
        # Create assignment attempt record
        attempt = AssignmentAttempt(
            incident_id=incident_id,
            workshop_id=result.assigned_workshop.id,
            technician_id=result.assigned_technician.id,
            algorithmic_score=0.8,  # TODO: Get from result
            ai_score=0.9 if result.ai_analysis_used else None,  # TODO: Get from result
            final_score=0.85,  # TODO: Get from result
            assignment_strategy=result.strategy_used.value if result.strategy_used else "algorithm_only",
            distance_km=5.0,  # TODO: Get from result
            ai_reasoning=result.reasoning,
            status="accepted",  # Successful assignment
            response_message="Automatically assigned by system"
        )
        
        session.add(attempt)
        await session.commit()
        await session.refresh(attempt)
        
        return attempt
        
    except Exception as e:
        logger.error(f"Failed to log assignment attempt: {str(e)}")
        return None