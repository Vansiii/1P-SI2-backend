from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.core.database import get_db_session
from app.core.dependencies import require_active_tenant, TenantContext, get_current_user, require_feature
from app.core.responses import create_success_response, create_paginated_response
from .service import MarketplaceService
from .schemas import MarketplaceListingCreate, MarketplaceListingUpdate, ListingCompareRequest

router = APIRouter(prefix="/marketplace", tags=["Marketplace"])


# ================= PUBLIC ENDPOINTS =================

@router.get("/listings")
async def list_listings(
    search: Optional[str] = Query(None, description="Buscar por título, marca o nro de parte"),
    category_id: Optional[int] = Query(None, description="Filtrar por categoría"),
    min_price: Optional[float] = Query(None, description="Precio mínimo"),
    max_price: Optional[float] = Query(None, description="Precio máximo"),
    vehicle_brand: Optional[str] = Query(None, description="Marca de vehículo compatible"),
    vehicle_model: Optional[str] = Query(None, description="Modelo de vehículo compatible"),
    workshop_id: Optional[int] = Query(None, description="Filtrar por taller publicante"),
    sort_by: str = Query("newest", description="price_asc, price_desc, rating, newest"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session)
):
    service = MarketplaceService(session)
    filters = {
        "search": search,
        "category_id": category_id,
        "min_price": min_price,
        "max_price": max_price,
        "vehicle_brand": vehicle_brand,
        "vehicle_model": vehicle_model,
        "workshop_id": workshop_id,
        "sort_by": sort_by,
        "page": page,
        "size": size
    }
    items, total = await service.list_listings(filters)
    return create_paginated_response(
        data=items,
        total=total,
        page=page,
        size=size,
    )


@router.post("/listings/compare")
async def compare_listings(
    body: ListingCompareRequest,
    session: AsyncSession = Depends(get_db_session)
):
    service = MarketplaceService(session)
    items = await service.compare_listings(body.listing_ids)
    return create_success_response(data=items, message="Comparación de publicaciones obtenida exitosamente")


@router.get("/workshops")
async def list_workshops_with_listings(
    session: AsyncSession = Depends(get_db_session)
):
    service = MarketplaceService(session)
    data = await service.list_workshops_with_listings()
    return create_success_response(data=data, message="Talleres con publicaciones obtenidos exitosamente")


@router.get("/listings/{listing_id}")
async def get_listing(
    listing_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    service = MarketplaceService(session)
    try:
        data = await service.get_listing(listing_id, increment_view=True)
        return create_success_response(data=data, message="Publicación obtenida exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ================= WORKSHOP ENDPOINTS =================

@router.get("/my-listings")
async def list_my_listings(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller para ver sus publicaciones.")
    
    service = MarketplaceService(session)
    items = await service.list_my_listings(ctx.tenant_id)
    return create_success_response(data=items, message="Sus publicaciones del taller fueron obtenidas exitosamente")


@router.get("/my-listings/stats")
async def get_my_stats(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller para ver estadísticas.")
    
    service = MarketplaceService(session)
    stats = await service.get_my_stats(ctx.tenant_id)
    return create_success_response(data=stats, message="Estadísticas de publicaciones obtenidas exitosamente")


@router.post("/listings")
async def create_listing(
    payload: MarketplaceListingCreate,
    ctx: TenantContext = Depends(require_active_tenant),
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo para publicar.")
    
    service = MarketplaceService(session)
    try:
        data = await service.create_listing(ctx.tenant_id, user.id, payload.model_dump())
        await session.commit()
        return create_success_response(data=data, message="Producto publicado en el marketplace exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/listings/{listing_id}")
async def update_listing(
    listing_id: int,
    payload: MarketplaceListingUpdate,
    ctx: TenantContext = Depends(require_active_tenant),
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo para modificar publicaciones.")
    
    service = MarketplaceService(session)
    try:
        data = await service.update_listing(ctx.tenant_id, listing_id, user.id, payload.model_dump(exclude_unset=True))
        await session.commit()
        return create_success_response(data=data, message="Publicación actualizada exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/listings/{listing_id}")
async def delete_listing(
    listing_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo para eliminar publicaciones.")

    service = MarketplaceService(session)
    try:
        await service.delete_listing(ctx.tenant_id, listing_id, user.id)
        await session.commit()
        return create_success_response(data=None, message="Publicación eliminada del marketplace exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/listings/by-product/{product_id}")
async def delete_listing_by_product(
    product_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    """Despublica el repuesto directamente desde Inventario, sin conocer el listing_id."""
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Debe pertenecer a un taller activo para eliminar publicaciones.")

    service = MarketplaceService(session)
    try:
        await service.delete_listing_by_product(ctx.tenant_id, product_id, user.id)
        await session.commit()
        return create_success_response(data=None, message="Publicación eliminada del marketplace exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
