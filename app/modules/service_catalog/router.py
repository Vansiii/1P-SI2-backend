from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import require_active_tenant, TenantContext
from app.core.responses import create_success_response
from .service import ServiceCatalogService
from .schemas import (
    ServiceCatalogItemCreate,
    ServiceCatalogItemUpdate,
)

router = APIRouter(prefix="/workshop/catalog", tags=["Workshop - Catalog"])


@router.get("")
async def list_catalog(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Acceso solo para talleres")
    service = ServiceCatalogService(session)
    items = await service.get_catalog(ctx.tenant_id)
    return create_success_response(data=items, message="Catalogo de servicios")


@router.post("/items")
async def create_catalog_item(
    body: ServiceCatalogItemCreate,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Acceso solo para talleres")
    service = ServiceCatalogService(session)
    try:
        item = await service.create_item(
            ctx.tenant_id, ctx.user_id, body.model_dump(exclude_none=True)
        )
        return create_success_response(data=item, message="Servicio agregado al catalogo")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/items/{item_id}")
async def get_catalog_item(
    item_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Acceso solo para talleres")
    service = ServiceCatalogService(session)
    item = await service.get_item(ctx.tenant_id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    return create_success_response(data=item, message="Detalle del servicio")


@router.patch("/items/{item_id}")
async def update_catalog_item(
    item_id: int,
    body: ServiceCatalogItemUpdate,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Acceso solo para talleres")
    service = ServiceCatalogService(session)
    try:
        item = await service.update_item(
            ctx.tenant_id, item_id, ctx.user_id,
            body.model_dump(exclude_none=True)
        )
        return create_success_response(data=item, message="Servicio actualizado")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/items/{item_id}/toggle")
async def toggle_catalog_item(
    item_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Acceso solo para talleres")
    service = ServiceCatalogService(session)
    try:
        item = await service.toggle_item(ctx.tenant_id, item_id, ctx.user_id)
        estado = "activado" if item["is_active"] else "desactivado"
        return create_success_response(data=item, message=f"Servicio {estado}")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/items/{item_id}")
async def delete_catalog_item(
    item_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session),
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Acceso solo para talleres")
    service = ServiceCatalogService(session)
    try:
        await service.delete_item(ctx.tenant_id, item_id, ctx.user_id)
        return create_success_response(data=None, message="Servicio eliminado del catalogo")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# === Endpoints publicos ===

public_router = APIRouter(prefix="/catalog", tags=["Catalog - Public"])


@public_router.get("/categories")
async def list_categories(
    session: AsyncSession = Depends(get_db_session),
):
    service = ServiceCatalogService(session)
    items = await service.get_categories()
    return create_success_response(data=items, message="Categorias disponibles")


@public_router.get("/services")
async def list_base_services(
    session: AsyncSession = Depends(get_db_session),
):
    service = ServiceCatalogService(session)
    items = await service.get_base_services()
    return create_success_response(data=items, message="Servicios base")
