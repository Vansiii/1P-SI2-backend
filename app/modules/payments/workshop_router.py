"""
Workshop Router - Workshop-facing endpoints for wallet and withdrawals.
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
from ...shared.dependencies.auth import get_current_workshop_user
from ...models.workshop import Workshop
from .schemas import CreateWithdrawalRequest
from .commission_service import CommissionService
from .withdrawal_service import WithdrawalService

logger = get_logger(__name__)

router = APIRouter(prefix="/workshops/me", tags=["Workshop Finance"])


@router.get(
    "/wallet",
    summary="Ver saldo del taller",
    description="Obtener información del wallet/saldo del taller autenticado.",
    dependencies=[Depends(require_permission(Permission.COMMISSION_VIEW_OWN))],
)
async def get_my_wallet(
    current_user: Workshop = Depends(get_current_workshop_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get the authenticated workshop's wallet information."""
    service = CommissionService(session)
    result = await service.get_workshop_wallet(workshop_id=current_user.id)
    return create_success_response(data=result)


@router.get(
    "/financial-history",
    summary="Historial financiero del taller",
    description="Obtener el historial de movimientos financieros del taller autenticado.",
    dependencies=[Depends(require_permission(Permission.COMMISSION_VIEW_OWN))],
)
async def get_my_financial_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    movement_type: Optional[str] = Query(None, description="Filtrar por tipo de movimiento"),
    date_from: Optional[datetime] = Query(None, description="Fecha inicio (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="Fecha fin (ISO 8601)"),
    current_user: Workshop = Depends(get_current_workshop_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get financial movement history for the authenticated workshop."""
    service = CommissionService(session)
    result = await service.get_financial_history(
        workshop_id=current_user.id,
        page=page,
        size=size,
        movement_type=movement_type,
        date_from=date_from,
        date_to=date_to,
    )
    return create_success_response(data=result)


@router.post(
    "/withdrawals",
    summary="Solicitar retiro de dinero",
    description="Crear una solicitud de retiro cuando el saldo sea suficiente.",
    dependencies=[Depends(require_permission(Permission.COMMISSION_VIEW_OWN))],
)
async def request_withdrawal(
    request: CreateWithdrawalRequest,
    current_user: Workshop = Depends(get_current_workshop_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Request a withdrawal from the workshop's available balance."""
    try:
        service = WithdrawalService(session)
        result = await service.request_withdrawal(
            workshop_id=current_user.id,
            amount=request.amount,
            bank_name=request.bank_name,
            account_number=request.account_number,
            account_holder=request.account_holder,
            notes=request.notes,
        )
        return create_success_response(
            data=result,
            message="Solicitud de retiro creada exitosamente",
            status_code=201,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/withdrawals",
    summary="Listar mis solicitudes de retiro",
    description="Obtener las solicitudes de retiro del taller autenticado.",
    dependencies=[Depends(require_permission(Permission.COMMISSION_VIEW_OWN))],
)
async def get_my_withdrawals(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filtrar por estado"),
    current_user: Workshop = Depends(get_current_workshop_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get withdrawal history for the authenticated workshop."""
    service = WithdrawalService(session)
    result = await service.get_workshop_withdrawals(
        workshop_id=current_user.id,
        page=page,
        size=size,
        status=status,
    )
    return create_success_response(data=result)
