"""Background job to clean up stuck AI analyses."""

from datetime import datetime, UTC, timedelta

from sqlalchemy import select

from ...core import get_logger, get_session_factory
from ...core.event_publisher import EventPublisher
from ...models.incident_ai_analysis import IncidentAIAnalysis
from ...shared.schemas.events.incident import IncidentAnalysisTimeoutEvent

logger = get_logger(__name__)


async def cleanup_stuck_analyses(stuck_threshold_minutes: int = 5) -> int:
    """
    Clean up AI analyses stuck in 'processing' state for more than threshold minutes.
    
    This job should run periodically via a scheduler (e.g., APScheduler).
    
    Args:
        stuck_threshold_minutes: Minutes after which an analysis is considered stuck
        
    Returns:
        Number of stuck analyses cleaned up
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Find analyses stuck in processing for more than threshold
        threshold_time = datetime.now(UTC) - timedelta(minutes=stuck_threshold_minutes)
        
        result = await session.execute(
            select(IncidentAIAnalysis)
            .where(IncidentAIAnalysis.status == "processing")
            .where(IncidentAIAnalysis.updated_at < threshold_time)
        )
        stuck_analyses = result.scalars().all()
        
        if not stuck_analyses:
            logger.debug("No stuck AI analyses found")
            return 0
        
        logger.warning(
            f"Found {len(stuck_analyses)} stuck AI analyses. Marking as timeout...",
            count=len(stuck_analyses),
            threshold_minutes=stuck_threshold_minutes
        )
        
        # Mark as timeout
        for analysis in stuck_analyses:
            analysis.status = "timeout"
            analysis.error_code = "STUCK_PROCESSING"
            analysis.error_message = (
                f"Analysis was stuck in processing state for more than {stuck_threshold_minutes} minutes. "
                f"Last updated: {analysis.updated_at.isoformat()}"
            )
            
            logger.warning(
                f"Marked analysis {analysis.id} as timeout (incident {analysis.incident_id})",
                analysis_id=analysis.id,
                incident_id=analysis.incident_id,
                stuck_duration_minutes=int((datetime.now(UTC) - analysis.updated_at).total_seconds() / 60)
            )
            
            # Publish timeout event
            try:
                timeout_event = IncidentAnalysisTimeoutEvent(
                    incident_id=analysis.incident_id,
                    analysis_id=analysis.id,
                    timeout_seconds=stuck_threshold_minutes * 60
                )
                await EventPublisher.publish(session, timeout_event)
            except Exception as e:
                logger.error(
                    f"Error publishing timeout event for analysis {analysis.id}: {str(e)}",
                    exc_info=True
                )
        
        await session.commit()
        
        logger.info(
            f"✅ Cleaned up {len(stuck_analyses)} stuck AI analyses",
            count=len(stuck_analyses)
        )
        
        return len(stuck_analyses)


async def get_stuck_analyses_count(stuck_threshold_minutes: int = 5) -> int:
    """
    Get count of analyses stuck in 'processing' state.
    
    Args:
        stuck_threshold_minutes: Minutes after which an analysis is considered stuck
        
    Returns:
        Number of stuck analyses
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        threshold_time = datetime.now(UTC) - timedelta(minutes=stuck_threshold_minutes)
        
        result = await session.execute(
            select(IncidentAIAnalysis)
            .where(IncidentAIAnalysis.status == "processing")
            .where(IncidentAIAnalysis.updated_at < threshold_time)
        )
        stuck_analyses = result.scalars().all()
        
        return len(stuck_analyses)
