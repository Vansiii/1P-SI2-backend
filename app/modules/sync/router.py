"""
Sync API endpoints for offline queue synchronization.

Supports idempotency via client_operation_id (UUID v4),
conflict detection for business rule violations,
and backward compatibility with legacy clients that omit client_operation_id.
"""

import uuid
import hashlib
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.dependencies import get_current_user
from ...core.logging import get_logger
from ...models.user import User

from .schemas import (
    QueueOperation,
    SyncBatchRequest,
    SyncBatchResponse,
    OperationResult,
    SyncStatusResponse,
)
from .services import SyncService

logger = get_logger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


async def _audit_sync_batch(
    request: Request,
    user_id: int,
    response: SyncBatchResponse,
    db: AsyncSession,
) -> None:
    try:
        from ...modules.audit.service import AuditService
        audit = AuditService(db)
        await audit.log_action_from_request(
            request=request,
            action="SYNC_BATCH_PROCESSED",
            user_id=user_id,
            resource_type="sync_batch",
            details={
                "total": response.total,
                "successful": response.successful,
                "failed": response.failed,
                "conflicts": response.conflicts,
            },
        )
        await db.commit()
    except Exception:
        logger.warning("Failed to create audit log for sync batch", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass


def _resolve_client_operation_id(op: QueueOperation) -> uuid.UUID:
    """Resolve client_operation_id from the new field or derive from legacy id."""
    if op.client_operation_id is not None:
        return op.client_operation_id
    if op.id:
        digest = hashlib.sha256(f"legacy:{op.id}".encode()).digest()[:16]
        return uuid.UUID(bytes=digest)
    return uuid.uuid4()


@router.post("/batch", response_model=SyncBatchResponse)
async def sync_batch_operations(
    request: Request,
    body: SyncBatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncBatchResponse:
    """
    Process batch of queued operations from offline mode.

    Each operation is identified by a client_operation_id for idempotency.
    Operations are sorted chronologically and processed independently.
    Conflicts are reported per-operation without failing the entire batch.

    Backward-compatible with legacy clients that use 'id' instead of
    'client_operation_id'.
    """
    ops = body.operations
    if not ops:
        return SyncBatchResponse(total=0, successful=0, failed=0, conflicts=0, results=[])

    user_id = current_user.id

    logger.info(
        "Processing batch sync — user=%s operations=%d platform=%s version=%s",
        user_id, len(ops), body.app_platform, body.app_version,
    )

    sorted_ops = sorted(ops, key=lambda o: o.client_timestamp)
    svc = SyncService(db)

    results: list[OperationResult] = []
    successful = 0
    failed = 0
    conflicts = 0

    server_entity_cache: dict[uuid.UUID, int] = {}

    for op in sorted_ops:
        try:
            logger.info(
                "Processing sync op — id=%s type=%s cid=%s body_keys=%s",
                op.id, op.operation_type, op.client_operation_id,
                list((op.payload or {}).keys()),
            )

            cid = _resolve_client_operation_id(op)
            op.client_operation_id = cid

            if op.depends_on and op.depends_on in server_entity_cache:
                payload = op.payload or {}
                if "incident_id" not in payload or payload.get("incident_id") is None:
                    payload["incident_id"] = server_entity_cache[op.depends_on]
                    op.payload = payload

            try:
                result = await svc.process_operation(
                    operation=op,
                    user_id=user_id,
                    app_platform=body.app_platform,
                    app_version=body.app_version,
                )
            except Exception:
                await db.rollback()
                raise

            result.id = op.id
            if result.server_entity_id:
                server_entity_cache[cid] = result.server_entity_id

            if result.success:
                successful += 1
            elif result.conflict_code:
                conflicts += 1
            else:
                failed += 1

            results.append(result)

        except Exception:
            logger.exception("Unhandled error processing operation id=%s", op.id)
            try:
                await db.rollback()
            except Exception:
                pass
            results.append(OperationResult(
                client_operation_id=op.client_operation_id,
                id=op.id,
                status="failed",
                success=False,
                message="Internal server error",
                retryable=True,
            ))
            failed += 1

    response = SyncBatchResponse(
        total=len(sorted_ops),
        successful=successful,
        failed=failed,
        conflicts=conflicts,
        results=results,
    )

    await _audit_sync_batch(request, user_id, response, db)

    logger.info(
        "Batch sync completed — user=%s total=%d ok=%d fail=%d conflicts=%d",
        user_id, response.total, successful, failed, conflicts,
    )

    return response


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncStatusResponse:
    """
    Get sync service status and supported operation types.

    Returns the list of operations that can be queued offline
    and synced via POST /sync/batch.
    """
    svc = SyncService(db)
    data = await svc.get_sync_status(current_user.id)
    return SyncStatusResponse(**data)
