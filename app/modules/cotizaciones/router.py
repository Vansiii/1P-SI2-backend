from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import (
    TenantContext,
    get_current_user_payload,
    require_active_tenant,
)
from app.core.responses import create_success_response

from .schemas import (
    ResponderCotizacionRequest,
    SeleccionarTallerRequest,
    SolicitarCotizacionRequest,
)
from .service import CotizacionService

router = APIRouter(prefix="/cotizaciones")


@router.post("/solicitar")
async def solicitar_cotizacion(
    body: SolicitarCotizacionRequest,
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    client_id = int(user_payload["sub"])
    service = CotizacionService(session)
    try:
        result = await service.solicitar_cotizacion(
            client_id=client_id,
            vehiculo_id=body.vehiculo_id,
            latitud=body.latitud,
            longitud=body.longitud,
            direccion_referencia=body.direccion_referencia,
            descripcion_dano=body.descripcion_dano,
            imagenes_dano=body.imagenes_dano,
            audio_diagnostico=body.audio_diagnostico,
            radio_busqueda_km=body.radio_busqueda_km,
        )
        return create_success_response(data=result, message="Cotizacion solicitada exitosamente")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/")
async def listar_cotizaciones_cliente(
    estado: str | None = Query(default=None),
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    client_id = int(user_payload["sub"])
    service = CotizacionService(session)
    result = await service.get_cotizaciones_cliente(client_id, estado)
    return create_success_response(
        data=result,
        message=f"{len(result)} cotizaciones encontradas",
    )


@router.get("/{cotizacion_id}")
async def get_cotizacion_detalle(
    cotizacion_id: int,
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    user_id = int(user_payload["sub"])
    user_type = user_payload.get("user_type", "")
    service = CotizacionService(session)
    try:
        result = await service.get_cotizacion_detalle(cotizacion_id, user_id, user_type)
        return create_success_response(data=result, message="Detalle de cotizacion")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{cotizacion_id}/detalle")
async def get_cotizacion_detalle_alias(
    cotizacion_id: int,
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    return await get_cotizacion_detalle(cotizacion_id, user_payload, session)


@router.post("/{cotizacion_id}/seleccionar-taller")
async def seleccionar_taller(
    cotizacion_id: int,
    body: SeleccionarTallerRequest,
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    client_id = int(user_payload["sub"])
    service = CotizacionService(session)
    try:
        result = await service.seleccionar_taller(
            cotizacion_id=cotizacion_id,
            respuesta_id=body.cotizacion_respuesta_id,
            client_id=client_id,
        )
        return create_success_response(data=result, message="Taller seleccionado exitosamente")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{cotizacion_id}/cancelar")
async def cancelar_cotizacion(
    cotizacion_id: int,
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    user_id = int(user_payload["sub"])
    user_type = user_payload.get("user_type", "")
    service = CotizacionService(session)
    try:
        result = await service.cancelar_cotizacion(cotizacion_id, user_id, user_type)
        return create_success_response(data=result, message="Cotizacion cancelada")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---- Workshop router ----

workshop_router = APIRouter(prefix="/cotizaciones")


@workshop_router.get("/")
async def listar_cotizaciones_taller(
    user_payload: dict = Depends(get_current_user_payload),
    tenant: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    workshop_id = int(user_payload["sub"])
    tenant_id = tenant.tenant_id
    service = CotizacionService(session)
    try:
        result = await service.get_cotizaciones_taller(workshop_id, tenant_id)
        return create_success_response(
            data=result,
            message=f"{len(result)} cotizaciones en tu zona",
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@workshop_router.get("/{cotizacion_id}")
async def get_cotizacion_taller(
    cotizacion_id: int,
    user_payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_db_session),
):
    user_id = int(user_payload["sub"])
    user_type = user_payload.get("user_type", "")
    service = CotizacionService(session)
    try:
        result = await service.get_cotizacion_detalle(cotizacion_id, user_id, user_type)
        return create_success_response(data=result, message="Detalle de cotizacion")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@workshop_router.post("/{cotizacion_id}/responder")
async def responder_cotizacion(
    cotizacion_id: int,
    body: ResponderCotizacionRequest,
    user_payload: dict = Depends(get_current_user_payload),
    tenant: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    workshop_id = int(user_payload["sub"])
    tenant_id = tenant.tenant_id
    service = CotizacionService(session)
    try:
        servicios_dicts = [s.model_dump() for s in body.servicios]
        result = await service.responder_cotizacion(
            cotizacion_id=cotizacion_id,
            workshop_id=workshop_id,
            tenant_id=tenant_id,
            servicios=servicios_dicts,
            costo_total=body.costo_total,
            tiempo_estimado_minutos=body.tiempo_estimado_minutos,
            tiempo_estimado_texto=body.tiempo_estimado_texto,
            notas=body.notas,
            validez_horas=body.validez_horas,
        )
        return create_success_response(data=result, message="Cotizacion enviada exitosamente")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---- Admin router ----

admin_router = APIRouter(prefix="/admin/cotizaciones")


@admin_router.get("/")
async def listar_cotizaciones_admin(
    estado: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
):
    service = CotizacionService(session)
    result = await service.get_cotizaciones_admin(estado)
    return create_success_response(
        data=result,
        message=f"{len(result)} cotizaciones encontradas",
    )
