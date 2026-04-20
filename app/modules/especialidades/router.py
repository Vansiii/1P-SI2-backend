"""
Especialidades router - endpoints for managing specialties.
"""
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...core.database import get_db
from ...core.responses import success_response
from ...models.especialidad import Especialidad
from .schemas import EspecialidadResponse

router = APIRouter(prefix="/specialties")


@router.get("", response_model=dict, status_code=status.HTTP_200_OK)
async def get_all_specialties(
    db: AsyncSession = Depends(get_db)
):
    """
    Get all available specialties.
    
    **Public endpoint** - No authentication required for listing specialties.
    """
    result = await db.execute(select(Especialidad).order_by(Especialidad.nombre))
    especialidades = result.scalars().all()
    
    return success_response(
        data=[
            {
                "id": esp.id,
                "nombre": esp.nombre,
                "descripcion": esp.descripcion
            }
            for esp in especialidades
        ],
        message="Specialties retrieved successfully"
    )


@router.get("/{specialty_id}", response_model=dict, status_code=status.HTTP_200_OK)
async def get_specialty_by_id(
    specialty_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific specialty by ID.
    
    **Public endpoint** - No authentication required.
    """
    result = await db.execute(
        select(Especialidad).where(Especialidad.id == specialty_id)
    )
    especialidad = result.scalar_one_or_none()
    
    if not especialidad:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Specialty {specialty_id} not found"
        )
    
    return success_response(
        data={
            "id": especialidad.id,
            "nombre": especialidad.nombre,
            "descripcion": especialidad.descripcion
        },
        message="Specialty retrieved successfully"
    )
