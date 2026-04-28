"""
Withdrawal Service - Handles workshop withdrawal requests.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.logging import get_logger
from ...models.workshop_balance import WorkshopBalance, Withdrawal
from ...models.financial_movement import WorkshopFinancialMovement

logger = get_logger(__name__)
settings = get_settings()


class WithdrawalService:
    """Service for managing workshop withdrawal requests."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def request_withdrawal(
        self,
        workshop_id: int,
        amount: float,
        bank_name: str = None,
        account_number: str = None,
        account_holder: str = None,
        notes: str = None,
    ) -> dict:
        """
        Create a withdrawal request for a workshop.
        
        Validates:
        - Amount >= minimum withdrawal amount
        - Workshop has sufficient available balance
        
        Then:
        - Deducts from available_balance
        - Adds to pending_balance
        - Creates Withdrawal record
        - Records financial movement
        """
        amount_decimal = Decimal(str(amount))
        min_amount = Decimal(str(settings.min_withdrawal_amount))
        
        if amount_decimal < min_amount:
            raise ValueError(
                f"El monto mínimo de retiro es Bs. {min_amount}. "
                f"Solicitaste Bs. {amount_decimal}"
            )
        
        # Get balance
        balance = await self.session.scalar(
            select(WorkshopBalance).where(
                WorkshopBalance.workshop_id == workshop_id
            )
        )
        
        if not balance:
            raise ValueError("No tienes saldo disponible. Aún no has recibido pagos.")
        
        available = Decimal(str(balance.available_balance))
        if available < amount_decimal:
            raise ValueError(
                f"Saldo insuficiente. Disponible: Bs. {available}, "
                f"Solicitado: Bs. {amount_decimal}"
            )
        
        # Deduct from available, add to pending
        balance.available_balance = available - amount_decimal
        balance.pending_balance = Decimal(str(balance.pending_balance)) + amount_decimal
        balance.updated_at = datetime.utcnow()
        
        # Create withdrawal
        withdrawal = Withdrawal(
            workshop_balance_id=balance.id,
            workshop_id=workshop_id,
            amount=amount_decimal,
            status="pending",
            bank_name=bank_name,
            account_number=account_number,
            account_holder=account_holder,
            notes=notes,
        )
        self.session.add(withdrawal)
        await self.session.flush()
        
        # Record financial movement
        movement = WorkshopFinancialMovement(
            workshop_id=workshop_id,
            withdrawal_id=withdrawal.id,
            movement_type="withdrawal_requested",
            amount=-amount_decimal,
            balance_after=balance.available_balance,
            description=f"Solicitud de retiro #{withdrawal.id} por Bs. {amount_decimal}",
        )
        self.session.add(movement)
        
        await self.session.commit()
        await self.session.refresh(withdrawal)
        
        logger.info(
            f"Withdrawal requested for workshop {workshop_id}",
            extra={
                "withdrawal_id": withdrawal.id,
                "amount": float(amount_decimal),
                "new_available": float(balance.available_balance),
            }
        )
        
        return withdrawal.to_dict()

    async def approve_withdrawal(
        self, withdrawal_id: int, admin_id: int, admin_notes: str = None
    ) -> dict:
        """Admin approves a withdrawal request."""
        withdrawal = await self._get_withdrawal(withdrawal_id)
        
        if withdrawal.status != "pending":
            raise ValueError(f"Solo se puede aprobar retiros pendientes. Estado actual: {withdrawal.status}")
        
        withdrawal.status = "approved"
        withdrawal.processed_by = admin_id
        withdrawal.admin_notes = admin_notes
        withdrawal.processed_at = datetime.utcnow()
        
        await self.session.commit()
        
        logger.info(f"Withdrawal {withdrawal_id} approved by admin {admin_id}")
        return withdrawal.to_dict()

    async def reject_withdrawal(
        self, withdrawal_id: int, admin_id: int, admin_notes: str = None
    ) -> dict:
        """
        Admin rejects a withdrawal request.
        Reverses the balance: pending_balance -= amount, available_balance += amount.
        """
        withdrawal = await self._get_withdrawal(withdrawal_id)
        
        if withdrawal.status != "pending":
            raise ValueError(f"Solo se puede rechazar retiros pendientes. Estado actual: {withdrawal.status}")
        
        amount = Decimal(str(withdrawal.amount))
        
        # Reverse balance
        balance = await self.session.scalar(
            select(WorkshopBalance).where(
                WorkshopBalance.workshop_id == withdrawal.workshop_id
            )
        )
        
        if balance:
            balance.available_balance = Decimal(str(balance.available_balance)) + amount
            balance.pending_balance = Decimal(str(balance.pending_balance)) - amount
            balance.updated_at = datetime.utcnow()
        
        withdrawal.status = "rejected"
        withdrawal.processed_by = admin_id
        withdrawal.admin_notes = admin_notes
        withdrawal.processed_at = datetime.utcnow()
        
        # Record reversal movement
        movement = WorkshopFinancialMovement(
            workshop_id=withdrawal.workshop_id,
            withdrawal_id=withdrawal.id,
            movement_type="withdrawal_reversed",
            amount=amount,
            balance_after=balance.available_balance if balance else Decimal("0.00"),
            description=f"Solicitud de retiro #{withdrawal.id} rechazada. Saldo devuelto.",
        )
        self.session.add(movement)
        
        await self.session.commit()
        
        logger.info(f"Withdrawal {withdrawal_id} rejected by admin {admin_id}")
        return withdrawal.to_dict()

    async def mark_withdrawal_paid(
        self, withdrawal_id: int, admin_id: int, admin_notes: str = None
    ) -> dict:
        """
        Admin marks a withdrawal as paid (money transferred).
        pending_balance -= amount, total_withdrawn += amount.
        """
        withdrawal = await self._get_withdrawal(withdrawal_id)
        
        if withdrawal.status != "approved":
            raise ValueError(
                f"Solo se puede marcar como pagado retiros aprobados. Estado actual: {withdrawal.status}"
            )
        
        amount = Decimal(str(withdrawal.amount))
        
        # Update balance
        balance = await self.session.scalar(
            select(WorkshopBalance).where(
                WorkshopBalance.workshop_id == withdrawal.workshop_id
            )
        )
        
        if balance:
            balance.pending_balance = Decimal(str(balance.pending_balance)) - amount
            balance.total_withdrawn = Decimal(str(balance.total_withdrawn)) + amount
            balance.updated_at = datetime.utcnow()
        
        withdrawal.status = "paid"
        withdrawal.processed_by = admin_id
        withdrawal.admin_notes = admin_notes
        withdrawal.completed_at = datetime.utcnow()
        
        # Record completion movement
        movement = WorkshopFinancialMovement(
            workshop_id=withdrawal.workshop_id,
            withdrawal_id=withdrawal.id,
            movement_type="withdrawal_completed",
            amount=-amount,
            balance_after=balance.available_balance if balance else Decimal("0.00"),
            description=f"Retiro #{withdrawal.id} completado. Transferencia realizada.",
        )
        self.session.add(movement)
        
        await self.session.commit()
        
        logger.info(f"Withdrawal {withdrawal_id} marked as paid by admin {admin_id}")
        return withdrawal.to_dict()

    async def get_workshop_withdrawals(
        self, workshop_id: int, page: int = 1, size: int = 20, status: str = None
    ) -> dict:
        """Get withdrawal history for a specific workshop."""
        offset = (page - 1) * size
        conditions = [Withdrawal.workshop_id == workshop_id]
        
        if status:
            conditions.append(Withdrawal.status == status)
        
        total = await self.session.scalar(
            select(func.count(Withdrawal.id)).where(and_(*conditions))
        )
        
        result = await self.session.scalars(
            select(Withdrawal)
            .where(and_(*conditions))
            .order_by(Withdrawal.requested_at.desc())
            .offset(offset)
            .limit(size)
        )
        withdrawals = result.all()
        
        return {
            "withdrawals": [w.to_dict() for w in withdrawals],
            "total": total or 0,
            "page": page,
            "size": size,
        }

    async def get_all_withdrawals(
        self, page: int = 1, size: int = 20, status: str = None
    ) -> dict:
        """Get all withdrawal requests (admin view)."""
        offset = (page - 1) * size
        conditions = []
        
        if status:
            conditions.append(Withdrawal.status == status)
        
        query = select(func.count(Withdrawal.id))
        if conditions:
            query = query.where(and_(*conditions))
        total = await self.session.scalar(query)
        
        withdrawals_query = select(Withdrawal).order_by(Withdrawal.requested_at.desc()).offset(offset).limit(size)
        if conditions:
            withdrawals_query = withdrawals_query.where(and_(*conditions))
        
        result = await self.session.scalars(withdrawals_query)
        withdrawals = result.all()
        
        return {
            "withdrawals": [w.to_dict() for w in withdrawals],
            "total": total or 0,
            "page": page,
            "size": size,
        }

    async def _get_withdrawal(self, withdrawal_id: int) -> Withdrawal:
        """Get a withdrawal by ID or raise error."""
        withdrawal = await self.session.scalar(
            select(Withdrawal).where(Withdrawal.id == withdrawal_id)
        )
        if not withdrawal:
            raise ValueError(f"Solicitud de retiro #{withdrawal_id} no encontrada")
        return withdrawal
