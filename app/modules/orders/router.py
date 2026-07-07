from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db_session
from app.core.dependencies import get_current_user, require_active_tenant, TenantContext
from app.core.responses import create_success_response
from .service import OrderService
from .schemas import OrderCheckout, OrderCancelRequest

router = APIRouter(prefix="/orders", tags=["Orders"])


# ================= CLIENT ENDPOINTS =================

@router.post("")
async def checkout_cart(
    payload: OrderCheckout,
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    service = OrderService(session)
    try:
        data = await service.checkout_cart(
            user_id=user.id,
            delivery_type=payload.delivery_type,
            delivery_address=payload.delivery_address,
            delivery_notes=payload.delivery_notes
        )
        await session.commit()
        return create_success_response(data=data, message="Órdenes de compra generadas exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_client_orders(
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    service = OrderService(session)
    try:
        data = await service.list_client_orders(user.id)
        return create_success_response(data=data, message="Historial de órdenes obtenido exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{order_id}")
async def get_client_order(
    order_id: int,
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    service = OrderService(session)
    try:
        data = await service.get_order(order_id)
        if data["client_id"] != user.id:
            raise HTTPException(status_code=403, detail="No tiene permisos para ver esta orden.")
        return create_success_response(data=data, message="Orden obtenida exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{order_id}/pay")
async def pay_order(
    order_id: int,
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    service = OrderService(session)
    try:
        data = await service.create_payment_intent(order_id, user.id)
        await session.commit()
        return create_success_response(data=data, message="Stripe PaymentIntent generado exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ================= WORKSHOP ENDPOINTS =================

@router.get("/workshop/list")
async def list_workshop_orders(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller para ver órdenes.")
    
    service = OrderService(session)
    data = await service.list_workshop_orders(ctx.tenant_id)
    return create_success_response(data=data, message="Órdenes recibidas obtenidas exitosamente")


@router.get("/workshop/{order_id}")
async def get_workshop_order(
    order_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller.")
    
    service = OrderService(session)
    try:
        data = await service.get_order(order_id)
        if data["tenant_id"] != ctx.tenant_id:
            raise HTTPException(status_code=403, detail="No tiene permisos para ver esta orden del taller.")
        return create_success_response(data=data, message="Detalle de orden obtenido exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/workshop/{order_id}/confirm")
async def confirm_order(
    order_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo.")
    
    service = OrderService(session)
    try:
        data = await service.update_order_status(ctx.tenant_id, order_id, "confirm")
        await session.commit()
        return create_success_response(data=data, message="Orden confirmada exitosamente por el taller")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/workshop/{order_id}/prepare")
async def prepare_order(
    order_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo.")
    
    service = OrderService(session)
    try:
        data = await service.update_order_status(ctx.tenant_id, order_id, "prepare")
        await session.commit()
        return create_success_response(data=data, message="Orden marcada en preparación")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/workshop/{order_id}/ready")
async def ready_order(
    order_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo.")
    
    service = OrderService(session)
    try:
        data = await service.update_order_status(ctx.tenant_id, order_id, "ready")
        await session.commit()
        return create_success_response(data=data, message="Orden marcada lista para retiro/despacho")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/workshop/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    payload: OrderCancelRequest,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo.")
    
    service = OrderService(session)
    try:
        data = await service.update_order_status(ctx.tenant_id, order_id, "cancel", payload.reason)
        await session.commit()
        return create_success_response(data=data, message="Orden cancelada exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
