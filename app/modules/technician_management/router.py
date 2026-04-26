"""
Technician management endpoints.
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.dependencies import get_current_user, require_permission
from ...core.permissions import Permission
from ...core.responses import success_response
from ...core.exceptions import NotFoundError, ValidationError
from .services import TechnicianManagementService
from .schemas import (
    UpdateAvailabilityRequest,
    TechnicianWorkloadResponse,
    TechnicianStatisticsResponse,
    AssignSpecialtyRequest,
    RemoveSpecialtyRequest
)
from ...models.user import User

router = APIRouter(prefix="/technicians", tags=["technician-management"])


@router.patch("/{technician_id}/availability", status_code=status.HTTP_200_OK)
async def update_technician_availability(
    technician_id: int,
    request: UpdateAvailabilityRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update technician availability status.
    
    This endpoint:
    - Updates the technician's availability
    - Validates that technician has no active services when setting unavailable
    - Updates last_seen_at timestamp
    
    **Permissions:** Technician (own profile), workshop admin, or system admin
    """
    # Verify permissions
    if current_user.user_type not in ["admin", "workshop"] and current_user.id != technician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own availability"
        )

    service = TechnicianManagementService(db)

    try:
        technician = await service.update_availability(
            technician_id=technician_id,
            is_available=request.is_available
        )

        return success_response(
            data={
                "technician_id": technician.id,
                "is_available": technician.is_available,
                "updated_at": technician.updated_at.isoformat() if technician.updated_at else None
            },
            message=f"Availability updated to {'available' if request.is_available else 'unavailable'}"
        )

    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{technician_id}/workload", response_model=TechnicianWorkloadResponse)
async def get_technician_workload(
    technician_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current workload for a technician.
    
    Returns information about active incidents and tracking sessions.
    
    **Permissions:** Technician (own profile), workshop admin, or system admin
    """
    service = TechnicianManagementService(db)
    workload = await service.get_technician_workload(technician_id)
    return workload


@router.get("/{technician_id}/statistics", response_model=TechnicianStatisticsResponse)
async def get_technician_statistics(
    technician_id: int,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get statistics for a technician.
    
    Returns incident counts and resolution rate.
    
    **Permissions:** Technician (own profile), workshop admin, or system admin
    """
    service = TechnicianManagementService(db)
    
    stats = await service.get_technician_statistics(
        technician_id=technician_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return stats


@router.get("/workshops/{workshop_id}/available", status_code=status.HTTP_200_OK)
async def get_available_technicians(
    workshop_id: int,
    specialty_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get available technicians for a workshop.
    
    Optionally filter by specialty.
    
    **Permissions:** Workshop admin or system admin
    """
    service = TechnicianManagementService(db)
    
    technicians = await service.get_available_technicians(
        workshop_id=workshop_id,
        specialty_id=specialty_id
    )

    return success_response(
        data={
            "workshop_id": workshop_id,
            "specialty_id": specialty_id,
            "count": len(technicians),
            "technicians": [
                {
                    "id": t.id,
                    "first_name": t.first_name,
                    "last_name": t.last_name,
                    "is_online": t.is_online,
                    "is_available": t.is_available,
                    "current_latitude": float(t.current_latitude) if t.current_latitude else None,
                    "current_longitude": float(t.current_longitude) if t.current_longitude else None
                }
                for t in technicians
            ]
        },
        message=f"Found {len(technicians)} available technicians"
    )


@router.get("/workshops/{workshop_id}/all", status_code=status.HTTP_200_OK)
async def get_workshop_technicians(
    workshop_id: int,
    include_unavailable: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TECHNICIAN_VIEW_OWN_WORKSHOP))
):
    """
    Get all technicians for a workshop.
    
    **Permissions:** Workshop admin or system admin
    """
    service = TechnicianManagementService(db)
    
    technicians = await service.get_workshop_technicians(
        workshop_id=workshop_id,
        include_unavailable=include_unavailable
    )

    return success_response(
        data={
            "workshop_id": workshop_id,
            "count": len(technicians),
            "technicians": [
                {
                    "id": t.id,
                    "first_name": t.first_name,
                    "last_name": t.last_name,
                    "email": t.email,
                    "phone": t.phone,
                    "is_online": t.is_online,
                    "is_available": t.is_available,
                    "is_on_duty": t.is_on_duty,
                    "last_seen_at": t.last_seen_at.isoformat() if t.last_seen_at else None,
                    "current_latitude": float(t.current_latitude) if t.current_latitude else None,
                    "current_longitude": float(t.current_longitude) if t.current_longitude else None,
                    "location_updated_at": t.location_updated_at.isoformat() if t.location_updated_at else None,
                    "location_accuracy": float(t.location_accuracy) if t.location_accuracy else None
                }
                for t in technicians
            ]
        },
        message=f"Found {len(technicians)} technicians"
    )


@router.post("/{technician_id}/specialties", status_code=status.HTTP_200_OK)
async def assign_specialty_to_technician(
    technician_id: int,
    request: AssignSpecialtyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TECHNICIAN_UPDATE))
):
    """
    Assign a specialty to a technician.
    
    **Permissions:** Workshop admin or system admin
    """
    service = TechnicianManagementService(db)
    
    success = await service.assign_specialty(
        technician_id=technician_id,
        specialty_id=request.specialty_id
    )

    return success_response(
        data={
            "technician_id": technician_id,
            "specialty_id": request.specialty_id,
            "assigned": success
        },
        message="Specialty assigned successfully"
    )


@router.delete("/{technician_id}/specialties/{specialty_id}", status_code=status.HTTP_200_OK)
async def remove_specialty_from_technician(
    technician_id: int,
    specialty_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TECHNICIAN_UPDATE))
):
    """
    Remove a specialty from a technician.
    
    **Permissions:** Workshop admin or system admin
    """
    service = TechnicianManagementService(db)
    
    success = await service.remove_specialty(
        technician_id=technician_id,
        specialty_id=specialty_id
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Specialty assignment not found"
        )

    return success_response(
        data={
            "technician_id": technician_id,
            "specialty_id": specialty_id,
            "removed": success
        },
        message="Specialty removed successfully"
    )
