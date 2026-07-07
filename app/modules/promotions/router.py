from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import require_active_tenant, TenantContext, get_current_user
from app.core.responses import create_success_response
from .service import PromotionService
from .schemas import PromotionCreate, PromotionUpdate

router = APIRouter(prefix="/promotions", tags=["Promotions"])


@router.get("")
async def list_promotions(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo.")
    
    service = PromotionService(session)
    data = await service.list_promotions(ctx.tenant_id)
    return create_success_response(data=data, message="Promociones obtenidas exitosamente")


@router.post("")
async def create_promotion(
    payload: PromotionCreate,
    ctx: TenantContext = Depends(require_active_tenant),
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo.")
    
    service = PromotionService(session)
    try:
        data = await service.create_promotion(ctx.tenant_id, user.id, payload.model_dump())
        await session.commit()
        return create_success_response(data=data, message="Promoción creada exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{promo_id}")
async def get_promotion(
    promo_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo.")
    
    service = PromotionService(session)
    try:
        data = await service.get_promotion(ctx.tenant_id, promo_id)
        return create_success_response(data=data, message="Detalle de promoción obtenido exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{promo_id}")
async def update_promotion(
    promo_id: int,
    payload: PromotionUpdate,
    ctx: TenantContext = Depends(require_active_tenant),
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo.")
    
    service = PromotionService(session)
    try:
        data = await service.update_promotion(ctx.tenant_id, promo_id, user.id, payload.model_dump(exclude_unset=True))
        await session.commit()
        return create_success_response(data=data, message="Promoción actualizada exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{promo_id}")
async def delete_promotion(
    promo_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo.")
    
    service = PromotionService(session)
    try:
        await service.delete_promotion(ctx.tenant_id, promo_id, user.id)
        await session.commit()
        return create_success_response(data=None, message="Promoción eliminada exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
