from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import require_active_tenant, TenantContext, require_feature
from app.core.responses import create_success_response
from .service import SupplierService
from .schemas import SupplierCreate, SupplierUpdate

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])


@router.get("")
async def list_suppliers(
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = SupplierService(session)
    suppliers = await service.list_suppliers(ctx.tenant_id)
    return create_success_response(data=suppliers, message="Proveedores listados correctamente")


@router.post("")
async def create_supplier(
    body: SupplierCreate,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = SupplierService(session)
    try:
        supplier = await service.create_supplier(ctx.tenant_id, ctx.user_id, body.model_dump(exclude_none=True))
        await session.commit()
        return create_success_response(data=supplier, message="Proveedor creado correctamente", status_code=status.HTTP_201_CREATED)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{supplier_id}")
async def get_supplier(
    supplier_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = SupplierService(session)
    supplier = await service.get_supplier(ctx.tenant_id, supplier_id)
    if not supplier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proveedor no encontrado")
    return create_success_response(data=supplier, message="Detalle del proveedor")


@router.patch("/{supplier_id}")
async def update_supplier(
    supplier_id: int,
    body: SupplierUpdate,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = SupplierService(session)
    try:
        supplier = await service.update_supplier(ctx.tenant_id, supplier_id, ctx.user_id, body.model_dump(exclude_none=True))
        await session.commit()
        return create_success_response(data=supplier, message="Proveedor actualizado correctamente")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{supplier_id}")
async def delete_supplier(
    supplier_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = SupplierService(session)
    try:
        await service.delete_supplier(ctx.tenant_id, supplier_id, ctx.user_id)
        await session.commit()
        return create_success_response(data=None, message="Proveedor eliminado correctamente")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{supplier_id}/products")
async def get_supplier_products(
    supplier_id: int,
    ctx: TenantContext = Depends(require_active_tenant),
    session: AsyncSession = Depends(get_db_session)
):
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso exclusivo para talleres")
    
    service = SupplierService(session)
    products = await service.get_supplier_products(ctx.tenant_id, supplier_id)
    return create_success_response(data=products, message="Productos del proveedor obtenidos correctamente")
