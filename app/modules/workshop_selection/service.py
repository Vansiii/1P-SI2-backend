import math
import json
import unicodedata
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.incidente import Incidente
from app.models.workshop import Workshop
from app.models.tenant import Tenant
from app.models.tenant_subscription import TenantSubscription
from app.models.subscription_plan import SubscriptionPlan
from app.models.servicio_taller import ServicioTaller
from app.models.servicio import Servicio
from app.models.categoria import Categoria
from app.models.service_rating import ServiceRating
from app.models.technician import Technician
from app.models.workshop_schedule import WorkshopSchedule
from app.models.assignment_attempt import AssignmentAttempt
from app.models.audit_log import AuditLog
from app.core.event_publisher import EventPublisher

logger = get_logger(__name__)


class WorkshopSelectionService:
    MAX_DISTANCE_KM = 50.0
    DISTANCE_WEIGHT = 0.35
    SPECIALIZATION_WEIGHT = 0.25
    AVAILABILITY_WEIGHT = 0.15
    RATING_WEIGHT = 0.10
    TIME_WEIGHT = 0.15

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_compatible_workshops(
        self, incident_id: int, client_id: int, radius_km: float | None = None
    ) -> list[dict]:
        max_radius = radius_km or self.MAX_DISTANCE_KM

        incident = await self.session.get(Incidente, incident_id)
        if not incident:
            raise ValueError("Incidente no encontrado")
        if incident.client_id != client_id:
            raise PermissionError("No eres el dueño de este incidente")
        if incident.estado_actual not in ("pendiente", "sin_taller_disponible"):
            raise ValueError(f"No se puede seleccionar taller en estado '{incident.estado_actual}'")

        excluded_workshops = []
        if incident.assignment_mode != 'manual':
            excluded_workshops = await self._get_excluded_workshops(incident_id)

        base_conditions = [
            Workshop.is_active == True,
            Workshop.is_verified == True,
            func.sqrt(
                func.pow(Workshop.latitude - incident.latitude, 2) +
                func.pow(Workshop.longitude - incident.longitude, 2)
            ) * 111.32 <= max_radius,
        ]
        if excluded_workshops:
            base_conditions.append(Workshop.id.notin_(excluded_workshops))

        result = await self.session.execute(
            select(Workshop)
            .where(and_(*base_conditions))
            .options(
                selectinload(Workshop.tenant).selectinload(Tenant.subscriptions).selectinload(TenantSubscription.plan),
                selectinload(Workshop.technicians),
                selectinload(Workshop.catalogo).selectinload(ServicioTaller.servicio).selectinload(Servicio.categoria),
            )
        )
        workshops = list(result.scalars().all())

        logger.info(f"📍 Found {len(workshops)} workshops within {max_radius} km (incident location: {incident.latitude}, {incident.longitude})")

        compatible = []
        for workshop in workshops:
            if not self._is_tenant_valid(workshop):
                continue

            distance_km = self._haversine(
                incident.latitude, incident.longitude,
                workshop.latitude, workshop.longitude
            )
            w_coverage = float(workshop.coverage_radius_km) if workshop.coverage_radius_km else max_radius
            if distance_km > w_coverage:
                continue

            matching = await self._get_matching_services(workshop.id, incident.categoria_ia)
            est_time = max((s.get("tiempo_estimado_min") or 0 for s in matching), default=None)

            spec_score = self._calc_specialization_score(matching)
            avail_score = await self._calc_availability_score(workshop)
            rating_data = await self._get_rating_data(workshop.id)
            rating_score = rating_data.get("score", 0.8)
            time_score = self._calc_time_score(est_time)

            score = (
                self._distance_score(distance_km, w_coverage) * self.DISTANCE_WEIGHT +
                spec_score * self.SPECIALIZATION_WEIGHT +
                avail_score * self.AVAILABILITY_WEIGHT +
                rating_score * self.RATING_WEIGHT +
                time_score * self.TIME_WEIGHT
            )

            is_open = self._is_open_now(workshop)

            compatible.append({
                "workshop_id": workshop.id,
                "workshop_name": workshop.workshop_name,
                "description": workshop.description,
                "address": workshop.address,
                "latitude": float(workshop.latitude),
                "longitude": float(workshop.longitude),
                "distance_km": round(distance_km, 2),
                "coverage_radius_km": float(w_coverage) if w_coverage else None,
                "estimated_time_minutes": est_time,
                "rating": rating_data.get("avg_rating"),
                "rating_count": rating_data.get("count", 0),
                "is_available": workshop.is_available,
                "is_open_now": is_open,
                "matching_services": matching[:6],
                "available_technicians": len([
                    t for t in workshop.technicians
                    if t.is_active and t.is_available and not t.is_on_duty
                ]),
                "score": round(score, 3),
            })

        compatible.sort(key=lambda w: (0 if w["is_available"] else 1, -w["score"]))
        return compatible

    async def select_workshop(
        self, incident_id: int, workshop_id: int, client_id: int
    ) -> dict:
        incident = await self.session.get(Incidente, incident_id)
        if not incident:
            raise ValueError("Incidente no encontrado")
        if incident.client_id != client_id:
            raise PermissionError("No eres el dueño de este incidente")
        if incident.estado_actual not in ("pendiente", "sin_taller_disponible"):
            raise ValueError(f"No se puede seleccionar taller en estado '{incident.estado_actual}'")
        if incident.taller_id is not None:
            pending_attempt = await self.session.scalar(
                select(AssignmentAttempt).where(
                    AssignmentAttempt.incident_id == incident_id,
                    AssignmentAttempt.workshop_id == incident.taller_id,
                    AssignmentAttempt.status == "pending",
                )
            )
            if pending_attempt:
                raise ValueError("Ya tienes una solicitud pendiente con este taller. Espera su respuesta.")
            incident.taller_id = None

        result = await self.session.execute(
            select(Workshop)
            .where(Workshop.id == workshop_id)
            .options(
                selectinload(Workshop.tenant).selectinload(Tenant.subscriptions),
            )
        )
        workshop = result.scalar_one_or_none()
        if not workshop:
            raise ValueError("Taller no encontrado")

        if not self._is_tenant_valid(workshop):
            raise ValueError("El taller no esta disponible para recibir solicitudes")

        distance_km = self._haversine(
            incident.latitude, incident.longitude,
            workshop.latitude, workshop.longitude
        )
        w_coverage = workshop.coverage_radius_km or self.MAX_DISTANCE_KM
        if distance_km > w_coverage:
            raise ValueError("El taller esta fuera de su radio de cobertura")

        matching = await self._get_matching_services(workshop.id, incident.categoria_ia)
        if not matching:
            raise ValueError("El taller no ofrece servicios compatibles con tu incidente")

        tenant = workshop.tenant
        tenant_id = tenant.id if tenant else None

        incident.taller_id = workshop_id

        est_time = max((s.get("tiempo_estimado_min") or 0 for s in matching), default=None)

        timeout_minutes = self._get_response_timeout(incident)
        timeout_at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        from datetime import timedelta
        timeout_at = timeout_at + timedelta(minutes=timeout_minutes)

        attempt = AssignmentAttempt(
            incident_id=incident_id,
            workshop_id=workshop_id,
            tenant_id=tenant_id,
            algorithmic_score=1.0,
            final_score=1.0,
            assignment_strategy="client_selection",
            distance_km=round(distance_km, 2),
            status="pending",
            timeout_at=timeout_at,
        )
        self.session.add(attempt)

        self.session.add(AuditLog(
            user_id=client_id,
            tenant_id=tenant_id,
            action="workshop_selected_by_client",
            resource_type="incident",
            resource_id=incident_id,
            ip_address="system",
            details=json.dumps({
                "workshop_id": workshop_id,
                "distance_km": round(distance_km, 2),
                "estimated_time_minutes": est_time,
            }, default=str),
        ))

        await self.session.commit()

        try:
            from app.shared.schemas.events.incident import IncidentAssignedEvent
            event = IncidentAssignedEvent(
                incident_id=incident_id,
                workshop_id=workshop_id,
                workshop_name=workshop.workshop_name,
                estimated_time=timeout_minutes,
                assignment_strategy="client_selection",
            )
            await EventPublisher.publish(self.session, event)
            await self.session.commit()
        except Exception:
            logger.exception("Failed to publish workshop_selected event")

        return {
            "success": True,
            "incident_id": incident_id,
            "workshop_id": workshop_id,
            "workshop_name": workshop.workshop_name,
            "estimated_time_minutes": est_time,
            "message": f"Taller {workshop.workshop_name} seleccionado exitosamente",
        }

    async def get_workshop_profile(self, workshop_id: int) -> Optional[dict]:
        result = await self.session.execute(
            select(Workshop)
            .where(Workshop.id == workshop_id)
            .options(
                selectinload(Workshop.tenant).selectinload(Tenant.subscriptions).selectinload(TenantSubscription.plan),
                selectinload(Workshop.catalogo).selectinload(ServicioTaller.servicio).selectinload(Servicio.categoria),
            )
        )
        workshop = result.scalar_one_or_none()
        if not workshop:
            return None

        if not self._is_tenant_valid(workshop):
            return None

        rating_data = await self._get_rating_data(workshop_id)

        schedules_result = await self.session.execute(
            select(WorkshopSchedule)
            .where(WorkshopSchedule.workshop_id == workshop_id)
            .order_by(WorkshopSchedule.day_of_week)
        )
        schedules = schedules_result.scalars().all()

        active_services = [
            {
                "servicio_id": st.servicio_id,
                "nombre": st.servicio.nombre if st.servicio else "",
                "categoria": st.servicio.categoria.nombre if st.servicio and st.servicio.categoria else "",
                "modalidad": st.modalidad,
                "tiempo_estimado_min": st.tiempo_estimado_min,
                "precio": float(st.precio) if st.precio else None,
            }
            for st in workshop.catalogo
            if st.is_active and st.deleted_at is None
        ]

        days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

        return {
            "workshop_id": workshop.id,
            "workshop_name": workshop.workshop_name,
            "description": workshop.description,
            "address": workshop.address,
            "latitude": float(workshop.latitude),
            "longitude": float(workshop.longitude),
            "coverage_radius_km": float(workshop.coverage_radius_km) if workshop.coverage_radius_km else None,
            "rating": rating_data.get("avg_rating"),
            "rating_count": rating_data.get("count", 0),
            "active_services": active_services,
            "schedules": [
                {
                    "day": days[s.day_of_week] if s.day_of_week < 7 else str(s.day_of_week),
                    "day_of_week": s.day_of_week,
                    "is_open": s.is_open,
                    "open_time": str(s.open_time) if s.open_time else None,
                    "close_time": str(s.close_time) if s.close_time else None,
                }
                for s in schedules
            ],
        }

    async def get_assignment_history(
        self, incident_id: int, workshop_id: int, client_id: int
    ) -> list[dict]:
        result = await self.session.execute(
            select(AssignmentAttempt)
            .where(
                AssignmentAttempt.incident_id == incident_id,
                AssignmentAttempt.workshop_id == workshop_id,
            )
            .order_by(AssignmentAttempt.created_at.desc())
        )
        attempts = result.scalars().all()

        status_labels = {
            "pending": "Pendiente",
            "accepted": "Aceptado",
            "rejected": "Rechazado",
            "timeout": "No respondió",
            "cancelled": "Cancelado",
        }

        return [
            {
                "id": a.id,
                "status": a.status,
                "status_label": status_labels.get(a.status, a.status),
                "assignment_strategy": a.assignment_strategy,
                "distance_km": float(a.distance_km) if a.distance_km else None,
                "final_score": float(a.final_score) if a.final_score else None,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "responded_at": a.responded_at.isoformat() if a.responded_at else None,
                "timeout_at": a.timeout_at.isoformat() if a.timeout_at else None,
                "response_message": a.response_message,
            }
            for a in attempts
        ]

    async def _get_matching_services(
        self, workshop_id: int, categoria_ia: str | None
    ) -> list[dict]:

        def _strip_accents(s: str) -> str:
            return ''.join(
                c for c in unicodedata.normalize('NFKD', s)
                if not unicodedata.combining(c)
            ).lower()

        result = await self.session.execute(
            select(ServicioTaller)
            .join(Servicio, ServicioTaller.servicio_id == Servicio.id)
            .join(Categoria, Servicio.categoria_id == Categoria.id)
            .where(
                ServicioTaller.taller_id == workshop_id,
                ServicioTaller.is_active == True,
                ServicioTaller.deleted_at == None,
            )
            .options(
                selectinload(ServicioTaller.servicio).selectinload(Servicio.categoria),
            )
        )
        items = result.scalars().all()

        if not categoria_ia or categoria_ia.lower() == "otros":
            return [
                {
                    "nombre": item.servicio.nombre if item.servicio else "",
                    "categoria": item.servicio.categoria.nombre if item.servicio and item.servicio.categoria else "",
                    "modalidad": item.modalidad,
                    "tiempo_estimado_min": item.tiempo_estimado_min,
                    "precio": float(item.precio) if item.precio else None,
                }
                for item in items
                if item.servicio and item.servicio.categoria
            ]

        categoria_normalized = _strip_accents(categoria_ia)
        matching = []
        for item in items:
            if not item.servicio or not item.servicio.categoria:
                continue
            cat_norm = _strip_accents(item.servicio.categoria.nombre)
            if categoria_normalized in cat_norm:
                matching.append({
                    "nombre": item.servicio.nombre,
                    "categoria": item.servicio.categoria.nombre,
                    "modalidad": item.modalidad,
                    "tiempo_estimado_min": item.tiempo_estimado_min,
                    "precio": float(item.precio) if item.precio else None,
                })
        return matching

    async def _get_rating_data(self, workshop_id: int) -> dict:
        result = await self.session.execute(
            select(
                func.avg(ServiceRating.rating).label("avg_rating"),
                func.count(ServiceRating.id).label("count"),
            )
            .where(
                ServiceRating.workshop_id == workshop_id,
            )
        )
        row = result.one()
        avg = float(row.avg_rating) if row.avg_rating else None
        count = row.count

        if avg is None:
            return {"avg_rating": None, "count": 0, "score": 0.8}

        score = max(0.3, avg / 5.0)
        return {"avg_rating": round(avg, 1), "count": count, "score": round(score, 3)}

    async def _calc_availability_score(self, workshop: Workshop) -> float:
        available = [
            t for t in workshop.technicians
            if t.is_active and t.is_available and not t.is_on_duty
        ]
        return min(1.0, len(available) / 3.0)

    async def _get_excluded_workshops(self, incident_id: int) -> list[int]:
        result = await self.session.execute(
            select(AssignmentAttempt.workshop_id)
            .where(
                AssignmentAttempt.incident_id == incident_id,
                AssignmentAttempt.status.in_(["rejected", "timeout", "cancelled"]),
            )
        )
        return list(set(row[0] for row in result.all()))

    VALID_SUBSCRIPTION_STATUSES = {
        "active", "trialing", "past_due",
        "pending_downgrade", "pending_cancellation",
    }

    @staticmethod
    def _is_tenant_valid(workshop: Workshop) -> bool:
        tenant = workshop.tenant
        if not tenant:
            return False
        if tenant.status != "active":
            return False
        subscriptions = tenant.subscriptions
        if not subscriptions:
            return False
        active_sub = next(
            (s for s in subscriptions if s.status in WorkshopSelectionService.VALID_SUBSCRIPTION_STATUSES),
            None,
        )
        return active_sub is not None

    @staticmethod
    def _is_open_now(workshop: Workshop) -> bool:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        day = now.weekday()
        day_name = now.strftime("%A")
        for schedule in workshop.schedules if hasattr(workshop, 'schedules') else []:
            if schedule.day_of_week == day:
                if not schedule.is_open:
                    return False
                return True
        return True

    @staticmethod
    def _calc_specialization_score(matching: list[dict]) -> float:
        if not matching:
            return 0.0
        return min(1.0, 0.7 + (len(matching) * 0.1))

    @staticmethod
    def _calc_time_score(est_time_minutes: int | None) -> float:
        if est_time_minutes is None:
            return 0.5
        if est_time_minutes <= 30:
            return 1.0
        if est_time_minutes <= 60:
            return 0.9
        if est_time_minutes <= 120:
            return 0.7
        if est_time_minutes <= 240:
            return 0.5
        return 0.3

    @staticmethod
    def _get_response_timeout(incident: Incidente) -> int:
        from app.core.config import get_settings
        settings = get_settings()
        priority = incident.prioridad_ia.lower() if incident.prioridad_ia else "media"
        if priority in ("alta", "high"):
            return settings.assignment_timeout_high_priority
        elif priority in ("baja", "low"):
            return settings.assignment_timeout_low_priority
        else:
            return settings.assignment_timeout_medium_priority

    @staticmethod
    def _distance_score(distance_km: float, max_radius: float) -> float:
        return max(0.0, 1.0 - (distance_km / max(max_radius, 1.0)))

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371
        lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
        lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
        dlat, dlon = lat2_r - lat1_r, lon2_r - lon1_r
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
