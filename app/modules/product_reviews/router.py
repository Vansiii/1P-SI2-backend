from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db_session
from app.core.dependencies import get_current_user
from app.core.responses import create_success_response
from .service import ProductReviewService
from .schemas import ProductReviewCreate

router = APIRouter(prefix="/marketplace/listings", tags=["Product Reviews"])


@router.get("/{listing_id}/reviews")
async def list_reviews(
    listing_id: int,
    session: AsyncSession = Depends(get_db_session)
):
    service = ProductReviewService(session)
    try:
        data = await service.list_reviews_for_listing(listing_id)
        return create_success_response(data=data, message="Reseñas del producto obtenidas exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{listing_id}/reviews")
async def create_review(
    listing_id: int,
    payload: ProductReviewCreate,
    user = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
):
    if payload.listing_id != listing_id:
        raise HTTPException(status_code=400, detail="El listing_id de la ruta no coincide con el cuerpo.")
    
    service = ProductReviewService(session)
    try:
        data = await service.create_review(user.id, payload.model_dump())
        await session.commit()
        return create_success_response(data=data, message="Reseña publicada exitosamente")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
