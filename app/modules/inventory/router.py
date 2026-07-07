from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import require_active_tenant, TenantContext, require_feature
from app.core.responses import create_success_response, create_paginated_response
from .service import InventoryService
from .schemas import (
    InventoryProductCreate,
    InventoryProductUpdate,
    InventoryProductFilter,
    InventoryMovementCreate,
    InventoryCategoryCreate,
    InventoryCategoryUpdate,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])


# === Product Endpoints ===

@router.get("/products")
async def list_products(
    search: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    supplier_id: Optional[int] = Query(None),
    low_stock: Optional[bool] = Query(None),
    out_of_stock: Optional[bool] = Query(None),
    is_published: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    filters = {
        "search": search,
        "category_id": category_id,
        "supplier_id": supplier_id,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "is_published": is_published,
        "is_active": is_active,
        "page": page,
        "size": size
    }
    
    service = InventoryService(session)
    products, total = await service.list_products(ctx.tenant_id, filters)
    return create_paginated_response(data=products, total=total, page=page, size=size)


@router.post("/products")
async def create_product(
    body: InventoryProductCreate,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    try:
        product = await service.create_product(ctx.tenant_id, ctx.user_id, body.model_dump(exclude_none=True))
        await session.commit()
        return create_success_response(data=product, message="Producto registrado correctamente", status_code=status.HTTP_201_CREATED)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/products/low-stock")
async def get_low_stock_products(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    products = await service.get_low_stock_products(ctx.tenant_id)
    return create_success_response(data=products, message="Productos con bajo stock obtenidos correctamente")


@router.get("/products/out-of-stock")
async def get_out_of_stock_products(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    products = await service.get_out_of_stock_products(ctx.tenant_id)
    return create_success_response(data=products, message="Productos agotados obtenidos correctamente")


@router.get("/products/{product_id}")
async def get_product(
    product_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    product = await service.get_product(ctx.tenant_id, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
    return create_success_response(data=product, message="Detalle del producto")


@router.patch("/products/{product_id}")
async def update_product(
    product_id: int,
    body: InventoryProductUpdate,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    try:
        product = await service.update_product(ctx.tenant_id, product_id, ctx.user_id, body.model_dump(exclude_none=True))
        await session.commit()
        return create_success_response(data=product, message="Producto actualizado correctamente")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    try:
        await service.delete_product(ctx.tenant_id, product_id, ctx.user_id)
        await session.commit()
        return create_success_response(data=None, message="Producto eliminado correctamente")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# === Movement Endpoints ===

@router.post("/movements")
async def create_movement(
    body: InventoryMovementCreate,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    try:
        movement = await service.create_movement(ctx.tenant_id, ctx.user_id, body.model_dump(exclude_none=True))
        await session.commit()
        return create_success_response(data=movement, message="Movimiento registrado correctamente", status_code=status.HTTP_201_CREATED)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/movements")
async def list_movements(
    product_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    movements, total = await service.list_movements(ctx.tenant_id, product_id, page, size)
    return create_paginated_response(data=movements, total=total, page=page, size=size)


# === Category Endpoints ===

@router.get("/categories")
async def list_categories(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    categories = await service.list_categories(ctx.tenant_id)
    return create_success_response(data=categories, message="Categorías listadas correctamente")


@router.post("/categories")
async def create_category(
    body: InventoryCategoryCreate,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    try:
        category = await service.create_category(ctx.tenant_id, body.model_dump(exclude_none=True))
        await session.commit()
        return create_success_response(data=category, message="Categoría creada correctamente", status_code=status.HTTP_201_CREATED)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/categories/{category_id}")
async def update_category(
    category_id: int,
    body: InventoryCategoryUpdate,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    try:
        category = await service.update_category(ctx.tenant_id, category_id, body.model_dump(exclude_none=True))
        await session.commit()
        return create_success_response(data=category, message="Categoría actualizada correctamente")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    try:
        await service.delete_category(ctx.tenant_id, category_id)
        await session.commit()
        return create_success_response(data=None, message="Categoría eliminada correctamente")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# === Alert Endpoints ===

@router.get("/alerts")
async def list_alerts(
    unread_only: bool = Query(True),
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    alerts = await service.list_alerts(ctx.tenant_id, unread_only)
    return create_success_response(data=alerts, message="Alertas obtenidas correctamente")


@router.patch("/alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    try:
        alert = await service.mark_alert_read(ctx.tenant_id, alert_id)
        await session.commit()
        return create_success_response(data=alert, message="Alerta marcada como leída")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/alerts/mark-all-read")
async def mark_all_alerts_read(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    count = await service.mark_all_alerts_read(ctx.tenant_id)
    await session.commit()
    return create_success_response(data={"marked_count": count}, message="Todas las alertas marcadas como leídas")


# === Dashboard Endpoint ===

@router.get("/dashboard")
async def get_dashboard(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = InventoryService(session)
    dashboard_data = await service.get_dashboard(ctx.tenant_id)
    return create_success_response(data=dashboard_data, message="Dashboard de inventario cargado correctamente")
