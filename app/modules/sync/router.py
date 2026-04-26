"""
Sync API endpoints for offline queue synchronization.
"""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from ...core.database import get_db
from ...core.dependencies import get_current_user
from ...core.logging import get_logger
from ...models.user import User

logger = get_logger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


class QueueOperation(BaseModel):
    """Single queued operation."""
    id: str = Field(..., description="Unique operation ID (UUID)")
    type: str = Field(..., description="Operation type")
    endpoint: str = Field(..., description="API endpoint")
    method: str = Field(..., description="HTTP method")
    body: Dict[str, Any] = Field(default_factory=dict, description="Request body")
    timestamp: int = Field(..., description="Unix timestamp when queued")
    retries: int = Field(default=0, description="Number of retry attempts")


class SyncBatchRequest(BaseModel):
    """Batch sync request with multiple operations."""
    operations: List[QueueOperation] = Field(..., description="List of queued operations")


class OperationResult(BaseModel):
    """Result of a single operation."""
    id: str
    success: bool
    status_code: int | None = None
    error: str | None = None
    data: Dict[str, Any] | None = None


class SyncBatchResponse(BaseModel):
    """Batch sync response."""
    total: int
    successful: int
    failed: int
    results: List[OperationResult]


@router.post("/batch", response_model=SyncBatchResponse)
async def sync_batch_operations(
    request: SyncBatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> SyncBatchResponse:
    """
    Process batch of queued operations from offline mode.
    
    Operations are executed in chronological order (by timestamp).
    Each operation is validated and executed independently.
    
    Args:
        request: Batch of operations to sync
        current_user: Authenticated user
        db: Database session
        
    Returns:
        Results for each operation
    """
    logger.info(
        f"Processing batch sync for user {current_user.id}: "
        f"{len(request.operations)} operations"
    )
    
    # Sort operations by timestamp to maintain order
    sorted_ops = sorted(request.operations, key=lambda op: op.timestamp)
    
    results: List[OperationResult] = []
    successful = 0
    failed = 0
    
    for operation in sorted_ops:
        try:
            result = await _process_operation(operation, current_user, db)
            
            if result.success:
                successful += 1
            else:
                failed += 1
            
            results.append(result)
            
        except Exception as e:
            logger.error(
                f"Error processing operation {operation.id}: {str(e)}",
                exc_info=True
            )
            
            results.append(OperationResult(
                id=operation.id,
                success=False,
                error=f"Internal error: {str(e)}"
            ))
            failed += 1
    
    logger.info(
        f"Batch sync completed for user {current_user.id}: "
        f"{successful} successful, {failed} failed"
    )
    
    return SyncBatchResponse(
        total=len(sorted_ops),
        successful=successful,
        failed=failed,
        results=results
    )


async def _process_operation(
    operation: QueueOperation,
    user: User,
    db: AsyncSession
) -> OperationResult:
    """
    Process a single queued operation.
    
    Args:
        operation: Operation to process
        user: User who queued the operation
        db: Database session
        
    Returns:
        Operation result
    """
    try:
        # Route operation to appropriate handler
        if operation.type == "UPDATE_INCIDENT_STATUS":
            return await _handle_update_incident_status(operation, user, db)
        
        elif operation.type == "SEND_CHAT_MESSAGE":
            return await _handle_send_chat_message(operation, user, db)
        
        elif operation.type == "UPDATE_LOCATION":
            return await _handle_update_location(operation, user, db)
        
        elif operation.type == "ASSIGN_TECHNICIAN":
            return await _handle_assign_technician(operation, user, db)
        
        elif operation.type == "MARK_ARRIVED":
            return await _handle_mark_arrived(operation, user, db)
        
        else:
            return OperationResult(
                id=operation.id,
                success=False,
                error=f"Unknown operation type: {operation.type}"
            )
    
    except Exception as e:
        logger.error(f"Error in operation handler: {str(e)}", exc_info=True)
        return OperationResult(
            id=operation.id,
            success=False,
            error=str(e)
        )


async def _handle_update_incident_status(
    operation: QueueOperation,
    user: User,
    db: AsyncSession
) -> OperationResult:
    """Handle incident status update operation."""
    from ...modules.incident_states.services import IncidentStateService
    
    try:
        incident_id = operation.body.get("incident_id")
        new_status = operation.body.get("estado")
        notes = operation.body.get("notes")
        
        if not incident_id or not new_status:
            return OperationResult(
                id=operation.id,
                success=False,
                error="Missing incident_id or estado"
            )
        
        service = IncidentStateService(db)
        incident = await service.transition_state(
            incident_id=incident_id,
            new_state=new_status,
            changed_by=user.id,
            notes=notes
        )
        
        return OperationResult(
            id=operation.id,
            success=True,
            status_code=200,
            data={"incident_id": incident.id, "estado": incident.estado_actual}
        )
    
    except Exception as e:
        return OperationResult(
            id=operation.id,
            success=False,
            error=str(e)
        )


async def _handle_send_chat_message(
    operation: QueueOperation,
    user: User,
    db: AsyncSession
) -> OperationResult:
    """Handle chat message send operation."""
    from ...modules.chat.services import ChatService
    
    try:
        incident_id = operation.body.get("incident_id")
        message = operation.body.get("message")
        message_type = operation.body.get("message_type", "text")
        
        if not incident_id or not message:
            return OperationResult(
                id=operation.id,
                success=False,
                error="Missing incident_id or message"
            )
        
        service = ChatService(db)
        result = await service.send_message(
            incident_id=incident_id,
            sender_id=user.id,
            message_text=message,
            message_type=message_type
        )
        
        return OperationResult(
            id=operation.id,
            success=True,
            status_code=200,
            data={"message_id": result["id"]}
        )
    
    except Exception as e:
        return OperationResult(
            id=operation.id,
            success=False,
            error=str(e)
        )


async def _handle_update_location(
    operation: QueueOperation,
    user: User,
    db: AsyncSession
) -> OperationResult:
    """Handle location update operation."""
    from ...modules.real_time.services import RealTimeService
    
    try:
        latitude = operation.body.get("latitude")
        longitude = operation.body.get("longitude")
        accuracy = operation.body.get("accuracy")
        speed = operation.body.get("speed")
        heading = operation.body.get("heading")
        
        if latitude is None or longitude is None:
            return OperationResult(
                id=operation.id,
                success=False,
                error="Missing latitude or longitude"
            )
        
        service = RealTimeService(db)
        success = await service.update_technician_location(
            technician_id=user.id,
            latitude=latitude,
            longitude=longitude,
            accuracy=accuracy,
            speed=speed,
            heading=heading
        )
        
        return OperationResult(
            id=operation.id,
            success=success,
            status_code=200 if success else 500
        )
    
    except Exception as e:
        return OperationResult(
            id=operation.id,
            success=False,
            error=str(e)
        )


async def _handle_assign_technician(
    operation: QueueOperation,
    user: User,
    db: AsyncSession
) -> OperationResult:
    """Handle technician assignment operation."""
    from ...modules.real_time.services import RealTimeService
    
    try:
        incident_id = operation.body.get("incident_id")
        technician_id = operation.body.get("technician_id")
        
        if not incident_id or not technician_id:
            return OperationResult(
                id=operation.id,
                success=False,
                error="Missing incident_id or technician_id"
            )
        
        service = RealTimeService(db)
        success = await service.assign_technician_to_incident(
            incident_id=incident_id,
            technician_id=technician_id,
            assigned_by=user.id
        )
        
        return OperationResult(
            id=operation.id,
            success=success,
            status_code=200 if success else 500
        )
    
    except Exception as e:
        return OperationResult(
            id=operation.id,
            success=False,
            error=str(e)
        )


async def _handle_mark_arrived(
    operation: QueueOperation,
    user: User,
    db: AsyncSession
) -> OperationResult:
    """Handle technician arrival marking operation."""
    from ...modules.real_time.services import RealTimeService
    
    try:
        incident_id = operation.body.get("incident_id")
        
        if not incident_id:
            return OperationResult(
                id=operation.id,
                success=False,
                error="Missing incident_id"
            )
        
        service = RealTimeService(db)
        success = await service.notify_technician_arrived(
            incident_id=incident_id,
            technician_id=user.id
        )
        
        return OperationResult(
            id=operation.id,
            success=success,
            status_code=200 if success else 500
        )
    
    except Exception as e:
        return OperationResult(
            id=operation.id,
            success=False,
            error=str(e)
        )


@router.get("/status")
async def get_sync_status(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get sync service status.
    
    Returns:
        Service status information
    """
    return {
        "service": "sync",
        "status": "operational",
        "user_id": current_user.id,
        "supported_operations": [
            "UPDATE_INCIDENT_STATUS",
            "SEND_CHAT_MESSAGE",
            "UPDATE_LOCATION",
            "ASSIGN_TECHNICIAN",
            "MARK_ARRIVED"
        ]
    }
