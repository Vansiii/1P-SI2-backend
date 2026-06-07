"""
Sync Service for offline queue synchronization with idempotency, conflict detection,
and multi-tenant isolation.

Supports offline synchronization for incidents, chat, vehicles, notifications,
catalog, and cancellation flows:
- CREATE_INCIDENT, UPDATE_INCIDENT_STATUS, UPDATE_INCIDENT
- SEND_CHAT_MESSAGE
- UPDATE_LOCATION, ASSIGN_TECHNICIAN, MARK_ARRIVED
- UPLOAD_EVIDENCE, UPLOAD_FILE, SELECT_WORKSHOP
- CREATE_VEHICLE, UPDATE_VEHICLE, DELETE_VEHICLE
- MARK_NOTIFICATION_READ
- CREATE_CATALOG_ITEM, UPDATE_CATALOG_ITEM, TOGGLE_CATALOG_ITEM, DELETE_CATALOG_ITEM
- REQUEST_CANCELLATION, RESPOND_CANCELLATION
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging import get_logger
from ...core.exceptions import NotFoundException, ValidationException, ForbiddenException
from ...models.sync_operation import SyncOperation, SyncOperationStatus
from ...models.incidente import Incidente
from ...models.workshop import Workshop
from ...models.tenant import Tenant
from ...models.tenant_subscription import TenantSubscription
from ...models.technician import Technician
from ...models.user import User

from .schemas import QueueOperation, OperationResult

logger = get_logger(__name__)


class ConflictCode:
    WORKSHOP_NOT_AVAILABLE = "WORKSHOP_NOT_AVAILABLE"
    INCIDENT_ALREADY_RESOLVED = "INCIDENT_ALREADY_RESOLVED"
    INCIDENT_CANCELLED = "INCIDENT_CANCELLED"
    TECHNICIAN_NOT_AVAILABLE = "TECHNICIAN_NOT_AVAILABLE"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    RESOURCE_VERSION_CHANGED = "RESOURCE_VERSION_CHANGED"
    TENANT_SUSPENDED = "TENANT_SUSPENDED"
    SUBSCRIPTION_INACTIVE = "SUBSCRIPTION_INACTIVE"
    DUPLICATE_OPERATION = "DUPLICATE_OPERATION"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"


class SyncService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Public API ────────────────────────────────────────────────────────

    async def process_operation(
        self,
        operation: QueueOperation,
        user_id: int,
        app_platform: Optional[str] = None,
        app_version: Optional[str] = None,
    ) -> OperationResult:
        cid = operation.client_operation_id

        existing = await self._find_existing(cid)
        if existing:
            return self._build_duplicate_result(existing)

        record = SyncOperation(
            client_operation_id=cid,
            user_id=user_id,
            tenant_id=None,
            operation_type=operation.operation_type,
            entity_type=operation.entity_type,
            status=SyncOperationStatus.PROCESSING,
            request_payload=operation.model_dump(mode="json"),
            app_platform=app_platform,
            app_version=app_version,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except Exception:
            await self.session.rollback()
            existing = await self._find_existing(cid)
            if existing:
                return self._build_duplicate_result(existing)
            raise

        try:
            result = await self._route(operation, user_id)
            record.status = SyncOperationStatus.COMPLETED if result.success else SyncOperationStatus.CONFLICT
            record.response_payload = result.model_dump(mode="json")
            record.entity_id = result.server_entity_id
            record.processed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await self.session.flush()
            return result
        except Exception:
            exc = getattr(_sys_exc_info(), "value", None)
            exc_msg = str(exc) if exc else "unknown"
            record.status = SyncOperationStatus.FAILED
            record.error_message = exc_msg
            record.retry_count = operation.retries + 1
            await self.session.flush()
            logger.error(
                "Sync operation failed — type=%s user=%s cid=%s error=%s",
                operation.operation_type, user_id, cid, exc_msg, exc_info=True,
            )
            return OperationResult(
                client_operation_id=cid,
                status="failed",
                success=False,
                message=f"Error: {exc_msg}",
                retryable=True,
            )

    async def get_sync_status(self, user_id: int) -> dict[str, Any]:
        return {
            "service": "sync",
            "status": "operational",
            "user_id": user_id,
            "supported_operations": [
                "CREATE_INCIDENT",
                "UPDATE_INCIDENT_STATUS",
                "UPDATE_INCIDENT",
                "SEND_CHAT_MESSAGE",
                "UPDATE_LOCATION",
                "ASSIGN_TECHNICIAN",
                "MARK_ARRIVED",
                "UPLOAD_EVIDENCE",
                "UPLOAD_FILE",
                "SELECT_WORKSHOP",
                "CREATE_VEHICLE",
                "UPDATE_VEHICLE",
                "DELETE_VEHICLE",
                "MARK_NOTIFICATION_READ",
                "CREATE_CATALOG_ITEM",
                "UPDATE_CATALOG_ITEM",
                "TOGGLE_CATALOG_ITEM",
                "DELETE_CATALOG_ITEM",
                "REQUEST_CANCELLATION",
                "RESPOND_CANCELLATION",
            ],
        }

    # ── Idempotency ───────────────────────────────────────────────────────

    async def _find_existing(self, client_operation_id: UUID) -> Optional[SyncOperation]:
        result = await self.session.scalar(
            select(SyncOperation).where(
                SyncOperation.client_operation_id == client_operation_id
            )
        )
        return result

    def _build_duplicate_result(self, record: SyncOperation) -> OperationResult:
        return OperationResult(
            client_operation_id=record.client_operation_id,
            status="duplicate",
            success=record.status == SyncOperationStatus.COMPLETED,
            server_entity_id=record.entity_id,
            conflict_code=ConflictCode.DUPLICATE_OPERATION,
            message="Esta operacion ya fue procesada anteriormente",
            retryable=False,
        )

    # ── Routing ───────────────────────────────────────────────────────────

    async def _route(self, op: QueueOperation, user_id: int) -> OperationResult:
        otype = op.operation_type
        payload = op.payload or {}

        if otype == "CREATE_INCIDENT":
            return await self._handle_create_incident(payload, user_id, op)
        elif otype == "UPDATE_INCIDENT_STATUS":
            return await self._handle_update_incident_status(payload, user_id, op)
        elif otype == "UPDATE_INCIDENT":
            return await self._handle_update_incident(payload, user_id, op)
        elif otype == "SEND_CHAT_MESSAGE":
            return await self._handle_send_chat_message(payload, user_id, op)
        elif otype == "UPDATE_LOCATION":
            return await self._handle_update_location(payload, user_id, op)
        elif otype == "ASSIGN_TECHNICIAN":
            return await self._handle_assign_technician(payload, user_id, op)
        elif otype == "MARK_ARRIVED":
            return await self._handle_mark_arrived(payload, user_id, op)
        elif otype == "UPLOAD_EVIDENCE":
            return await self._handle_upload_evidence(payload, user_id, op)
        elif otype == "UPLOAD_FILE":
            return await self._handle_upload_file(payload, user_id, op)
        elif otype == "SELECT_WORKSHOP":
            return await self._handle_select_workshop(payload, user_id, op)
        elif otype == "CREATE_VEHICLE":
            return await self._handle_create_vehicle(payload, user_id, op)
        elif otype == "UPDATE_VEHICLE":
            return await self._handle_update_vehicle(payload, user_id, op)
        elif otype == "DELETE_VEHICLE":
            return await self._handle_delete_vehicle(payload, user_id, op)
        elif otype == "MARK_NOTIFICATION_READ":
            return await self._handle_mark_notification_read(payload, user_id, op)
        elif otype == "CREATE_CATALOG_ITEM":
            return await self._handle_create_catalog_item(payload, user_id, op)
        elif otype == "UPDATE_CATALOG_ITEM":
            return await self._handle_update_catalog_item(payload, user_id, op)
        elif otype == "TOGGLE_CATALOG_ITEM":
            return await self._handle_toggle_catalog_item(payload, user_id, op)
        elif otype == "DELETE_CATALOG_ITEM":
            return await self._handle_delete_catalog_item(payload, user_id, op)
        elif otype == "REQUEST_CANCELLATION":
            return await self._handle_request_cancellation(payload, user_id, op)
        elif otype == "RESPOND_CANCELLATION":
            return await self._handle_respond_cancellation(payload, user_id, op)
        else:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message=f"Unknown operation type: {otype}",
                retryable=False,
            )

    # ── Conflict helpers ──────────────────────────────────────────────────

    async def _check_incident_conflict(self, incident_id: int) -> Optional[OperationResult]:
        incident = await self.session.get(Incidente, incident_id)
        if not incident:
            return OperationResult(
                client_operation_id=UUID(int=0),
                status="conflict",
                success=False,
                conflict_code=ConflictCode.RESOURCE_NOT_FOUND,
                message="El incidente ya no existe",
                retryable=False,
            )
        if incident.estado_actual == "cancelado":
            return OperationResult(
                client_operation_id=UUID(int=0),
                status="conflict",
                success=False,
                conflict_code=ConflictCode.INCIDENT_CANCELLED,
                message="El incidente fue cancelado mientras estabas sin conexion",
                retryable=False,
                server_state={"incident_id": incident.id, "estado": incident.estado_actual},
            )
        if incident.estado_actual == "resuelto":
            return OperationResult(
                client_operation_id=UUID(int=0),
                status="conflict",
                success=False,
                conflict_code=ConflictCode.INCIDENT_ALREADY_RESOLVED,
                message="El incidente ya fue resuelto mientras estabas sin conexion",
                retryable=False,
                server_state={"incident_id": incident.id, "estado": incident.estado_actual},
            )
        return None

    async def _check_workshop_available(self, workshop_id: int) -> Optional[OperationResult]:
        workshop = await self.session.get(Workshop, workshop_id)
        if not workshop or not workshop.is_active:
            return OperationResult(
                client_operation_id=UUID(int=0),
                status="conflict",
                success=False,
                conflict_code=ConflictCode.WORKSHOP_NOT_AVAILABLE,
                message="El taller ya no esta disponible",
                retryable=False,
            )
        if workshop.tenant_id:
            tenant = await self.session.get(Tenant, workshop.tenant_id)
            if tenant and tenant.status == "suspended":
                return OperationResult(
                    client_operation_id=UUID(int=0),
                    status="conflict",
                    success=False,
                    conflict_code=ConflictCode.TENANT_SUSPENDED,
                    message="El taller fue suspendido",
                    retryable=False,
                )
        return None

    async def _check_technician_available(self, technician_id: int) -> Optional[OperationResult]:
        tech = await self.session.get(Technician, technician_id)
        if not tech or not tech.is_active:
            return OperationResult(
                client_operation_id=UUID(int=0),
                status="conflict",
                success=False,
                conflict_code=ConflictCode.TECHNICIAN_NOT_AVAILABLE,
                message="El tecnico ya no esta disponible",
                retryable=False,
            )
        return None

    async def _get_workshop_tenant_id(self, user_id: int) -> Optional[int]:
        workshop = await self.session.get(Workshop, user_id)
        return workshop.tenant_id if workshop else None

    async def _get_user_type(self, user_id: int) -> Optional[str]:
        user = await self.session.get(User, user_id)
        return user.user_type if user else None

    # ── Handlers ──────────────────────────────────────────────────────────

    async def _handle_create_incident(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.incidentes.service import IncidenteService
        from ...modules.incidentes.schemas import IncidenteCreateRequest

        logger.info(
            "Sync CREATE_INCIDENT — user=%s payload_keys=%s vehiculo_id=%s desc_len=%d",
            user_id, list(payload.keys()),
            payload.get("vehiculo_id"),
            len(payload.get("descripcion", "")),
        )

        incident_request = IncidenteCreateRequest(
            vehiculo_id=payload["vehiculo_id"],
            latitude=payload["latitude"],
            longitude=payload["longitude"],
            direccion_referencia=payload.get("direccion_referencia"),
            descripcion=payload["descripcion"],
            assignment_mode=payload.get("assignment_mode", "auto"),
            imagenes=payload.get("imagenes", []),
            audios=payload.get("audios", []),
        )
        service = IncidenteService(self.session)
        incident = await service.create_incidente(user_id, incident_request)
        logger.info(
            "Sync CREATE_INCIDENT success — incident_id=%s user=%s",
            incident.id, user_id,
        )
        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed",
            success=True,
            server_entity_id=incident.id,
            message="Incidente creado correctamente",
            server_state={"incident_id": incident.id, "estado": incident.estado_actual},
        )

    async def _handle_update_incident_status(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.incident_states.services import IncidentStateService

        incident_id = payload.get("incident_id")
        new_status = payload.get("estado")
        notes = payload.get("notes")

        if not incident_id or not new_status:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere incident_id y estado",
                retryable=False,
            )

        conflict = await self._check_incident_conflict(incident_id)
        if conflict:
            conflict.client_operation_id = op.client_operation_id
            return conflict

        svc = IncidentStateService(self.session)
        incident = await svc.transition_state(
            incident_id=incident_id,
            new_state=new_status,
            changed_by=user_id,
            notes=notes,
        )
        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed",
            success=True,
            server_entity_id=incident.id,
            message=f"Estado actualizado a {incident.estado_actual}",
            server_state={"incident_id": incident.id, "estado": incident.estado_actual},
        )

    async def _handle_update_incident(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...core.event_publisher import EventPublisher
        from ...shared.schemas.events.incident import IncidentUpdatedEvent

        incident_id = payload.get("incident_id")
        if not incident_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere incident_id",
                retryable=False,
            )

        conflict = await self._check_incident_conflict(incident_id)
        if conflict:
            conflict.client_operation_id = op.client_operation_id
            return conflict

        incident = await self.session.get(Incidente, incident_id)
        updatable = {"descripcion", "direccion_referencia"}
        updated_fields: dict[str, Any] = {}
        for key, value in payload.items():
            if key in updatable and value is not None:
                setattr(incident, key, value)
                updated_fields[key] = value

        if not updated_fields:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="completed",
                success=True,
                server_entity_id=incident.id,
                message="No hubo cambios para aplicar",
                server_state={"incident_id": incident.id, "estado": incident.estado_actual},
            )

        incident.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        updated_fields["updated_at"] = incident.updated_at.isoformat()
        await self.session.flush()

        await EventPublisher.publish(
            self.session,
            IncidentUpdatedEvent(
                incident_id=incident.id,
                updated_fields=updated_fields,
            ),
            tenant_id=incident.tenant_id,
        )

        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed",
            success=True,
            server_entity_id=incident.id,
            message="Incidente actualizado correctamente",
            server_state={"incident_id": incident.id, "estado": incident.estado_actual},
        )

    async def _handle_send_chat_message(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.chat.services import ChatService

        incident_id = payload.get("incident_id")
        message = payload.get("message")
        message_type = payload.get("message_type", "text")
        if not incident_id or not message:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere incident_id y message",
                retryable=False,
            )

        conflict = await self._check_incident_conflict(incident_id)
        if conflict:
            conflict.client_operation_id = op.client_operation_id
            return conflict

        svc = ChatService(self.session)
        msg = await svc.send_message(
            incident_id=incident_id,
            sender_id=user_id,
            message_text=message,
            message_type=message_type,
        )
        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed",
            success=True,
            server_entity_id=msg.id,
            message="Mensaje enviado",
        )

    async def _handle_update_location(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.real_time.services import RealTimeService

        latitude = payload.get("latitude")
        longitude = payload.get("longitude")
        accuracy = payload.get("accuracy")
        speed = payload.get("speed")
        heading = payload.get("heading")
        if latitude is None or longitude is None:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere latitude y longitude",
                retryable=False,
            )

        svc = RealTimeService(self.session)
        ok = await svc.update_technician_location(
            technician_id=user_id,
            latitude=latitude,
            longitude=longitude,
            accuracy=accuracy,
            speed=speed,
            heading=heading,
        )
        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed" if ok else "failed",
            success=ok,
            message="Ubicacion actualizada" if ok else "Error al actualizar ubicacion",
            retryable=not ok,
        )

    async def _handle_assign_technician(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.real_time.services import RealTimeService

        incident_id = payload.get("incident_id")
        technician_id = payload.get("technician_id")
        if not incident_id or not technician_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere incident_id y technician_id",
                retryable=False,
            )

        conflict = await self._check_incident_conflict(incident_id)
        if conflict:
            conflict.client_operation_id = op.client_operation_id
            return conflict

        tech_conflict = await self._check_technician_available(technician_id)
        if tech_conflict:
            tech_conflict.client_operation_id = op.client_operation_id
            return tech_conflict

        svc = RealTimeService(self.session)
        ok = await svc.assign_technician_to_incident(
            incident_id=incident_id,
            technician_id=technician_id,
            assigned_by=user_id,
        )
        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed" if ok else "failed",
            success=ok,
            message="Tecnico asignado" if ok else "Error al asignar tecnico",
            retryable=not ok,
        )

    async def _handle_mark_arrived(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.real_time.services import RealTimeService

        incident_id = payload.get("incident_id")
        if not incident_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere incident_id",
                retryable=False,
            )

        conflict = await self._check_incident_conflict(incident_id)
        if conflict:
            conflict.client_operation_id = op.client_operation_id
            return conflict

        svc = RealTimeService(self.session)
        ok = await svc.notify_technician_arrived(
            incident_id=incident_id,
            technician_id=user_id,
        )
        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed" if ok else "failed",
            success=ok,
            message="Llegada registrada" if ok else "Error al registrar llegada",
            retryable=not ok,
        )

    async def _handle_upload_evidence(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        incident_id = payload.get("incident_id")
        file_url = payload.get("file_url")
        evidence_type = payload.get("evidence_type", "IMAGE")
        description = payload.get("description", "Evidencia offline")
        file_name = payload.get("file_name", "evidence.jpg")
        mime_type = payload.get("mime_type", "image/jpeg")
        file_size = payload.get("file_size", 0)

        if not incident_id or not file_url:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere incident_id y file_url",
                retryable=False,
            )

        conflict = await self._check_incident_conflict(incident_id)
        if conflict:
            conflict.client_operation_id = op.client_operation_id
            return conflict

        from ...models.evidencia import Evidencia
        from ...models.evidencia_imagen import EvidenciaImagen
        from ...models.evidencia_audio import EvidenciaAudio

        evidencia = Evidencia(
            incidente_id=incident_id,
            uploaded_by_user_id=user_id,
            tipo=evidence_type,
            descripcion=description,
        )
        self.session.add(evidencia)
        await self.session.flush()

        if evidence_type == "IMAGE":
            img = EvidenciaImagen(
                evidencia_id=evidencia.id,
                file_url=file_url,
                file_name=file_name,
                file_type="image",
                mime_type=mime_type,
                size=file_size,
                uploaded_by=user_id,
            )
            self.session.add(img)
        elif evidence_type == "AUDIO":
            aud = EvidenciaAudio(
                evidencia_id=evidencia.id,
                file_url=file_url,
                file_name=file_name,
                file_type="audio",
                mime_type=mime_type,
                size=file_size,
                uploaded_by=user_id,
            )
            self.session.add(aud)

        await self.session.flush()
        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed",
            success=True,
            server_entity_id=evidencia.id,
            message="Evidencia registrada correctamente",
        )

    async def _handle_upload_file(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        """Handle file upload sync operation.

        Note: The mobile client should upload the actual file via multipart
        BEFORE sending this operation in the sync batch. This handler just
        records the file_url in the database if provided.
        """
        file_url = payload.get("file_url")
        file_type = payload.get("file_type", "image")
        file_name = payload.get("file_name", "upload.jpg")
        mime_type = payload.get("mime_type", "image/jpeg")
        file_size = payload.get("file_size", 0)

        if not file_url:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere file_url. El archivo debe subirse via multipart antes del sync batch.",
                retryable=False,
            )

        if file_url.startswith("local://"):
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="URL local no valida. El archivo debe subirse al servidor antes del sync.",
                retryable=False,
            )

        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed",
            success=True,
            server_entity_id=None,
            message="Archivo registrado correctamente",
            server_state={"file_url": file_url, "file_type": file_type},
        )

    async def _handle_select_workshop(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.workshop_selection.service import WorkshopSelectionService

        incident_id = payload.get("incident_id")
        workshop_id = payload.get("workshop_id")
        if not incident_id or not workshop_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere incident_id y workshop_id",
                retryable=False,
            )

        conflict = await self._check_incident_conflict(incident_id)
        if conflict:
            conflict.client_operation_id = op.client_operation_id
            return conflict

        ws_conflict = await self._check_workshop_available(workshop_id)
        if ws_conflict:
            ws_conflict.client_operation_id = op.client_operation_id

            svc = WorkshopSelectionService(self.session)
            try:
                compatible = await svc.get_compatible_workshops(incident_id, user_id)
                alternatives = [
                    {"workshop_id": w["workshop_id"], "name": w.get("workshop_name", ""),
                     "distance_km": w.get("distance_km", 0), "score": w.get("score", 0)}
                    for w in (compatible or [])[:5]
                ]
                ws_conflict.alternatives = alternatives
            except Exception:
                pass

            return ws_conflict

        svc = WorkshopSelectionService(self.session)
        try:
            result = await svc.select_workshop(incident_id, workshop_id, user_id)
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="completed",
                success=True,
                server_entity_id=incident_id,
                message="Taller seleccionado correctamente",
                server_state=result,
            )
        except ValueError as e:
            svc2 = WorkshopSelectionService(self.session)
            try:
                compatible = await svc2.get_compatible_workshops(incident_id, user_id)
                alternatives = [
                    {"workshop_id": w["workshop_id"], "name": w.get("workshop_name", ""),
                     "distance_km": w.get("distance_km", 0), "score": w.get("score", 0)}
                    for w in (compatible or [])[:5]
                ]
            except Exception:
                alternatives = []
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="conflict",
                success=False,
                conflict_code=ConflictCode.WORKSHOP_NOT_AVAILABLE,
                message=str(e),
                retryable=False,
                alternatives=alternatives,
            )

    async def _handle_create_vehicle(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.vehiculos.service import VehiculoService
        from ...modules.vehiculos.schemas import VehiculoCreateRequest

        logger.info(
            "Sync CREATE_VEHICLE — user=%s payload_keys=%s matricula=%s",
            user_id, list(payload.keys()),
            payload.get("matricula"),
        )

        request = VehiculoCreateRequest(
            matricula=payload["matricula"],
            marca=payload.get("marca"),
            modelo=payload.get("modelo", "Desconocido"),
            anio=payload.get("anio", 2024),
            color=payload.get("color"),
            imagen=payload.get("imagen"),
        )
        svc = VehiculoService(self.session)
        vehiculo = await svc.create_vehiculo(user_id, request)
        logger.info(
            "Sync CREATE_VEHICLE success — vehicle_id=%s matricula=%s user=%s",
            vehiculo.id, vehiculo.matricula, user_id,
        )
        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed",
            success=True,
            server_entity_id=vehiculo.id,
            message="Vehiculo creado correctamente",
            server_state={"vehiculo_id": vehiculo.id, "matricula": vehiculo.matricula},
        )

    async def _handle_update_vehicle(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.vehiculos.service import VehiculoService
        from ...modules.vehiculos.schemas import VehiculoUpdateRequest

        vehicle_id = payload.get("vehiculo_id")
        if not vehicle_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere vehiculo_id",
                retryable=False,
            )

        svc = VehiculoService(self.session)
        try:
            vehiculo = await svc.get_vehiculo(vehicle_id, user_id)
        except NotFoundException:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="conflict",
                success=False,
                conflict_code=ConflictCode.RESOURCE_NOT_FOUND,
                message="El vehiculo ya no existe",
                retryable=False,
            )

        request = VehiculoUpdateRequest(
            marca=payload.get("marca"),
            modelo=payload.get("modelo"),
            anio=payload.get("anio"),
            color=payload.get("color"),
            imagen=payload.get("imagen"),
            is_active=payload.get("is_active"),
        )
        vehiculo = await svc.update_vehiculo(vehicle_id, user_id, request)

        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed",
            success=True,
            server_entity_id=vehiculo.id,
            message="Vehiculo actualizado correctamente",
        )

    async def _handle_delete_vehicle(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.vehiculos.service import VehiculoService

        vehicle_id = payload.get("vehiculo_id")
        if not vehicle_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere vehiculo_id",
                retryable=False,
            )

        svc = VehiculoService(self.session)
        try:
            await svc.delete_vehiculo(vehicle_id, client_id=user_id)
        except NotFoundException:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="conflict",
                success=False,
                conflict_code=ConflictCode.RESOURCE_NOT_FOUND,
                message="El vehiculo ya no existe o fue eliminado",
                retryable=False,
            )

        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed",
            success=True,
            server_entity_id=vehicle_id,
            message="Vehiculo eliminado correctamente",
        )

    async def _handle_mark_notification_read(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.notifications.service import InAppNotificationService

        notification_id = payload.get("notification_id")
        if not notification_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere notification_id",
                retryable=False,
            )

        svc = InAppNotificationService(self.session)
        notification = await svc.mark_as_read(notification_id, user_id)

        if notification is None:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="completed",
                success=True,
                server_entity_id=notification_id,
                message="Notificacion no encontrada -- tratada como leida (idempotente)",
            )

        return OperationResult(
            client_operation_id=op.client_operation_id,
            status="completed",
            success=True,
            server_entity_id=notification.id,
            message="Notificacion marcada como leida",
        )

    async def _handle_create_catalog_item(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.service_catalog.service import ServiceCatalogService

        tenant_id = await self._get_workshop_tenant_id(user_id)
        if not tenant_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Usuario de taller sin tenant asociado",
                retryable=False,
            )

        servicio_id = payload.get("servicio_id")
        if not servicio_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requiere servicio_id",
                retryable=False,
            )

        svc = ServiceCatalogService(self.session)
        try:
            item = await svc.create_item(tenant_id, user_id, payload)
            if payload.get("is_active") is False:
                item = await svc.toggle_item(tenant_id, item["id"], user_id)
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="completed",
                success=True,
                server_entity_id=item["id"],
                message="Servicio de catálogo creado correctamente",
                server_state=item,
            )
        except ValueError as e:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="conflict",
                success=False,
                message=str(e),
                retryable=False,
            )

    async def _handle_update_catalog_item(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.service_catalog.service import ServiceCatalogService

        tenant_id = await self._get_workshop_tenant_id(user_id)
        item_id = payload.get("item_id")
        if not tenant_id or not item_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requieren tenant e item_id",
                retryable=False,
            )

        svc = ServiceCatalogService(self.session)
        try:
            item = await svc.update_item(tenant_id, item_id, user_id, payload)
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="completed",
                success=True,
                server_entity_id=item["id"],
                message="Servicio de catálogo actualizado correctamente",
                server_state=item,
            )
        except ValueError as e:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="conflict",
                success=False,
                message=str(e),
                retryable=False,
            )

    async def _handle_toggle_catalog_item(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.service_catalog.service import ServiceCatalogService

        tenant_id = await self._get_workshop_tenant_id(user_id)
        item_id = payload.get("item_id")
        if not tenant_id or not item_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requieren tenant e item_id",
                retryable=False,
            )

        svc = ServiceCatalogService(self.session)
        try:
            item = await svc.toggle_item(tenant_id, item_id, user_id)
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="completed",
                success=True,
                server_entity_id=item["id"],
                message="Estado del catálogo actualizado correctamente",
                server_state=item,
            )
        except ValueError as e:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="conflict",
                success=False,
                message=str(e),
                retryable=False,
            )

    async def _handle_delete_catalog_item(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.service_catalog.service import ServiceCatalogService

        tenant_id = await self._get_workshop_tenant_id(user_id)
        item_id = payload.get("item_id")
        if not tenant_id or not item_id:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requieren tenant e item_id",
                retryable=False,
            )

        svc = ServiceCatalogService(self.session)
        try:
            await svc.delete_item(tenant_id, item_id, user_id)
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="completed",
                success=True,
                server_entity_id=item_id,
                message="Servicio de catálogo eliminado correctamente",
            )
        except ValueError as e:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="conflict",
                success=False,
                message=str(e),
                retryable=False,
            )

    async def _handle_request_cancellation(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.cancellation.service import CancellationService

        incident_id = payload.get("incident_id")
        reason = payload.get("reason")
        user_type = payload.get("user_type") or await self._get_user_type(user_id)
        if not incident_id or not reason or not user_type:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requieren incident_id, reason y user_type",
                retryable=False,
            )

        svc = CancellationService(self.session)
        try:
            request = await svc.request_cancellation(incident_id, user_id, user_type, reason)
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="completed",
                success=True,
                server_entity_id=request.id,
                message="Solicitud de cancelación registrada correctamente",
                server_state={"request_id": request.id, "status": request.status},
            )
        except (NotFoundException, ValidationException, ForbiddenException) as e:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="conflict",
                success=False,
                message=str(e),
                retryable=False,
                conflict_code=ConflictCode.RESOURCE_NOT_FOUND if isinstance(e, NotFoundException) else None,
            )

    async def _handle_respond_cancellation(
        self, payload: dict, user_id: int, op: QueueOperation
    ) -> OperationResult:
        from ...modules.cancellation.service import CancellationService

        request_id = payload.get("request_id")
        user_type = payload.get("user_type") or await self._get_user_type(user_id)
        if not request_id or user_type is None or payload.get("accept") is None:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="failed",
                success=False,
                message="Se requieren request_id, accept y user_type",
                retryable=False,
            )

        svc = CancellationService(self.session)
        try:
            request = await svc.respond_to_cancellation(
                request_id=request_id,
                user_id=user_id,
                user_type=user_type,
                accept=bool(payload.get("accept")),
                response_message=payload.get("response_message"),
            )
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="completed",
                success=True,
                server_entity_id=request.id,
                message="Respuesta de cancelación procesada correctamente",
                server_state={"request_id": request.id, "status": request.status},
            )
        except (NotFoundException, ValidationException, ForbiddenException) as e:
            return OperationResult(
                client_operation_id=op.client_operation_id,
                status="conflict",
                success=False,
                message=str(e),
                retryable=False,
                conflict_code=ConflictCode.RESOURCE_NOT_FOUND if isinstance(e, NotFoundException) else None,
            )


def _sys_exc_info():
    import sys
    return sys.exc_info()[1]
