"""
Commission Service - Handles commission calculation and workshop balance management.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.logging import get_logger
from ...models.transaction import Transaction
from ...models.workshop_balance import WorkshopBalance
from ...models.financial_movement import WorkshopFinancialMovement
from ...models.platform_commission import PlatformCommission

logger = get_logger(__name__)
settings = get_settings()


class CommissionService:
    """Service for managing commissions and workshop balances."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_commission_and_credit(self, transaction: Transaction) -> None:
        """
        Record platform commission and credit the workshop balance.
        Called after a payment is confirmed via webhook.
        
        1. Create PlatformCommission record.
        2. Get or create WorkshopBalance.
        3. Update available_balance and total_earned.
        4. Record WorkshopFinancialMovement.
        """
        commission_rate = Decimal(str(settings.platform_commission_rate))
        
        # 1. Create PlatformCommission record
        commission = PlatformCommission(
            transaction_id=transaction.id,
            workshop_id=transaction.workshop_id,
            total_amount=transaction.amount,
            commission_rate=commission_rate,
            commission_amount=transaction.commission,
            workshop_amount=transaction.workshop_amount,
        )
        self.session.add(commission)
        
        # 2. Get or create WorkshopBalance
        balance = await self._get_or_create_balance(transaction.workshop_id)
        
        # 3. Update balance
        workshop_amount = Decimal(str(transaction.workshop_amount))
        balance.available_balance = Decimal(str(balance.available_balance)) + workshop_amount
        balance.total_earned = Decimal(str(balance.total_earned)) + workshop_amount
        balance.updated_at = datetime.utcnow()
        
        # 4. Record financial movement
        movement = WorkshopFinancialMovement(
            workshop_id=transaction.workshop_id,
            transaction_id=transaction.id,
            movement_type="payment_received",
            amount=workshop_amount,
            balance_after=balance.available_balance,
            description=f"Pago recibido por servicio - Incidente #{transaction.incident_id}",
        )
        self.session.add(movement)
        
        logger.info(
            f"Commission recorded for transaction {transaction.id}",
            extra={
                "workshop_id": transaction.workshop_id,
                "commission": float(transaction.commission),
                "workshop_amount": float(workshop_amount),
                "new_balance": float(balance.available_balance),
            }
        )

    async def _get_or_create_balance(self, workshop_id: int) -> WorkshopBalance:
        """Get existing balance or create a new one for the workshop."""
        balance = await self.session.scalar(
            select(WorkshopBalance).where(
                WorkshopBalance.workshop_id == workshop_id
            )
        )
        
        if not balance:
            balance = WorkshopBalance(
                workshop_id=workshop_id,
                available_balance=Decimal("0.00"),
                pending_balance=Decimal("0.00"),
                total_earned=Decimal("0.00"),
                total_withdrawn=Decimal("0.00"),
            )
            self.session.add(balance)
            await self.session.flush()
        
        return balance

    async def get_workshop_wallet(self, workshop_id: int) -> dict:
        """Get the workshop's current wallet/balance information."""
        balance = await self._get_or_create_balance(workshop_id)
        return balance.to_dict()

    async def get_financial_history(
        self,
        workshop_id: int,
        page: int = 1,
        size: int = 20,
        movement_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> dict:
        """Get financial movement history for a workshop with filtering."""
        offset = (page - 1) * size
        
        # Build query
        conditions = [WorkshopFinancialMovement.workshop_id == workshop_id]
        
        if movement_type:
            conditions.append(WorkshopFinancialMovement.movement_type == movement_type)
        if date_from:
            conditions.append(WorkshopFinancialMovement.created_at >= date_from)
        if date_to:
            conditions.append(WorkshopFinancialMovement.created_at <= date_to)
        
        # Count total
        total = await self.session.scalar(
            select(func.count(WorkshopFinancialMovement.id)).where(
                and_(*conditions)
            )
        )
        
        # Get movements
        result = await self.session.scalars(
            select(WorkshopFinancialMovement)
            .where(and_(*conditions))
            .order_by(WorkshopFinancialMovement.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        movements = result.all()
        
        return {
            "movements": [m.to_dict() for m in movements],
            "total": total or 0,
            "page": page,
            "size": size,
        }
