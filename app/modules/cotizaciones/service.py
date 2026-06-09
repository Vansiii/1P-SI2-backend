"""
Cotizaciones Service - CU32: Gestionar Cotizacion del Servicio.
"""
import json
import math
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import stripe
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.event_publisher import EventPublisher
from app.core.logging import get_logger
from app.core.websocket_events import EventTypes
from app.models.assignment_attempt import AssignmentAttempt
from app.models.audit_log import AuditLog
from app.models.cotizacion import Cotizacion
from app.models.cotizacion_chat_sala import CotizacionChatSala
from app.models.cotizacion_respuesta import CotizacionRespuesta
from app.models.incidente import Incidente
from app.models.servicio_taller import ServicioTaller
from app.models.tenant import Tenant
from app.models.vehiculo import Vehiculo
from app.models.workshop import Workshop
from app.models.conversation import Conversation
from app.shared.schemas.events.base import BaseEvent, EventPriority

logger = get_logger(__name__)
settings = get_settings()


def _serialize_servicios_to_jsonb(servicios: list[dict]) -> list[dict]:
    result = []
    for sv in servicios:
        item = dict(sv)
        if "precio" in item and hasattr(item["precio"], "__float__"):
            item["precio"] = float(item["precio"])
        result.append(item)
    return result


class CotizacionService:
    MAX_DISTANCE_KM = 50.0

    def __init__(self, session: AsyncSession):
        self.session = session
        stripe.api_key = settings.stripe_secret_key

    async def solicitar_cotizacion(
        self,
        client_id: int,
        vehiculo_id: int,
        latitud: float,
        longitud: float,
        direccion_referencia: str | None,
        descripcion_dano: str,
        imagenes_dano: list[str],
        audio_diagnostico: str | None,
        radio_busqueda_km: float,
    ) -> dict:
        vehiculo = await self.session.get(Vehiculo, vehiculo_id)
        if not vehiculo:
            raise ValueError("Vehiculo no encontrado")
        if vehiculo.client_id != client_id:
            raise PermissionError("El vehiculo no te pertenece")

        cotizacion = Cotizacion(
            client_id=client_id,
            vehiculo_id=vehiculo_id,
            latitud=latitud,
            longitud=longitud,
            direccion_referencia=direccion_referencia,
            descripcion_dano=descripcion_dano,
            imagenes_dano=imagenes_dano if imagenes_dano else None,
            audio_diagnostico=audio_diagnostico,
            estado="pendiente_cotizacion",
        )
        self.session.add(cotizacion)

        self.session.add(AuditLog(
            user_id=client_id,
            action="cotizacion_solicitada",
            resource_type="cotizacion",
            resource_id=cotizacion.id,
            ip_address="system",
            details=json.dumps({
                "vehiculo_id": vehiculo_id,
                "descripcion_dano": descripcion_dano[:200],
                "latitud": latitud,
                "longitud": longitud,
            }, default=str),
        ))

        await self.session.flush()

        cotizacion.estado = "cotizando"

        await self._run_ai_analysis(cotizacion)

        await self._emitir_evento(
            EventTypes.COTIZACION_SOLICITADA,
            {
                "cotizacion_id": cotizacion.id,
                "client_id": client_id,
                "vehiculo_id": vehiculo_id,
                "descripcion_dano": descripcion_dano[:300],
                "categoria_ia": cotizacion.categoria_ia,
                "ubicacion": {"lat": latitud, "lng": longitud},
                "radio_busqueda_km": radio_busqueda_km,
            },
            EventPriority.HIGH,
            client_id,
        )

        result = {
            "id": cotizacion.id,
            "tenant_id": cotizacion.tenant_id,
            "client_id": cotizacion.client_id,
            "vehiculo_id": cotizacion.vehiculo_id,
            "workshop_id": cotizacion.workshop_id,
            "latitud": float(cotizacion.latitud),
            "longitud": float(cotizacion.longitud),
            "direccion_referencia": cotizacion.direccion_referencia,
            "descripcion_dano": cotizacion.descripcion_dano,
            "imagenes_dano": cotizacion.imagenes_dano,
            "audio_diagnostico": cotizacion.audio_diagnostico,
            "categoria_ia": cotizacion.categoria_ia,
            "prioridad_ia": cotizacion.prioridad_ia,
            "resumen_ia": cotizacion.resumen_ia,
            "es_ambiguo": cotizacion.es_ambiguo,
            "estado": cotizacion.estado,
            "respuestas": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        await self.session.commit()

        return result

    async def get_cotizaciones_cliente(self, client_id: int, estado: str | None = None) -> list[dict]:
        conditions = [Cotizacion.client_id == client_id]
        if estado:
            conditions.append(Cotizacion.estado == estado)

        result = await self.session.execute(
            select(Cotizacion)
            .where(and_(*conditions))
            .options(
                selectinload(Cotizacion.respuestas).selectinload(CotizacionRespuesta.workshop),
                selectinload(Cotizacion.vehiculo),
                selectinload(Cotizacion.workshop),
            )
            .order_by(Cotizacion.created_at.desc())
        )
        cotizaciones = result.scalars().all()
        return [self._serialize_cotizacion_list_item(c) for c in cotizaciones]

    async def get_cotizacion_detalle(self, cotizacion_id: int, user_id: int, user_type: str) -> dict:
        cotizacion = await self.session.scalar(
            select(Cotizacion)
            .where(Cotizacion.id == cotizacion_id)
            .options(
                selectinload(Cotizacion.respuestas).selectinload(CotizacionRespuesta.workshop),
                selectinload(Cotizacion.vehiculo),
                selectinload(Cotizacion.workshop),
                selectinload(Cotizacion.client),
            )
        )
        if not cotizacion:
            raise ValueError("Cotizacion no encontrada")

        if user_type not in ("admin", "administrator"):
            if user_type == "client" and cotizacion.client_id != user_id:
                raise PermissionError("No tienes permiso para ver esta cotizacion")
            if user_type == "workshop" and cotizacion.tenant_id is not None:
                if cotizacion.workshop_id != user_id:
                    raise PermissionError("No tienes permiso para ver esta cotizacion asociada a otro tenant")
        return self._serialize_cotizacion(cotizacion)

    async def get_cotizaciones_taller(self, workshop_id: int, tenant_id: int) -> list[dict]:
        workshop = await self.session.scalar(
            select(Workshop)
            .where(Workshop.id == workshop_id)
            .options(selectinload(Workshop.tenant).selectinload(Tenant.subscriptions))
        )
        if not workshop:
            raise ValueError("Taller no encontrado")

        if not await self._is_tenant_valid(workshop):
            raise PermissionError("Tu cuenta no esta activa para recibir cotizaciones")

        available = workshop.is_available and workshop.is_verified
        if not available:
            return []

        result = await self.session.execute(
            select(Cotizacion)
            .where(
                Cotizacion.estado.in_([
                    "pendiente_cotizacion", "cotizando", "cotizado",
                    "taller_seleccionado", "negociando", "aceptado",
                    "pago_pendiente", "pagado",
                ]),
            )
            .options(
                selectinload(Cotizacion.respuestas).selectinload(CotizacionRespuesta.workshop),
                selectinload(Cotizacion.vehiculo),
                selectinload(Cotizacion.workshop),
            )
            .order_by(Cotizacion.created_at.desc())
        )
        cotizaciones = result.scalars().all()

        w_lat = float(workshop.latitude) if workshop.latitude else 0
        w_lng = float(workshop.longitude) if workshop.longitude else 0
        w_coverage = float(workshop.coverage_radius_km) if workshop.coverage_radius_km else self.MAX_DISTANCE_KM

        nearby = []
        for c in cotizaciones:
            ya_respondio = any(r.workshop_id == workshop_id for r in c.respuestas)

            if c.version == "v2":
                if c.workshop_id != workshop_id:
                    continue
                distance = self._haversine(w_lat, w_lng, float(c.latitud), float(c.longitud))
            else:
                # v1: for estados past "cotizado", only the selected workshop sees it
                if c.estado not in ("pendiente_cotizacion", "cotizando", "cotizado"):
                    if c.workshop_id != workshop_id:
                        continue
                # v1: if another workshop responded but this one didn't, skip
                # (prevent leaking responded cotizaciones across workshops)
                if c.estado == "cotizado" and not ya_respondio:
                    continue
                distance = self._haversine(w_lat, w_lng, float(c.latitud), float(c.longitud))
                if distance > w_coverage:
                    continue
                # v1: only show cotizaciones from the same tenant or tenantless
                if c.tenant_id is not None and c.tenant_id != tenant_id:
                    continue

            item = self._serialize_cotizacion_list_item(c)
            item["distance_km"] = round(distance, 2)
            item["ya_respondio"] = ya_respondio
            nearby.append(item)

        return nearby

    async def responder_cotizacion(
        self,
        cotizacion_id: int,
        workshop_id: int,
        tenant_id: int,
        servicios: list[dict],
        costo_total: Decimal,
        tiempo_estimado_minutos: int,
        tiempo_estimado_texto: str,
        notas: str | None,
        validez_horas: int,
    ) -> dict:
        workshop = await self.session.get(Workshop, workshop_id)
        if not workshop:
            raise ValueError("Taller no encontrado")
        if not await self._is_tenant_valid(workshop):
            raise PermissionError("Tu cuenta no esta activa para enviar cotizaciones")

        cotizacion = await self.session.scalar(
            select(Cotizacion)
            .where(Cotizacion.id == cotizacion_id)
            .options(selectinload(Cotizacion.respuestas))
        )
        if not cotizacion:
            raise ValueError("Cotizacion no encontrada")
        if cotizacion.estado not in ("pendiente_cotizacion", "cotizando", "cotizado"):
            raise ValueError(f"No se puede responder una cotizacion en estado '{cotizacion.estado}'")

        w_lat = float(workshop.latitude) if workshop.latitude else 0
        w_lng = float(workshop.longitude) if workshop.longitude else 0
        w_coverage = float(workshop.coverage_radius_km) if workshop.coverage_radius_km else self.MAX_DISTANCE_KM
        distance = self._haversine(w_lat, w_lng, float(cotizacion.latitud), float(cotizacion.longitud))
        if distance > w_coverage:
            raise ValueError("La cotizacion esta fuera del radio de cobertura de tu taller")

        ya_respondio = any(r.workshop_id == workshop_id for r in cotizacion.respuestas)
        if ya_respondio:
            raise ValueError("Ya has enviado una respuesta a esta cotizacion")

        for sv in servicios:
            existe = await self.session.scalar(
                select(ServicioTaller).where(
                    ServicioTaller.taller_id == workshop_id,
                    ServicioTaller.servicio_id == sv.get("servicio_id"),
                    ServicioTaller.is_active,
                )
            )
            if not existe:
                raise ValueError(f"El servicio '{sv.get('nombre')}' no pertenece a tu catalogo")

        valida_hasta = datetime.now(timezone.utc) + timedelta(hours=validez_horas)

        servicios_jsonb = _serialize_servicios_to_jsonb(servicios)

        respuesta = CotizacionRespuesta(
            cotizacion_id=cotizacion_id,
            workshop_id=workshop_id,
            tenant_id=tenant_id,
            servicios=servicios_jsonb,
            costo_total=costo_total,
            tiempo_estimado_minutos=tiempo_estimado_minutos,
            tiempo_estimado_texto=tiempo_estimado_texto,
            notas=notas,
            valida_hasta=valida_hasta,
            estado="pendiente",
        )
        self.session.add(respuesta)

        if cotizacion.estado != "cotizado":
            cotizacion.estado = "cotizado"
            cotizacion.cotizado_at = datetime.now(timezone.utc)

        self.session.add(AuditLog(
            user_id=workshop_id,
            tenant_id=tenant_id,
            action="cotizacion_respondida",
            resource_type="cotizacion",
            resource_id=cotizacion_id,
            ip_address="system",
            details=json.dumps({
                "costo_total": str(costo_total),
                "tiempo_estimado_minutos": tiempo_estimado_minutos,
                "servicios_count": len(servicios),
            }, default=str),
        ))

        await self.session.flush()

        await self._emitir_evento(
            EventTypes.COTIZACION_RESPUESTA_RECIBIDA,
            {
                "cotizacion_id": cotizacion_id,
                "respuesta_id": respuesta.id,
                "workshop_id": workshop_id,
                "workshop_name": workshop.workshop_name,
                "costo_total": str(costo_total),
                "tiempo_estimado_texto": tiempo_estimado_texto,
            },
            EventPriority.HIGH,
            cotizacion.client_id,
        )

        await self.session.commit()

        return {
            "respuesta_id": respuesta.id,
            "cotizacion_id": cotizacion_id,
            "workshop_id": workshop_id,
            "workshop_name": workshop.workshop_name,
            "costo_total": float(costo_total),
            "tiempo_estimado_texto": tiempo_estimado_texto,
            "valida_hasta": valida_hasta,
        }

    async def seleccionar_taller(
        self, cotizacion_id: int, respuesta_id: int, client_id: int
    ) -> dict:
        cotizacion = await self.session.scalar(
            select(Cotizacion)
            .where(Cotizacion.id == cotizacion_id)
            .options(selectinload(Cotizacion.respuestas))
        )
        if not cotizacion:
            raise ValueError("Cotizacion no encontrada")
        if cotizacion.client_id != client_id:
            raise PermissionError("No tienes permiso para esta cotizacion")
        if cotizacion.estado not in ("cotizado", "pendiente_cotizacion", "cotizando"):
            raise ValueError(f"No se puede seleccionar taller en estado '{cotizacion.estado}'")

        respuesta = None
        for r in cotizacion.respuestas:
            if r.id == respuesta_id:
                respuesta = r
                break
        if not respuesta:
            raise ValueError("Respuesta de taller no encontrada")
        if respuesta.estado != "pendiente":
            raise ValueError("Esta respuesta ya no esta disponible")

        if respuesta.valida_hasta and respuesta.valida_hasta < datetime.now(timezone.utc):
            respuesta.estado = "expirada"
            raise ValueError("Esta cotizacion ha expirado")

        workshop = await self.session.get(Workshop, respuesta.workshop_id)
        if not workshop:
            raise ValueError("Taller no encontrado")

        cotizacion.workshop_id = respuesta.workshop_id
        cotizacion.tenant_id = respuesta.tenant_id
        cotizacion.servicios_cotizados = respuesta.servicios
        cotizacion.costo_total_estimado = respuesta.costo_total
        cotizacion.tiempo_total_estimado_minutos = respuesta.tiempo_estimado_minutos
        cotizacion.notas_cotizacion = respuesta.notas
        cotizacion.estado = "taller_seleccionado"
        cotizacion.taller_seleccionado_at = datetime.now(timezone.utc)

        respuesta.estado = "aceptada"

        for r in cotizacion.respuestas:
            if r.id != respuesta_id and r.estado == "pendiente":
                r.estado = "rechazada"

        incidente_id = cotizacion.incidente_id
        if cotizacion.incidente_id:
            # v2: the incident already exists, update it instead of creating a new one
            incidente = await self.session.get(Incidente, cotizacion.incidente_id)
            if incidente:
                incidente.descripcion = f"{incidente.descripcion}\n\n[Cotizacion aceptada] {float(respuesta.costo_total):.2f} BOB — {respuesta.tiempo_estimado_texto}"
                incidente.taller_id = respuesta.workshop_id
                incidente.estado_actual = "pendiente"
                incidente.assignment_mode = "manual"
                incidente_id = incidente.id
            else:
                incidente = None
                incidente_id = None
        else:
            # v1: no incident yet, create one
            descripcion_completa = cotizacion.descripcion_dano
            if respuesta.servicios:
                svc_names = [s.get("nombre", "") for s in respuesta.servicios if s.get("nombre")]
                if svc_names:
                    descripcion_completa += f"\n\nServicios cotizados: {', '.join(svc_names)}"
                    descripcion_completa += f"\nCosto estimado: {float(respuesta.costo_total):.2f} BOB"
                    descripcion_completa += f"\nTiempo estimado: {respuesta.tiempo_estimado_texto}"

            incidente = Incidente(
                tenant_id=respuesta.tenant_id,
                client_id=cotizacion.client_id,
                vehiculo_id=cotizacion.vehiculo_id,
                taller_id=respuesta.workshop_id,
                latitude=cotizacion.latitud,
                longitude=cotizacion.longitud,
                direccion_referencia=cotizacion.direccion_referencia,
                descripcion=descripcion_completa,
                categoria_ia=cotizacion.categoria_ia,
                prioridad_ia=cotizacion.prioridad_ia,
                resumen_ia=cotizacion.resumen_ia,
                es_ambiguo=cotizacion.es_ambiguo,
                estado_actual="pendiente",
                assignment_mode="manual",
            )
            self.session.add(incidente)
            await self.session.flush()
            incidente_id = incidente.id
            cotizacion.incidente_id = incidente.id

        if not incidente or not incidente_id:
            await self.session.rollback()
            raise ValueError("No se pudo crear o vincular el incidente")

        timeout_minutes = self._get_response_timeout(incidente)
        timeout_at = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)

        w_lat = float(workshop.latitude) if workshop.latitude else 0
        w_lng = float(workshop.longitude) if workshop.longitude else 0
        distance = self._haversine(w_lat, w_lng, float(cotizacion.latitud), float(cotizacion.longitud))

        attempt = AssignmentAttempt(
            incident_id=incidente.id,
            workshop_id=respuesta.workshop_id,
            tenant_id=respuesta.tenant_id,
            algorithmic_score=1.0,
            final_score=1.0,
            assignment_strategy="client_selection",
            distance_km=round(distance, 2),
            status="pending",
            timeout_at=timeout_at,
        )
        self.session.add(attempt)

        self.session.add(AuditLog(
            user_id=client_id,
            action="taller_seleccionado_cotizacion",
            resource_type="cotizacion",
            resource_id=cotizacion_id,
            ip_address="system",
            details=json.dumps({
                "workshop_id": respuesta.workshop_id,
                "costo_total": str(respuesta.costo_total),
                "incidente_id": incidente.id,
            }, default=str),
        ))

        await self.session.flush()

        await self._emitir_evento(
            EventTypes.COTIZACION_TALLER_SELECCIONADO,
            {
                "cotizacion_id": cotizacion_id,
                "incidente_id": incidente.id,
                "workshop_id": respuesta.workshop_id,
                "workshop_name": workshop.workshop_name,
                "costo_total": str(respuesta.costo_total),
            },
            EventPriority.HIGH,
            client_id,
        )

        await self.session.commit()

        return {
            "cotizacion_id": cotizacion_id,
            "incidente_id": incidente.id,
            "workshop_id": respuesta.workshop_id,
            "workshop_name": workshop.workshop_name,
            "costo_total": float(respuesta.costo_total),
            "tiempo_estimado": respuesta.tiempo_estimado_texto,
            "estado": "taller_seleccionado",
        }

    async def procesar_pago_exitoso(self, payment_intent_id: str) -> None:
        result = await self.session.execute(
            select(Cotizacion).where(Cotizacion.stripe_payment_intent_id == payment_intent_id)
        )
        cotizacion = result.scalar_one_or_none()
        if not cotizacion:
            logger.warning(f"No cotizacion found for payment_intent {payment_intent_id}")
            return

        if cotizacion.estado == "pagado":
            return

        cotizacion.estado = "pagado"
        cotizacion.pagado_at = datetime.now(timezone.utc)
        cotizacion.monto_pagado = cotizacion.costo_total_estimado

        commission_rate = Decimal(str(settings.platform_commission_rate))
        amount = Decimal(str(cotizacion.costo_total_estimado))
        commission = (amount * commission_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        self.session.add(AuditLog(
            user_id=cotizacion.client_id,
            tenant_id=cotizacion.tenant_id,
            action="pago_cotizacion_completado",
            resource_type="cotizacion",
            resource_id=cotizacion.id,
            ip_address="system",
            details=json.dumps({
                "amount": str(amount),
                "commission": str(commission),
                "payment_intent_id": payment_intent_id,
            }, default=str),
        ))

        await self._emitir_evento(
            EventTypes.COTIZACION_PAGO_CONFIRMADO,
            {
                "cotizacion_id": cotizacion.id,
                "amount": str(amount),
                "status": "pagado",
            },
            EventPriority.HIGH,
        )

        await self.session.commit()

    async def cancelar_cotizacion(self, cotizacion_id: int, user_id: int, user_type: str) -> dict:
        cotizacion = await self.session.scalar(
            select(Cotizacion)
            .where(Cotizacion.id == cotizacion_id)
            .options(selectinload(Cotizacion.respuestas))
        )
        if not cotizacion:
            raise ValueError("Cotizacion no encontrada")

        if user_type not in ("admin", "administrator"):
            if user_type == "client" and cotizacion.client_id != user_id:
                raise PermissionError("No tienes permiso para cancelar esta cotizacion")
            if user_type == "workshop" and cotizacion.workshop_id != user_id:
                raise PermissionError("No tienes permiso para cancelar esta cotizacion")

        if cotizacion.estado in ("completado", "cancelado", "rechazado"):
            raise ValueError(f"No se puede cancelar una cotizacion en estado '{cotizacion.estado}'")

        cotizacion.estado = "cancelado"

        for r in cotizacion.respuestas:
            if r.estado == "pendiente":
                r.estado = "rechazada"

        self.session.add(AuditLog(
            user_id=user_id,
            tenant_id=cotizacion.tenant_id,
            action="cotizacion_cancelada",
            resource_type="cotizacion",
            resource_id=cotizacion_id,
            ip_address="system",
        ))

        await self.session.flush()

        await self._emitir_evento(
            EventTypes.COTIZACION_CANCELADA,
            {"cotizacion_id": cotizacion_id},
            EventPriority.MEDIUM,
        )

        await self.session.commit()

        return {"cotizacion_id": cotizacion_id, "estado": "cancelado"}

    async def get_cotizaciones_admin(self, estado: str | None = None) -> list[dict]:
        conditions = []
        if estado:
            conditions.append(Cotizacion.estado == estado)

        result = await self.session.execute(
            select(Cotizacion)
            .where(and_(*conditions) if conditions else True)
            .options(
                selectinload(Cotizacion.respuestas).selectinload(CotizacionRespuesta.workshop),
                selectinload(Cotizacion.vehiculo),
                selectinload(Cotizacion.workshop),
            )
            .order_by(Cotizacion.created_at.desc())
            .limit(100)
        )
        return [self._serialize_cotizacion_list_item(c) for c in result.scalars().all()]

    VALID_SUBSCRIPTION_STATUSES = {
        "active", "trialing", "past_due",
        "pending_downgrade", "pending_cancellation",
    }

    async def get_preview(
        self, incidente_id: int, workshop_id: int, client_id: int
    ) -> dict:
        incidente = await self.session.scalar(
            select(Incidente)
            .where(Incidente.id == incidente_id)
            .options(selectinload(Incidente.vehiculo))
        )
        if not incidente:
            raise ValueError("Incidente no encontrado")
        if incidente.client_id != client_id:
            raise PermissionError("El incidente no te pertenece")

        workshop = await self.session.get(Workshop, workshop_id)
        if not workshop:
            raise ValueError("Taller no encontrado")

        w_lat = float(workshop.latitude) if workshop.latitude else 0
        w_lng = float(workshop.longitude) if workshop.longitude else 0
        distance = self._haversine(w_lat, w_lng, incidente.latitude, incidente.longitude)

        servicios_sugeridos = await self._match_servicios_catalogo(
            incidente.categoria_ia or "",
            workshop_id,
            incidente.descripcion or "",
        )

        return {
            "incidente_id": incidente.id,
            "incidente_descripcion": incidente.descripcion or "",
            "incidente_ubicacion": {
                "lat": float(incidente.latitude),
                "lng": float(incidente.longitude),
                "direccion": incidente.direccion_referencia or "",
            },
            "taller_ubicacion": {
                "lat": w_lat,
                "lng": w_lng,
                "nombre": workshop.workshop_name or "Taller",
            },
            "vehiculo_matricula": incidente.vehiculo.matricula if incidente.vehiculo else "",
            "vehiculo_marca": incidente.vehiculo.marca if incidente.vehiculo else "",
            "vehiculo_modelo": incidente.vehiculo.modelo if incidente.vehiculo else "",
            "taller_id": workshop_id,
            "taller_nombre": workshop.workshop_name,
            "servicios_sugeridos": servicios_sugeridos,
            "distancia_km": round(distance, 2),
            "duracion_minutos": round((distance / 40) * 60, 1),
        }

    async def solicitar_desde_incidente(
        self,
        incidente_id: int,
        workshop_id: int,
        client_id: int,
        servicios_seleccionados: list[int],
        descripcion_adicional: str | None,
    ) -> dict:
        incidente = await self.session.scalar(
            select(Incidente)
            .where(Incidente.id == incidente_id)
            .options(selectinload(Incidente.vehiculo))
        )
        if not incidente:
            raise ValueError("Incidente no encontrado")
        if incidente.client_id != client_id:
            raise PermissionError("El incidente no te pertenece")

        workshop = await self.session.get(Workshop, workshop_id)
        if not workshop:
            raise ValueError("Taller no encontrado")
        if not await self._is_tenant_valid(workshop):
            raise PermissionError("El taller no esta disponible para recibir cotizaciones")

        descripcion = incidente.descripcion or ""
        if descripcion_adicional:
            descripcion += f"\n\n[Adicional]: {descripcion_adicional}"

        vehiculo = incidente.vehiculo
        if not vehiculo:
            raise ValueError("El incidente no tiene vehiculo asociado")

        cotizacion = Cotizacion(
            client_id=client_id,
            vehiculo_id=vehiculo.id,
            incidente_id=incidente_id,
            workshop_id=workshop_id,
            latitud=incidente.latitude,
            longitud=incidente.longitude,
            direccion_referencia=incidente.direccion_referencia,
            descripcion_dano=descripcion,
            categoria_ia=incidente.categoria_ia,
            prioridad_ia=incidente.prioridad_ia,
            resumen_ia=incidente.resumen_ia,
            es_ambiguo=incidente.es_ambiguo if incidente.es_ambiguo is not None else False,
            estado="cotizando",
            version="v2",
            tenant_id=workshop.tenant_id,
        )
        self.session.add(cotizacion)

        if servicios_seleccionados:
            servicios_validados = []
            total = Decimal("0")
            tiempo_total = 0
            for st_id in servicios_seleccionados:
                st_result = await self.session.execute(
                    select(ServicioTaller)
                    .where(ServicioTaller.id == st_id)
                    .options(selectinload(ServicioTaller.servicio))
                )
                st = st_result.scalar_one_or_none()
                if not st or st.taller_id != workshop_id or not st.is_active:
                    continue
                precio = st.precio if st.precio else Decimal("0")
                tiempo = st.tiempo_estimado_min if st.tiempo_estimado_min else 0
                servicios_validados.append({
                    "servicio_id": st.id,
                    "nombre": st.servicio.nombre if st.servicio else "",
                    "precio": float(precio),
                    "tiempo_minutos": tiempo,
                })
                total += precio
                tiempo_total += tiempo
            if servicios_validados:
                cotizacion.servicios_cotizados = servicios_validados
                cotizacion.costo_total_estimado = total
                cotizacion.tiempo_total_estimado_minutos = tiempo_total

        self.session.add(AuditLog(
            user_id=client_id,
            tenant_id=workshop.tenant_id,
            action="cotizacion_v2_solicitada",
            resource_type="cotizacion",
            resource_id=cotizacion.id,
            ip_address="system",
            details=json.dumps({
                "incidente_id": incidente_id,
                "workshop_id": workshop_id,
                "version": "v2",
            }, default=str),
        ))

        await self.session.flush()

        await self._run_ai_analysis(cotizacion)

        await self._emitir_evento(
            EventTypes.COTIZACION_SOLICITADA,
            {
                "cotizacion_id": cotizacion.id,
                "client_id": client_id,
                "workshop_id": workshop_id,
                "incidente_id": incidente_id,
                "version": "v2",
                "descripcion_dano": descripcion[:300],
                "categoria_ia": cotizacion.categoria_ia,
                "ubicacion": {"lat": float(incidente.latitude), "lng": float(incidente.longitude)},
            },
            EventPriority.HIGH,
            client_id,
        )

        await self._notificar_push(
            workshop_id,
            "Nueva solicitud de cotizacion",
            f"Un cliente solicito cotizacion para su {vehiculo.marca} {vehiculo.modelo}",
            {"type": "cotizacion_v2", "cotizacion_id": cotizacion.id},
        )

        await self.session.commit()

        return {
            "id": cotizacion.id,
            "incidente_id": incidente_id,
            "workshop_id": workshop_id,
            "workshop_name": workshop.workshop_name,
            "version": "v2",
            "estado": cotizacion.estado,
            "costo_total_estimado": float(cotizacion.costo_total_estimado) if cotizacion.costo_total_estimado else None,
            "created_at": cotizacion.created_at.isoformat() if cotizacion.created_at else None,
        }

    async def aceptar_cotizacion(self, cotizacion_id: int, client_id: int, respuesta_id: int | None = None) -> dict:
        cotizacion = await self.session.scalar(
            select(Cotizacion)
            .where(Cotizacion.id == cotizacion_id)
            .options(selectinload(Cotizacion.respuestas), selectinload(Cotizacion.workshop))
        )
        if not cotizacion:
            raise ValueError("Cotizacion no encontrada")
        if cotizacion.client_id != client_id:
            raise PermissionError("No tienes permiso para esta cotizacion")
        if cotizacion.estado not in ("cotizado", "cotizando", "negociando", "pendiente_cotizacion"):
            raise ValueError(f"No se puede aceptar una cotizacion en estado '{cotizacion.estado}'")

        if respuesta_id:
            respuesta = next((r for r in cotizacion.respuestas if r.id == respuesta_id), None)
            if not respuesta:
                raise ValueError("Respuesta no encontrada")
            if respuesta.estado != "pendiente":
                raise ValueError("La respuesta seleccionada ya no esta disponible")
            if respuesta.valida_hasta and respuesta.valida_hasta < datetime.now(timezone.utc):
                raise ValueError("La respuesta seleccionada ha expirado")
            cotizacion.monto_aceptado = respuesta.costo_total
            # Mark selected as accepted, reject others
            respuesta.estado = "aceptada"
            for r in cotizacion.respuestas:
                if r.id != respuesta_id and r.estado == "pendiente":
                    r.estado = "rechazada"
        elif cotizacion.costo_total_estimado:
            cotizacion.monto_aceptado = cotizacion.costo_total_estimado
        cotizacion.estado = "aceptado"

        if cotizacion.chat_sala_id:
            sala = await self.session.get(CotizacionChatSala, cotizacion.chat_sala_id)
            if sala:
                sala.estado = "cerrada_aceptada"
                sala.cerrada_at = datetime.now(timezone.utc)

        self.session.add(AuditLog(
            user_id=client_id,
            tenant_id=cotizacion.tenant_id,
            action="cotizacion_aceptada",
            resource_type="cotizacion",
            resource_id=cotizacion_id,
            ip_address="system",
            details=json.dumps({"monto_aceptado": str(cotizacion.monto_aceptado)} if cotizacion.monto_aceptado else {}, default=str),
        ))

        await self.session.flush()

        await self._emitir_evento(
            EventTypes.COTIZACION_TALLER_SELECCIONADO,
            {
                "cotizacion_id": cotizacion_id,
                "workshop_id": cotizacion.workshop_id,
                "monto_aceptado": str(cotizacion.monto_aceptado) if cotizacion.monto_aceptado else None,
                "estado": "aceptado",
            },
            EventPriority.HIGH,
            client_id,
        )

        if cotizacion.workshop_id:
            await self._notificar_push(
                cotizacion.workshop_id,
                "Cotizacion aceptada",
                f"El cliente acepto tu cotizacion por ${float(cotizacion.monto_aceptado):.2f}" if cotizacion.monto_aceptado else "El cliente acepto tu cotizacion",
                {"type": "cotizacion_aceptada", "cotizacion_id": cotizacion_id},
            )

        await self.session.commit()

        return {
            "cotizacion_id": cotizacion_id,
            "estado": "aceptado",
            "monto_aceptado": float(cotizacion.monto_aceptado) if cotizacion.monto_aceptado else None,
        }

    async def iniciar_negociacion(self, cotizacion_id: int, client_id: int) -> dict:
        cotizacion = await self.session.scalar(
            select(Cotizacion)
            .where(Cotizacion.id == cotizacion_id)
            .options(selectinload(Cotizacion.workshop))
        )
        if not cotizacion:
            raise ValueError("Cotizacion no encontrada")
        if cotizacion.client_id != client_id:
            raise PermissionError("No tienes permiso para esta cotizacion")
        if cotizacion.estado not in ("cotizado", "cotizando"):
            raise ValueError(f"No se puede negociar una cotizacion en estado '{cotizacion.estado}'")
        if not cotizacion.workshop_id:
            raise ValueError("La cotizacion no tiene taller asignado para negociar")
        if cotizacion.chat_sala_id:
            raise ValueError("Ya se inicio una negociacion para esta cotizacion. Espera la contraoferta del taller.")

        cotizacion.estado = "negociando"

        incident_id = cotizacion.incidente_id or 0
        conversation = Conversation(
            incident_id=incident_id,
            client_id=client_id,
            workshop_id=cotizacion.workshop_id,
            tenant_id=cotizacion.tenant_id,
        )
        self.session.add(conversation)
        await self.session.flush()

        sala = CotizacionChatSala(
            cotizacion_id=cotizacion_id,
            conversation_id=conversation.id,
            client_id=client_id,
            workshop_id=cotizacion.workshop_id,
            tenant_id=cotizacion.tenant_id,
            estado="activa",
        )
        self.session.add(sala)
        await self.session.flush()

        cotizacion.chat_sala_id = sala.id

        self.session.add(AuditLog(
            user_id=client_id,
            tenant_id=cotizacion.tenant_id,
            action="cotizacion_negociacion_iniciada",
            resource_type="cotizacion",
            resource_id=cotizacion_id,
            ip_address="system",
            details=json.dumps({
                "chat_sala_id": sala.id,
                "conversation_id": conversation.id,
            }, default=str),
        ))

        await self.session.flush()

        await self._emitir_evento(
            EventTypes.COTIZACION_RESPUESTA_RECIBIDA,
            {
                "cotizacion_id": cotizacion_id,
                "chat_sala_id": sala.id,
                "conversation_id": conversation.id,
                "estado": "negociando",
            },
            EventPriority.HIGH,
            client_id,
        )

        await self.session.commit()

        return {
            "cotizacion_id": cotizacion_id,
            "chat_sala_id": sala.id,
            "conversation_id": conversation.id,
            "estado": "negociando",
        }

    async def enviar_contraoferta(
        self,
        cotizacion_id: int,
        workshop_id: int,
        tenant_id: int,
        servicios: list[dict],
        costo_total: Decimal,
        tiempo_estimado_minutos: int,
        tiempo_estimado_texto: str,
        notas: str | None,
    ) -> dict:
        cotizacion = await self.session.scalar(
            select(Cotizacion)
            .where(Cotizacion.id == cotizacion_id)
            .options(selectinload(Cotizacion.chat_sala))
        )
        if not cotizacion:
            raise ValueError("Cotizacion no encontrada")
        if cotizacion.workshop_id != workshop_id:
            raise PermissionError("Esta cotizacion no esta dirigida a tu taller")
        if cotizacion.estado != "negociando":
            raise ValueError(f"No se puede enviar contraoferta en estado '{cotizacion.estado}'")

        workshop = await self.session.get(Workshop, workshop_id)
        if not workshop:
            raise ValueError("Taller no encontrado")

        servicios_jsonb = _serialize_servicios_to_jsonb(servicios)

        respuesta = CotizacionRespuesta(
            cotizacion_id=cotizacion_id,
            workshop_id=workshop_id,
            tenant_id=tenant_id,
            servicios=servicios_jsonb,
            costo_total=costo_total,
            tiempo_estimado_minutos=tiempo_estimado_minutos,
            tiempo_estimado_texto=tiempo_estimado_texto,
            notas=notas,
            valida_hasta=datetime.now(timezone.utc) + timedelta(hours=24),
            estado="pendiente",
        )
        self.session.add(respuesta)

        cotizacion.costo_total_estimado = costo_total
        cotizacion.servicios_cotizados = servicios_jsonb
        cotizacion.tiempo_total_estimado_minutos = tiempo_estimado_minutos
        cotizacion.updated_at = datetime.now(timezone.utc)

        if cotizacion.chat_sala and cotizacion.chat_sala_id:
            cotizacion.chat_sala.ultima_oferta_monto = costo_total
            cotizacion.chat_sala.ultima_oferta_at = datetime.now(timezone.utc)

        # Only allow one contraoferta — return to cotizado after sending
        cotizacion.estado = "cotizado"

        self.session.add(AuditLog(
            user_id=workshop_id,
            tenant_id=tenant_id,
            action="cotizacion_contraoferta_enviada",
            resource_type="cotizacion",
            resource_id=cotizacion_id,
            ip_address="system",
            details=json.dumps({
                "costo_total": str(costo_total),
                "tiempo_estimado_minutos": tiempo_estimado_minutos,
                "respuesta_id": respuesta.id,
            }, default=str),
        ))

        await self.session.flush()

        await self._emitir_evento(
            EventTypes.COTIZACION_RESPUESTA_RECIBIDA,
            {
                "cotizacion_id": cotizacion_id,
                "respuesta_id": respuesta.id,
                "workshop_id": workshop_id,
                "workshop_name": workshop.workshop_name,
                "costo_total": str(costo_total),
                "tiempo_estimado_texto": tiempo_estimado_texto,
                "es_contraoferta": True,
            },
            EventPriority.HIGH,
            cotizacion.client_id,
        )

        await self._notificar_push(
            cotizacion.client_id,
            "Taller envio contraoferta",
            f"{workshop.workshop_name} ofrecio ${float(costo_total):.2f} — {tiempo_estimado_texto}",
            {"type": "contraoferta", "cotizacion_id": cotizacion_id, "respuesta_id": respuesta.id},
        )

        await self.session.commit()

        return {
            "respuesta_id": respuesta.id,
            "cotizacion_id": cotizacion_id,
            "workshop_id": workshop_id,
            "costo_total": float(costo_total),
            "tiempo_estimado_texto": tiempo_estimado_texto,
            "valida_hasta": respuesta.valida_hasta.isoformat() if respuesta.valida_hasta else None,
        }

    async def calcular_ruta(self, cotizacion_id: int, user_id: int, user_type: str) -> dict:
        cotizacion = await self.session.scalar(
            select(Cotizacion)
            .where(Cotizacion.id == cotizacion_id)
            .options(selectinload(Cotizacion.workshop), selectinload(Cotizacion.incidente))
        )
        if not cotizacion:
            raise ValueError("Cotizacion no encontrada")

        if user_type not in ("admin", "administrator"):
            if user_type == "client" and cotizacion.client_id != user_id:
                raise PermissionError("No tienes permiso para ver esta ruta")
            if user_type == "workshop" and cotizacion.workshop_id != user_id:
                raise PermissionError("No tienes permiso para ver esta ruta")

        workshop = cotizacion.workshop
        if not workshop:
            raise ValueError("La cotizacion no tiene taller asociado")

        w_lat = float(workshop.latitude) if workshop.latitude else 0
        w_lng = float(workshop.longitude) if workshop.longitude else 0
        if not w_lat or not w_lng:
            raise ValueError("El taller no tiene ubicacion registrada")

        from app.modules.routing.services import RoutingService
        routing = RoutingService()
        try:
            route = await routing.calculate_route(
                w_lat, w_lng,
                float(cotizacion.latitud),
                float(cotizacion.longitud),
            )
        finally:
            await routing.close()

        distancia = route.get("distance_km", 0)
        duracion = route.get("duration_minutes", 0)
        geometry = route.get("geometry")

        polyline = None
        if geometry and geometry.get("coordinates"):
            coords = geometry["coordinates"]
            polyline_data = []
            for c in coords:
                polyline_data.append({"lat": c[1], "lng": c[0]})
            polyline = polyline_data
        elif geometry and isinstance(geometry, dict) and "points" in geometry:
            polyline = geometry["points"]

        incidente_nombre = f"Incidente #{cotizacion.incidente_id}" if cotizacion.incidente_id else f"Cotizacion #{cotizacion_id}"
        taller_nombre = workshop.workshop_name or "Taller"

        return {
            "origen": {
                "lat": float(cotizacion.latitud),
                "lng": float(cotizacion.longitud),
                "nombre": incidente_nombre,
            },
            "destino": {
                "lat": w_lat,
                "lng": w_lng,
                "nombre": taller_nombre,
            },
            "ruta": {
                "polyline": polyline,
                "distancia_km": distancia,
                "duracion_minutos": duracion,
            },
            "fuente": route.get("source", "haversine"),
        }

    async def _match_servicios_catalogo(
        self, categoria_ia: str, workshop_id: int, descripcion: str
    ) -> list[dict]:
        from sqlalchemy.orm import selectinload
        result = await self.session.execute(
            select(ServicioTaller)
            .where(ServicioTaller.taller_id == workshop_id, ServicioTaller.is_active)
            .options(selectinload(ServicioTaller.servicio))
        )
        servicios = result.scalars().all()

        matched = []
        keywords = (categoria_ia + " " + descripcion).lower()
        for sv in servicios:
            motivo = ""
            sv_nombre = (sv.servicio.nombre or "").lower() if sv.servicio else ""
            sv_desc = (sv.descripcion or "").lower()
            if any(kw in sv_nombre or kw in sv_desc for kw in keywords.split() if len(kw) > 2):
                motivo = "Coincide con diagnostico IA"
            else:
                continue
            matched.append({
                "servicio_id": sv.id,
                "nombre": sv.servicio.nombre if sv.servicio else "",
                "precio": float(sv.precio) if sv.precio else 0,
                "tiempo_minutos": sv.tiempo_estimado_min or 0,
                "motivo": motivo,
            })

        return matched[:10]

    async def _is_tenant_valid(self, workshop: Workshop) -> bool:
        result = await self.session.execute(
            select(Tenant)
            .where(Tenant.id == workshop.tenant_id)
            .options(selectinload(Tenant.subscriptions))
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            return False
        if tenant.status != "active":
            return False
        subscriptions = tenant.subscriptions or []
        if not subscriptions:
            return False
        active_sub = next(
            (s for s in subscriptions if s.status in CotizacionService.VALID_SUBSCRIPTION_STATUSES),
            None,
        )
        return active_sub is not None

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371
        lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
        lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
        dlat, dlon = lat2_r - lat1_r, lon2_r - lon1_r
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    async def _emitir_evento(
        self,
        event_type: str,
        data: dict,
        priority: EventPriority = EventPriority.MEDIUM,
        user_id: int | None = None,
    ) -> None:
        try:
            event = BaseEvent(
                event_type=event_type,
                priority=priority,
                metadata={
                    **data,
                    "user_id": user_id,
                } if user_id else data,
            )
            await EventPublisher.publish(self.session, event)
            await self.session.flush()
        except Exception:
            logger.exception(f"Failed to publish event {event_type}")

    async def _notificar_push(
        self, user_id: int, titulo: str, cuerpo: str, data: dict | None = None
    ) -> None:
        try:
            from app.modules.push_notifications.services import PushNotificationService, PushNotificationData
            push = PushNotificationService(self.session)
            notif = PushNotificationData(
                title=titulo,
                body=cuerpo,
                data=data or {},
            )
            await push.send_to_user(user_id, notif)
        except Exception:
            logger.exception(f"Failed to send push notification to user {user_id}")

    @staticmethod
    def _get_response_timeout(incidente: Incidente) -> int:
        priority = incidente.prioridad_ia.lower() if incidente.prioridad_ia else "media"
        if priority in ("alta", "high"):
            return settings.assignment_timeout_high_priority
        elif priority in ("baja", "low"):
            return settings.assignment_timeout_low_priority
        else:
            return settings.assignment_timeout_medium_priority

    async def _run_ai_analysis(self, cotizacion: Cotizacion) -> None:
        from app.modules.incidentes.ai_classifier import GeminiIncidentClassifier
        try:
            classifier = GeminiIncidentClassifier()
            if not classifier.is_enabled:
                logger.info("Gemini AI disabled, skipping cotizacion analysis")
                return
            result = await classifier.classify_incident(
                description=cotizacion.descripcion_dano,
                image_urls=cotizacion.imagenes_dano or [],
                audio_urls=cotizacion.audio_diagnostico or [],
            )
            cls = result.classification
            cotizacion.categoria_ia = cls.category
            cotizacion.prioridad_ia = cls.priority
            cotizacion.resumen_ia = cls.summary
            cotizacion.es_ambiguo = cls.is_ambiguous
            logger.info(f"AI analysis completed for cotizacion {cotizacion.id}: {cls.category}")
        except Exception as e:
            logger.warning(f"AI analysis failed for cotizacion {cotizacion.id}: {e}")

    @staticmethod
    def _safe_get_relationship(obj, attr_name: str):
        from sqlalchemy import inspect
        try:
            state = inspect(obj)
            if not hasattr(state, 'unloaded') or attr_name not in state.unloaded:
                val = getattr(obj, attr_name, None)
                return val or []
        except Exception:
            pass
        return []

    @staticmethod
    def _safe_list(attr: list | None) -> list:
        try:
            return attr or []
        except Exception:
            return []

    @staticmethod
    def _safe_workshop_name(r: CotizacionRespuesta) -> str:
        try:
            if hasattr(r, "workshop") and r.workshop is not None:
                return r.workshop.workshop_name
        except Exception:
            pass
        return ""

    def _serialize_cotizacion(self, c: Cotizacion) -> dict:
        vehiculo = getattr(c, "vehiculo", None)
        try:
            v_matricula = vehiculo.matricula if vehiculo else ""
            v_marca = vehiculo.marca if vehiculo else ""
            v_modelo = vehiculo.modelo if vehiculo else ""
        except Exception:
            v_matricula = ""
            v_marca = ""
            v_modelo = ""
        return {
            "id": c.id,
            "tenant_id": c.tenant_id,
            "client_id": c.client_id,
            "vehiculo_id": c.vehiculo_id,
            "vehiculo_matricula": v_matricula,
            "vehiculo_marca": v_marca,
            "vehiculo_modelo": v_modelo,
            "workshop_id": c.workshop_id,
            "latitud": float(c.latitud),
            "longitud": float(c.longitud),
            "direccion_referencia": c.direccion_referencia,
            "descripcion_dano": c.descripcion_dano,
            "imagenes_dano": c.imagenes_dano,
            "audio_diagnostico": c.audio_diagnostico,
            "categoria_ia": c.categoria_ia,
            "prioridad_ia": c.prioridad_ia,
            "resumen_ia": c.resumen_ia,
            "es_ambiguo": c.es_ambiguo,
            "servicios_cotizados": c.servicios_cotizados,
            "costo_total_estimado": float(c.costo_total_estimado) if c.costo_total_estimado else None,
            "tiempo_total_estimado_minutos": c.tiempo_total_estimado_minutos,
            "notas_cotizacion": c.notas_cotizacion,
            "estado": c.estado,
            "stripe_payment_intent_id": c.stripe_payment_intent_id,
            "monto_pagado": float(c.monto_pagado) if c.monto_pagado else None,
            "monto_aceptado": float(c.monto_aceptado) if c.monto_aceptado else None,
            "version": c.version,
            "incidente_id": c.incidente_id,
            "chat_sala_id": c.chat_sala_id,
            "respuestas": [
                {
                    "id": r.id,
                    "workshop_id": r.workshop_id,
                    "workshop_name": CotizacionService._safe_workshop_name(r),
                    "servicios": r.servicios,
                    "costo_total": float(r.costo_total),
                    "tiempo_estimado_minutos": r.tiempo_estimado_minutos,
                    "tiempo_estimado_texto": r.tiempo_estimado_texto,
                    "notas": r.notas,
                    "valida_hasta": r.valida_hasta.isoformat() if r.valida_hasta else None,
                    "estado": r.estado,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in CotizacionService._safe_get_relationship(c, "respuestas")
            ],
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }

    def _serialize_cotizacion_list_item(self, c: Cotizacion) -> dict:
        vehiculo = getattr(c, "vehiculo", None)
        workshop = getattr(c, "workshop", None)
        try:
            matricula = vehiculo.matricula if vehiculo else ""
            marca = vehiculo.marca if vehiculo else ""
            modelo = vehiculo.modelo if vehiculo else ""
        except Exception:
            matricula = ""
            marca = ""
            modelo = ""
        return {
            "id": c.id,
            "vehiculo_id": c.vehiculo_id,
            "vehiculo_matricula": matricula,
            "vehiculo_marca": marca,
            "vehiculo_modelo": modelo,
            "descripcion_dano": c.descripcion_dano[:200] if c.descripcion_dano else "",
            "categoria_ia": c.categoria_ia,
            "prioridad_ia": c.prioridad_ia,
            "estado": c.estado,
            "costo_total_estimado": float(c.costo_total_estimado) if c.costo_total_estimado else None,
            "taller_nombre": workshop.workshop_name if workshop else None,
            "respuestas_count": len(CotizacionService._safe_get_relationship(c, "respuestas")),
            "incidente_id": c.incidente_id,
            "workshop_id": c.workshop_id,
            "version": c.version,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
