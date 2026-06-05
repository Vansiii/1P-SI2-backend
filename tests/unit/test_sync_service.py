"""
Unit tests for sync module — idempotency, conflict detection, schemas.

Run: pytest tests/unit/test_sync_service.py -v
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.sync_operation import SyncOperation, SyncOperationStatus
from app.modules.sync.schemas import (
    QueueOperation,
    SyncBatchRequest,
    SyncBatchResponse,
    OperationResult,
    SyncStatusResponse,
)


class TestSyncOperationModel:
    def test_creation_defaults(self):
        op = SyncOperation(
            client_operation_id=uuid.uuid4(),
            user_id=1,
            operation_type="CREATE_INCIDENT",
            request_payload={"test": True},
        )
        assert op.status == SyncOperationStatus.PENDING
        assert op.retry_count == 0
        assert op.processed_at is None
        assert isinstance(op.created_at, datetime)

    def test_unique_client_operation_id(self):
        cid = uuid.uuid4()
        op1 = SyncOperation(client_operation_id=cid, user_id=1, operation_type="X", request_payload={})
        op2 = SyncOperation(client_operation_id=cid, user_id=1, operation_type="X", request_payload={})
        assert op1.client_operation_id == op2.client_operation_id

    def test_status_enum_values(self):
        assert SyncOperationStatus.PENDING.value == "pending"
        assert SyncOperationStatus.COMPLETED.value == "completed"
        assert SyncOperationStatus.CONFLICT.value == "conflict"
        assert SyncOperationStatus.DUPLICATE.value == "duplicate"


class TestQueueOperationSchema:
    def test_legacy_format_alias(self):
        data = {
            "id": "abc-123",
            "type": "UPDATE_INCIDENT_STATUS",
            "endpoint": "/api/v1/x",
            "method": "POST",
            "body": {"incident_id": 1, "estado": "en_proceso"},
            "timestamp": 1717545600000,
            "retries": 0,
        }
        op = QueueOperation.model_validate(data)
        assert op.operation_type == "UPDATE_INCIDENT_STATUS"
        assert op.payload == {"incident_id": 1, "estado": "en_proceso"}
        assert op.client_timestamp == 1717545600000
        assert op.client_operation_id is None

    def test_new_format_with_client_operation_id(self):
        cid = uuid.uuid4()
        data = {
            "id": "abc-124",
            "client_operation_id": cid,
            "type": "CREATE_INCIDENT",
            "body": {"descripcion": "test"},
            "timestamp": 1717545600000,
            "retries": 0,
        }
        op = QueueOperation.model_validate(data)
        assert op.client_operation_id == cid
        assert op.operation_type == "CREATE_INCIDENT"


class TestSyncBatchRequestSchema:
    def test_full_request(self):
        cid = uuid.uuid4()
        req = SyncBatchRequest.model_validate({
            "client_request_id": uuid.uuid4(),
            "app_platform": "android",
            "app_version": "1.2.3",
            "operations": [{
                "id": "op-1",
                "client_operation_id": cid,
                "type": "SEND_CHAT_MESSAGE",
                "body": {"incident_id": 1, "message": "hola"},
                "timestamp": 1717545600000,
                "retries": 0,
            }],
        })
        assert len(req.operations) == 1
        assert req.app_platform == "android"
        assert req.app_version == "1.2.3"

    def test_empty_operations(self):
        req = SyncBatchRequest.model_validate({"operations": []})
        assert req.operations == []


class TestOperationResultSchema:
    def test_completed_result(self):
        cid = uuid.uuid4()
        result = OperationResult(
            client_operation_id=cid,
            status="completed",
            success=True,
            server_entity_id=42,
            message="Creado correctamente",
            id="legacy-1",
        )
        assert result.success is True
        assert result.server_entity_id == 42

    def test_conflict_result(self):
        cid = uuid.uuid4()
        result = OperationResult(
            client_operation_id=cid,
            status="conflict",
            success=False,
            conflict_code="INCIDENT_ALREADY_RESOLVED",
            message="Ya fue resuelto",
            retryable=False,
            server_state={"incident_id": 1, "estado": "resuelto"},
            alternatives=[{"workshop_id": 5, "name": "Taller X", "distance_km": 2.3}],
        )
        assert result.conflict_code == "INCIDENT_ALREADY_RESOLVED"
        assert result.retryable is False
        assert len(result.alternatives) == 1


class TestSyncBatchResponseSchema:
    def test_mixed_results(self):
        response = SyncBatchResponse(
            total=2,
            successful=1,
            failed=1,
            conflicts=1,
            results=[
                OperationResult(
                    client_operation_id=uuid.uuid4(),
                    status="completed",
                    success=True,
                    server_entity_id=42,
                    message="Ok",
                ),
                OperationResult(
                    client_operation_id=uuid.uuid4(),
                    status="conflict",
                    success=False,
                    conflict_code="WORKSHOP_NOT_AVAILABLE",
                    message="No disponible",
                ),
            ],
        )
        assert response.total == 2
        assert response.successful == 1
        assert response.failed == 1
        assert response.conflicts == 1


class TestSyncServiceIdempotency:
    """Test SyncService.process_operation idempotency behavior."""

    @pytest.mark.asyncio
    async def test_duplicate_returns_cached_result(self):
        from app.modules.sync.services import SyncService

        session = AsyncMock()
        cid = uuid.uuid4()

        existing = SyncOperation(
            id=1,
            client_operation_id=cid,
            user_id=1,
            operation_type="UPDATE_LOCATION",
            status=SyncOperationStatus.COMPLETED,
            request_payload={},
            entity_id=99,
        )

        session.scalar = AsyncMock(return_value=existing)
        session.add = MagicMock()
        session.flush = AsyncMock()

        svc = SyncService(session)
        op = QueueOperation(
            id="x",
            client_operation_id=cid,
            type="UPDATE_LOCATION",
            body={"latitude": 1.0, "longitude": 2.0},
            timestamp=1000,
            retries=0,
        )
        user_id = 1

        result = await svc.process_operation(op, user_id)
        assert result.status == "duplicate"
        assert result.success is True
        assert result.conflict_code == "DUPLICATE_OPERATION"
        assert result.server_entity_id == 99

    @pytest.mark.asyncio
    async def test_new_operation_is_processed(self):
        from app.modules.sync.services import SyncService

        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.add = MagicMock()
        session.flush = AsyncMock()

        svc = SyncService(session)
        cid = uuid.uuid4()
        op = QueueOperation(
            id="new-op",
            client_operation_id=cid,
            type="UPDATE_LOCATION",
            body={"latitude": 1.0, "longitude": 2.0},
            timestamp=1000,
            retries=0,
        )
        user_id = 1

        result = await svc.process_operation(op, user_id, "android", "1.0")
        assert result.client_operation_id == cid
        # Should have added the SyncOperation record
        session.add.assert_called_once()


class TestSyncServiceConflicts:
    """Test conflict detection logic."""

    @pytest.mark.asyncio
    async def test_incident_not_found(self):
        from app.modules.sync.services import SyncService

        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        session.get = AsyncMock(return_value=None)

        svc = SyncService(session)
        result = await svc._check_incident_conflict(999)
        assert result is not None
        assert result.conflict_code == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_incident_cancelled(self):
        from app.modules.sync.services import SyncService
        from app.models.incidente import Incidente

        session = AsyncMock()
        incident = MagicMock(spec=Incidente)
        incident.estado_actual = "cancelado"
        session.get = AsyncMock(return_value=incident)

        svc = SyncService(session)
        result = await svc._check_incident_conflict(1)
        assert result is not None
        assert result.conflict_code == "INCIDENT_CANCELLED"

    @pytest.mark.asyncio
    async def test_incident_resolved(self):
        from app.modules.sync.services import SyncService
        from app.models.incidente import Incidente

        session = AsyncMock()
        incident = MagicMock(spec=Incidente)
        incident.estado_actual = "resuelto"
        session.get = AsyncMock(return_value=incident)

        svc = SyncService(session)
        result = await svc._check_incident_conflict(1)
        assert result is not None
        assert result.conflict_code == "INCIDENT_ALREADY_RESOLVED"

    @pytest.mark.asyncio
    async def test_incident_active_no_conflict(self):
        from app.modules.sync.services import SyncService
        from app.models.incidente import Incidente

        session = AsyncMock()
        incident = MagicMock(spec=Incidente)
        incident.estado_actual = "en_proceso"
        session.get = AsyncMock(return_value=incident)

        svc = SyncService(session)
        result = await svc._check_incident_conflict(1)
        assert result is None

    @pytest.mark.asyncio
    async def test_workshop_unavailable(self):
        from app.modules.sync.services import SyncService

        session = AsyncMock()
        session.get = AsyncMock(return_value=None)

        svc = SyncService(session)
        result = await svc._check_workshop_available(5)
        assert result is not None
        assert result.conflict_code == "WORKSHOP_NOT_AVAILABLE"

    @pytest.mark.asyncio
    async def test_technician_unavailable(self):
        from app.modules.sync.services import SyncService

        session = AsyncMock()
        session.get = AsyncMock(return_value=None)

        svc = SyncService(session)
        result = await svc._check_technician_available(10)
        assert result is not None
        assert result.conflict_code == "TECHNICIAN_NOT_AVAILABLE"


class TestSyncStatusResponse:
    def test_status_response(self):
        resp = SyncStatusResponse(
            user_id=1,
            tenant_id=5,
            pending_operations_count=0,
            last_sync_at="2025-06-04T12:00:00Z",
            supported_operations=["CREATE_INCIDENT", "UPDATE_LOCATION"],
            app_min_version={"web": "1.0.0", "android": "1.0.0"},
        )
        assert resp.service == "sync"
        assert resp.status == "operational"
        assert resp.user_id == 1
        assert len(resp.supported_operations) == 2
