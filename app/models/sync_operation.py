"""
SyncOperation model for tracking offline sync operations with idempotency.

This model records every operation received via POST /sync/batch, enabling:
- Idempotency: duplicate client_operation_id returns original result
- Audit trail: who synced what, when, with what result
- Conflict tracking: what conflict was detected and why
- Retry tracking: how many times an operation was retried
"""

import enum
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Index, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
import uuid

from .base import Base


class SyncOperationStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CONFLICT = "conflict"
    DUPLICATE = "duplicate"
    EXPIRED = "expired"


class SyncOperation(Base):
    __tablename__ = "sync_operations"

    id = Column(Integer, primary_key=True, index=True)
    client_operation_id = Column(
        UUID(as_uuid=True), unique=True, nullable=False, index=True,
        default=uuid.uuid4
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    operation_type = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(Integer, nullable=True)

    status = Column(
        SQLEnum(SyncOperationStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=SyncOperationStatus.PENDING,
        server_default=sa.text("'pending'"),
        index=True,
    )

    request_payload = Column(JSONB, nullable=False)
    response_payload = Column(JSONB, nullable=True)

    conflict_code = Column(String(50), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)

    app_platform = Column(String(20), nullable=True)
    app_version = Column(String(20), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_sync_ops_user_status", "user_id", "status"),
        Index("idx_sync_ops_tenant", "tenant_id"),
        Index("idx_sync_ops_created", "created_at"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("status", SyncOperationStatus.PENDING)
        kwargs.setdefault("retry_count", 0)
        kwargs.setdefault("created_at", datetime.now(timezone.utc).replace(tzinfo=None))
        kwargs.setdefault("updated_at", datetime.now(timezone.utc).replace(tzinfo=None))
        super().__init__(**kwargs)

    def __repr__(self):
        return (
            f"<SyncOperation(id={self.id}, client_op_id={self.client_operation_id}, "
            f"type={self.operation_type}, status={self.status})>"
        )
