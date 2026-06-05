"""
Sync module Pydantic schemas with idempotency, conflict codes, and dependency support.
"""
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class QueueOperation(BaseModel):
    """Single queued offline operation with client_operation_id for idempotency."""
    id: Optional[str] = Field(None, description="Legacy operation ID (echoed in response)")
    client_operation_id: Optional[UUID] = Field(
        None, description="Unique idempotency key (UUID v4). "
                          "For legacy clients, derived from 'id' field if missing."
    )
    operation_type: str = Field(..., alias="type", description="Operation type identifier")
    entity_type: Optional[str] = Field(None, description="Entity type (incident, evidence, etc.)")
    payload: Optional[dict[str, Any]] = Field(
        default_factory=dict, alias="body",
        description="Operation payload"
    )
    client_timestamp: int = Field(
        ..., alias="timestamp",
        description="Unix milliseconds timestamp when the operation was queued on client"
    )
    retries: int = Field(default=0, description="Number of previous retry attempts on client")
    depends_on: Optional[UUID] = Field(
        None, description="client_operation_id of an operation this one depends on"
    )

    endpoint: Optional[str] = Field(None, description="Legacy field — not used by new handler")
    method: Optional[str] = Field(None, description="Legacy field — not used by new handler")


class SyncBatchRequest(BaseModel):
    """Batch sync request with optional client_request_id for tracing the whole batch."""
    client_request_id: Optional[UUID] = Field(
        None, description="Optional batch-level idempotency key"
    )
    app_platform: Optional[str] = Field(None, description="Client platform: web, ios, android")
    app_version: Optional[str] = Field(None, description="Client app version")
    operations: list[QueueOperation] = Field(..., description="List of queued operations")


class OperationResult(BaseModel):
    """Result of a single sync operation."""
    client_operation_id: UUID
    status: str = Field(..., description="completed | failed | conflict | duplicate")
    success: bool
    server_entity_id: Optional[int] = Field(None, description="Server-assigned entity ID")
    conflict_code: Optional[str] = Field(
        None,
        description="Conflict code: WORKSHOP_NOT_AVAILABLE, INCIDENT_ALREADY_RESOLVED, etc."
    )
    message: Optional[str] = Field(None, description="Human-readable result message")
    retryable: bool = Field(default=False, description="Whether the client should retry")
    server_state: Optional[dict[str, Any]] = Field(
        None, description="Current server state for conflict resolution"
    )
    alternatives: Optional[list[dict[str, Any]]] = Field(
        None, description="Alternative resources (e.g. other workshops)"
    )

    # Legacy fields for backward compat
    id: Optional[str] = Field(None, description="Legacy operation ID echo")
    status_code: Optional[int] = Field(None, description="Legacy HTTP status code")
    error: Optional[str] = Field(None, description="Legacy error field")
    data: Optional[dict[str, Any]] = Field(None, description="Legacy data field")


class SyncBatchResponse(BaseModel):
    """Batch sync response with per-operation results."""
    total: int
    successful: int
    failed: int
    conflicts: int = Field(default=0, description="Number of operations with conflict")
    results: list[OperationResult]


class SyncStatusResponse(BaseModel):
    """GET /sync/status response."""
    service: str = "sync"
    status: str = "operational"
    user_id: int
    tenant_id: Optional[int] = None
    pending_operations_count: int = 0
    last_sync_at: Optional[str] = None
    supported_operations: list[str] = Field(default_factory=list)
    app_min_version: dict[str, str] = Field(default_factory=dict)
