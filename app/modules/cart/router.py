from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import get_current_user
from app.core.responses import create_success_response
from .service import CartService
from .schemas import CartItemCreate, CartItemUpdate

router = APIRouter(prefix="/cart", tags=["Shopping Cart"])


@router.get("")
async def get_cart(
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    service = CartService(session)
    try:
        data = await service.get_cart_summary(user.id)
        return create_success_response(data=data, message="Carrito obtenido exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/items")
async def add_cart_item(
    payload: CartItemCreate,
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    service = CartService(session)
    try:
        data = await service.add_item(user.id, payload.listing_id, payload.quantity)
        await session.commit()
        return create_success_response(data=data, message="Producto añadido al carrito exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/items/{item_id}")
async def update_cart_item(
    item_id: int,
    payload: CartItemUpdate,
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    service = CartService(session)
    try:
        data = await service.update_item(user.id, item_id, payload.quantity)
        await session.commit()
        return create_success_response(data=data, message="Cantidad del carrito actualizada exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/items/{item_id}")
async def remove_cart_item(
    item_id: int,
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    service = CartService(session)
    try:
        data = await service.remove_item(user.id, item_id)
        await session.commit()
        return create_success_response(data=data, message="Producto eliminado del carrito exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("")
async def clear_cart(
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    service = CartService(session)
    try:
        await service.clear_cart(user.id)
        await session.commit()
        return create_success_response(data=None, message="Carrito vaciado exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/validate")
async def validate_cart(
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    service = CartService(session)
    try:
        data = await service.validate_cart_stock(user.id)
        return create_success_response(data=data, message="Validación de stock del carrito completada")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
