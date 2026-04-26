"""
Events API endpoint for missed events recovery.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from ...core.database import get_db_session
from ...core.dependencies import get_current_user
from ...models.user import User
from ...models.event_log import EventLog
from ...models.incidente import Incidente
from ...core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/events")


@router.get("/missed")
async def get_missed_events(
    since: str = Query(..., description="ISO 8601 timestamp of last received event"),
    incident_id: Optional[int] = Query(None, description="Filter by specific incident"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of events to return"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """
    Get events that occurred since a specific timestamp.
    
    This endpoint allows clients to recover events they missed during disconnection.
    
    Query Parameters:
        since: ISO 8601 timestamp (e.g., "2026-04-22T10:30:00Z")
        incident_id: Optional incident ID to filter events
        limit: Maximum number of events (default 100, max 500)
    
    Returns:
        List of events in chronological order
    """
    try:
        # Parse timestamp and convert to naive UTC (database uses TIMESTAMP WITHOUT TIME ZONE)
        since_dt_aware = datetime.fromisoformat(since.replace('Z', '+00:00'))
        since_dt = since_dt_aware.replace(tzinfo=None)  # Convert to naive
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid timestamp format. Use ISO 8601 format (e.g., '2026-04-22T10:30:00Z')"
        )
    
    # Validate timestamp is not too old (max 7 days)
    max_age = datetime.utcnow() - timedelta(days=7)
    if since_dt < max_age:
        raise HTTPException(
            status_code=400,
            detail="Timestamp is too old. Maximum age is 7 days."
        )
    
    logger.info(
        f"User {current_user.id} requesting missed events since {since_dt.isoformat()}"
        f"{f' for incident {incident_id}' if incident_id else ''}"
    )
    
    # Build query for event_log (which tracks all delivered events)
    query = select(EventLog).where(
        and_(
            EventLog.delivered_at > since_dt,
            EventLog.delivered_at <= datetime.utcnow(),
            EventLog.delivered_to == current_user.id  # Only events delivered to this user
        )
    )
    
    # Filter by incident if specified
    if incident_id:
        # Verify user has access to this incident
        incident = await session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )
        
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        has_access = (
            incident.client_id == current_user.id or
            incident.taller_id == current_user.id or
            incident.tecnico_id == current_user.id or
            current_user.user_type == "administrator"
        )
        
        if not has_access:
            raise HTTPException(
                status_code=403,
                detail="You don't have access to this incident"
            )
        
        # Filter event logs related to this incident
        # Parse payload JSON to check for incident_id
        import json
        query = query.where(
            EventLog.payload.contains(f'"incident_id": {incident_id}')
        )
    
    # Order by delivered_at and limit
    query = query.order_by(EventLog.delivered_at.asc()).limit(limit)
    
    # Execute query
    result = await session.scalars(query)
    event_logs = result.all()
    
    # Convert event logs to event format
    import json
    events = []
    for log in event_logs:
        try:
            payload_data = json.loads(log.payload)
            event = {
                "type": log.event_type,
                "data": payload_data,
                "timestamp": log.delivered_at.isoformat(),
                "version": "1.0",
                "delivered_via": log.delivered_via
            }
            events.append(event)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse event log {log.id} payload")
            continue
    
    logger.info(
        f"Returning {len(events)} missed events for user {current_user.id}"
    )
    
    return {
        "events": events,
        "count": len(events),
        "since": since_dt.isoformat() + 'Z',
        "until": datetime.utcnow().isoformat() + 'Z',
        "has_more": len(events) == limit
    }
