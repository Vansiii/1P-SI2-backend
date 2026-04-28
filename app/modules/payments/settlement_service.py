"""
Settlement Service - Generates financial settlements/liquidations for workshops.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging import get_logger
from ...models.transaction import Transaction
from ...models.workshop_balance import WorkshopBalance, Withdrawal
from ...models.workshop_settlement import WorkshopSettlement

logger = get_logger(__name__)


class SettlementService:
    """Service for generating workshop settlements/liquidations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_settlement(
        self,
        workshop_id: int,
        period_start: datetime,
        period_end: datetime,
        generated_by: int,
        notes: str = None,
    ) -> dict:
        """
        Generate a settlement for a workshop for a given period.
        
        Aggregates:
        - Total collected from clients
        - Total platform commission
        - Total net for workshop
        - Total withdrawn in period
        - Current balance
        """
        # Get completed transactions in period
        transactions = await self.session.scalars(
            select(Transaction).where(
                and_(
                    Transaction.workshop_id == workshop_id,
                    Transaction.status == "completed",
                    Transaction.completed_at >= period_start,
                    Transaction.completed_at <= period_end,
                )
            )
        )
        txns = transactions.all()
        
        total_collected = sum(Decimal(str(t.amount)) for t in txns)
        total_commission = sum(Decimal(str(t.commission)) for t in txns)
        total_net = sum(Decimal(str(t.workshop_amount)) for t in txns)
        
        # Get completed withdrawals in period
        withdrawals = await self.session.scalars(
            select(Withdrawal).where(
                and_(
                    Withdrawal.workshop_id == workshop_id,
                    Withdrawal.status == "paid",
                    Withdrawal.completed_at >= period_start,
                    Withdrawal.completed_at <= period_end,
                )
            )
        )
        wdls = withdrawals.all()
        total_withdrawn = sum(Decimal(str(w.amount)) for w in wdls)
        
        # Get current balance
        balance = await self.session.scalar(
            select(WorkshopBalance).where(
                WorkshopBalance.workshop_id == workshop_id
            )
        )
        balance_at_close = Decimal(str(balance.available_balance)) if balance else Decimal("0.00")
        
        # Create settlement
        settlement = WorkshopSettlement(
            workshop_id=workshop_id,
            period_start=period_start,
            period_end=period_end,
            total_collected=total_collected,
            total_commission=total_commission,
            total_net=total_net,
            total_withdrawn=total_withdrawn,
            balance_at_close=balance_at_close,
            transactions_count=len(txns),
            generated_by=generated_by,
            notes=notes,
        )
        self.session.add(settlement)
        await self.session.commit()
        await self.session.refresh(settlement)
        
        logger.info(
            f"Settlement generated for workshop {workshop_id}",
            extra={
                "settlement_id": settlement.id,
                "period": f"{period_start} - {period_end}",
                "transactions_count": len(txns),
                "total_net": float(total_net),
            }
        )
        
        return settlement.to_dict()

    async def get_workshop_settlements(
        self, workshop_id: int, page: int = 1, size: int = 20
    ) -> dict:
        """Get settlement history for a workshop."""
        offset = (page - 1) * size
        
        total = await self.session.scalar(
            select(func.count(WorkshopSettlement.id)).where(
                WorkshopSettlement.workshop_id == workshop_id
            )
        )
        
        result = await self.session.scalars(
            select(WorkshopSettlement)
            .where(WorkshopSettlement.workshop_id == workshop_id)
            .order_by(WorkshopSettlement.generated_at.desc())
            .offset(offset)
            .limit(size)
        )
        settlements = result.all()
        
        return {
            "settlements": [s.to_dict() for s in settlements],
            "total": total or 0,
            "page": page,
            "size": size,
        }
