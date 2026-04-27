"""
Admin Router - Admin endpoints for managing withdrawals and settlements.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...core.logging import get_logger
from ...core.responses import create_success_response
from ...core.permissions import Permission
from ...core.dependencies import require_permission
from ...shared.dependencies.auth import get_current_admin
from ...models.administrator import Administrator
from .schemas import AdminWithdrawalActionRequest, GenerateSettlementRequest
from .withdrawal_service import WithdrawalService
from .settlement_service import SettlementService

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin - Finance"])


@router.get(
    "/withdrawals",
    summary="Listar todas las solicitudes de retiro",
    description="Obtener todas las solicitudes de retiro de todos los talleres.",
    dependencies=[Depends(require_permission(Permission.ADMIN_VIEW_ALL_COMMISSIONS))],
)
async def get_all_withdrawals(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filtrar por estado"),
    current_admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """Get all withdrawal requests (admin view)."""
    service = WithdrawalService(session)
    result = await service.get_all_withdrawals(page=page, size=size, status=status)
    return create_success_response(data=result)


@router.patch(
    "/withdrawals/{withdrawal_id}/approve",
    summary="Aprobar solicitud de retiro",
    description="Aprobar una solicitud de retiro pendiente.",
    dependencies=[Depends(require_permission(Permission.ADMIN_VIEW_ALL_COMMISSIONS))],
)
async def approve_withdrawal(
    withdrawal_id: int,
    request: AdminWithdrawalActionRequest = None,
    current_admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """Approve a pending withdrawal request."""
    try:
        service = WithdrawalService(session)
        result = await service.approve_withdrawal(
            withdrawal_id=withdrawal_id,
            admin_id=current_admin.id,
            admin_notes=request.admin_notes if request else None,
        )
        return create_success_response(
            data=result,
            message="Solicitud de retiro aprobada",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch(
    "/withdrawals/{withdrawal_id}/reject",
    summary="Rechazar solicitud de retiro",
    description="Rechazar una solicitud de retiro pendiente. El saldo se devuelve al taller.",
    dependencies=[Depends(require_permission(Permission.ADMIN_VIEW_ALL_COMMISSIONS))],
)
async def reject_withdrawal(
    withdrawal_id: int,
    request: AdminWithdrawalActionRequest = None,
    current_admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """Reject a pending withdrawal request."""
    try:
        service = WithdrawalService(session)
        result = await service.reject_withdrawal(
            withdrawal_id=withdrawal_id,
            admin_id=current_admin.id,
            admin_notes=request.admin_notes if request else None,
        )
        return create_success_response(
            data=result,
            message="Solicitud de retiro rechazada. Saldo devuelto al taller.",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch(
    "/withdrawals/{withdrawal_id}/mark-paid",
    summary="Marcar retiro como pagado",
    description="Marcar una solicitud de retiro aprobada como pagada (dinero transferido).",
    dependencies=[Depends(require_permission(Permission.ADMIN_VIEW_ALL_COMMISSIONS))],
)
async def mark_withdrawal_paid(
    withdrawal_id: int,
    request: AdminWithdrawalActionRequest = None,
    current_admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """Mark an approved withdrawal as paid."""
    try:
        service = WithdrawalService(session)
        result = await service.mark_withdrawal_paid(
            withdrawal_id=withdrawal_id,
            admin_id=current_admin.id,
            admin_notes=request.admin_notes if request else None,
        )
        return create_success_response(
            data=result,
            message="Retiro marcado como pagado",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/workshops/{workshop_id}/settlements",
    summary="Liquidaciones de un taller",
    description="Obtener historial de liquidaciones de un taller específico.",
    dependencies=[Depends(require_permission(Permission.ADMIN_VIEW_ALL_COMMISSIONS))],
)
async def get_workshop_settlements(
    workshop_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """Get settlements for a specific workshop."""
    service = SettlementService(session)
    result = await service.get_workshop_settlements(
        workshop_id=workshop_id, page=page, size=size
    )
    return create_success_response(data=result)


@router.post(
    "/workshops/{workshop_id}/settlements/generate",
    summary="Generar liquidación para un taller",
    description="Generar una nueva liquidación financiera para un taller y período específico.",
    dependencies=[Depends(require_permission(Permission.ADMIN_VIEW_ALL_COMMISSIONS))],
)
async def generate_workshop_settlement(
    workshop_id: int,
    request: GenerateSettlementRequest,
    current_admin: Administrator = Depends(get_current_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """Generate a settlement for a workshop for a given period."""
    try:
        service = SettlementService(session)
        result = await service.generate_settlement(
            workshop_id=workshop_id,
            period_start=request.period_start,
            period_end=request.period_end,
            generated_by=current_admin.id,
            notes=request.notes,
        )
        return create_success_response(
            data=result,
            message="Liquidación generada exitosamente",
            status_code=201,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
