"""
Payment Service - Handles Stripe integration and payment processing.
"""
import stripe
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.logging import get_logger
from ...models.transaction import Transaction
from ...models.incidente import Incidente
from ...models.client import Client
from ...models.workshop import Workshop
from ...models.stripe_event_log import StripeEventLog

logger = get_logger(__name__)
settings = get_settings()


class PaymentService:
    """Service for managing payments and Stripe integration."""

    def __init__(self, session: AsyncSession):
        self.session = session
        stripe.api_key = settings.stripe_secret_key

    async def create_payment_intent(
        self, client_id: int, incident_id: int
    ) -> dict:
        """
        Create a Stripe PaymentIntent for an incident.
        
        1. Validates the incident is resolved and belongs to the client.
        2. Checks no completed payment exists for this incident.
        3. Creates a Stripe PaymentIntent.
        4. Records a pending Transaction in the database.
        
        Returns dict with client_secret and transaction details.
        """
        # 1. Validate incident
        incident = await self.session.scalar(
            select(Incidente).where(Incidente.id == incident_id)
        )
        if not incident:
            raise ValueError("Incidente no encontrado")
        
        if incident.client_id != client_id:
            raise PermissionError("No tienes permiso para pagar este incidente")
        
        if incident.estado_actual != "resuelto":
            raise ValueError(
                f"El incidente debe estar resuelto para poder pagarlo. "
                f"Estado actual: {incident.estado_actual}"
            )
        
        if not incident.taller_id:
            raise ValueError("El incidente no tiene un taller asignado")

        # 2. Check for existing completed payment
        existing_payment = await self.session.scalar(
            select(Transaction).where(
                and_(
                    Transaction.incident_id == incident_id,
                    Transaction.status == "completed"
                )
            )
        )
        if existing_payment:
            raise ValueError("Este incidente ya tiene un pago completado")

        # Check for existing pending payment (reuse it)
        pending_payment = await self.session.scalar(
            select(Transaction).where(
                and_(
                    Transaction.incident_id == incident_id,
                    Transaction.status == "pending",
                    Transaction.stripe_payment_intent_id.isnot(None)
                )
            )
        )
        
        if pending_payment:
            # Return existing pending payment's client_secret
            try:
                pi = stripe.PaymentIntent.retrieve(pending_payment.stripe_payment_intent_id)
                if pi.status in ("requires_payment_method", "requires_confirmation", "requires_action"):
                    return {
                        "transaction_id": pending_payment.id,
                        "client_secret": pi.client_secret,
                        "stripe_payment_intent_id": pi.id,
                        "amount": float(pending_payment.amount),
                        "commission": float(pending_payment.commission),
                        "workshop_amount": float(pending_payment.workshop_amount),
                        "publishable_key": settings.stripe_publishable_key,
                    }
                elif pi.status == "succeeded":
                    # Proactively handle success if webhook hasn't fired yet
                    await self.handle_payment_succeeded(pi.id)
                    raise ValueError("Este incidente ya tiene un pago completado")
            except ValueError as e:
                raise e
            except Exception as e:
                logger.warning(f"Could not reuse pending payment intent: {e}")
                # If we can't reuse, create a new one

        # 3. Calculate amounts
        # For now, use a fixed amount. In production, this would come from service pricing.
        amount = Decimal("150.00")  # TODO: Get from incident/service pricing
        commission_rate = Decimal(str(settings.platform_commission_rate))
        commission = (amount * commission_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        workshop_amount = amount - commission
        
        # Stripe expects amounts in cents (smallest currency unit)
        amount_cents = int(amount * 100)
        
        # 4. Create Stripe PaymentIntent
        idempotency_key = f"incident_{incident_id}_payment"
        
        try:
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="bob",  # Bolivianos
                metadata={
                    "incident_id": str(incident_id),
                    "client_id": str(client_id),
                    "workshop_id": str(incident.taller_id),
                },
                automatic_payment_methods={"enabled": True},
                idempotency_key=idempotency_key,
            )
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating PaymentIntent: {e}")
            raise ValueError(f"Error al procesar el pago: {str(e)}")

        # 5. Create Transaction record
        receipt_number = f"REC-{datetime.utcnow().strftime('%Y%m%d')}-{incident_id:06d}"
        
        transaction = Transaction(
            incident_id=incident_id,
            workshop_id=incident.taller_id,
            client_id=client_id,
            amount=amount,
            commission=commission,
            workshop_amount=workshop_amount,
            status="pending",
            payment_method="card",
            stripe_payment_intent_id=payment_intent.id,
            idempotency_key=idempotency_key,
            receipt_number=receipt_number,
            description=f"Pago por servicio de emergencia vehicular - Incidente #{incident_id}",
        )
        self.session.add(transaction)
        await self.session.commit()
        await self.session.refresh(transaction)

        logger.info(
            f"PaymentIntent created for incident {incident_id}",
            extra={
                "transaction_id": transaction.id,
                "amount": float(amount),
                "stripe_pi": payment_intent.id,
            }
        )

        return {
            "transaction_id": transaction.id,
            "client_secret": payment_intent.client_secret,
            "stripe_payment_intent_id": payment_intent.id,
            "amount": float(amount),
            "commission": float(commission),
            "workshop_amount": float(workshop_amount),
            "publishable_key": settings.stripe_publishable_key,
        }

    async def handle_payment_succeeded(self, payment_intent_id: str) -> Optional[Transaction]:
        """
        Handle a successful payment (called from webhook).
        
        1. Find the transaction by stripe_payment_intent_id.
        2. Mark as completed.
        3. Calculate commission and update workshop balance.
        4. Record financial movement.
        """
        from .commission_service import CommissionService
        
        transaction = await self.session.scalar(
            select(Transaction).where(
                Transaction.stripe_payment_intent_id == payment_intent_id
            )
        )
        
        if not transaction:
            logger.error(f"Transaction not found for PaymentIntent: {payment_intent_id}")
            return None
        
        if transaction.status == "completed":
            logger.info(f"Transaction {transaction.id} already completed, skipping")
            return transaction
        
        # Mark as completed
        transaction.status = "completed"
        transaction.completed_at = datetime.utcnow()
        
        # Calculate and record commission
        commission_service = CommissionService(self.session)
        await commission_service.record_commission_and_credit(transaction)
        
        await self.session.commit()
        
        logger.info(
            f"Payment completed for transaction {transaction.id}",
            extra={
                "incident_id": transaction.incident_id,
                "amount": float(transaction.amount),
                "workshop_id": transaction.workshop_id,
            }
        )
        
        return transaction

    async def handle_payment_failed(self, payment_intent_id: str, failure_reason: str = None) -> Optional[Transaction]:
        """Handle a failed payment (called from webhook)."""
        transaction = await self.session.scalar(
            select(Transaction).where(
                Transaction.stripe_payment_intent_id == payment_intent_id
            )
        )
        
        if not transaction:
            logger.error(f"Transaction not found for PaymentIntent: {payment_intent_id}")
            return None
        
        transaction.status = "failed"
        transaction.failure_reason = failure_reason or "Payment failed"
        
        await self.session.commit()
        
        logger.info(f"Payment failed for transaction {transaction.id}: {failure_reason}")
        return transaction

    async def get_client_payments(
        self, client_id: int, page: int = 1, size: int = 20
    ) -> dict:
        """Get payment history for a client."""
        offset = (page - 1) * size
        
        # Count total
        total = await self.session.scalar(
            select(func.count(Transaction.id)).where(
                Transaction.client_id == client_id
            )
        )
        
        # Get payments
        result = await self.session.scalars(
            select(Transaction)
            .where(Transaction.client_id == client_id)
            .order_by(Transaction.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        payments = result.all()
        
        return {
            "payments": [p.to_dict() for p in payments],
            "total": total or 0,
            "page": page,
            "size": size,
        }

    async def get_incident_payment_status(self, incident_id: int, client_id: int) -> dict:
        """Check if an incident has a completed payment and return its transaction ID."""
        from sqlalchemy import and_
        
        # 1. First check for a completed transaction
        transaction = await self.session.scalar(
            select(Transaction).where(
                and_(
                    Transaction.incident_id == incident_id,
                    Transaction.client_id == client_id,
                    Transaction.status == "completed"
                )
            )
        )
        
        if transaction:
            return {
                "is_paid": True,
                "transaction_id": transaction.id
            }
            
        # 2. If not completed, check if there is a pending transaction with a Stripe intent
        pending_tx = await self.session.scalar(
            select(Transaction).where(
                and_(
                    Transaction.incident_id == incident_id,
                    Transaction.client_id == client_id,
                    Transaction.status == "pending",
                    Transaction.stripe_payment_intent_id.isnot(None)
                )
            )
        )
        
        if pending_tx:
            # Proactively check Stripe
            try:
                pi = stripe.PaymentIntent.retrieve(pending_tx.stripe_payment_intent_id)
                if pi.status == "succeeded":
                    # Force handle payment success
                    completed_tx = await self.handle_payment_succeeded(pi.id)
                    if completed_tx:
                        return {
                            "is_paid": True,
                            "transaction_id": completed_tx.id
                        }
            except Exception as e:
                logger.error(f"Could not proactively verify payment intent status: {e}", exc_info=True)
                
        return {"is_paid": False}

    async def get_payment_receipt(self, transaction_id: int, client_id: int) -> dict:
        """Get payment receipt for a specific transaction."""
        transaction = await self.session.scalar(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        
        if not transaction:
            raise ValueError("Transacción no encontrada")
        
        if transaction.client_id != client_id:
            raise PermissionError("No tienes permiso para ver este comprobante")
        
        if transaction.status == "pending" and transaction.stripe_payment_intent_id:
            # Proactively check Stripe in case webhook was missed
            try:
                pi = stripe.PaymentIntent.retrieve(transaction.stripe_payment_intent_id)
                if pi.status == "succeeded":
                    completed_tx = await self.handle_payment_succeeded(pi.id)
                    if completed_tx:
                        transaction = completed_tx
            except Exception as e:
                logger.error(f"Could not proactively verify payment intent: {e}", exc_info=True)

        if transaction.status != "completed":
            raise ValueError("Solo se puede generar comprobante para pagos completados")
        
        # Get related entities
        client = await self.session.scalar(
            select(Client).where(Client.id == transaction.client_id)
        )
        workshop = await self.session.scalar(
            select(Workshop).where(Workshop.id == transaction.workshop_id)
        )
        
        return {
            "receipt_number": transaction.receipt_number or f"REC-{transaction.id:06d}",
            "transaction_id": transaction.id,
            "incident_id": transaction.incident_id,
            "client_name": f"{client.first_name} {client.last_name}" if client else "N/A",
            "workshop_name": workshop.workshop_name if workshop else "N/A",
            "amount": float(transaction.amount),
            "commission": float(transaction.commission),
            "workshop_amount": float(transaction.workshop_amount),
            "payment_method": transaction.payment_method,
            "status": transaction.status,
            "paid_at": transaction.completed_at,
            "description": transaction.description,
        }
