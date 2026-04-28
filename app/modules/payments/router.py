"""
Payment Router - Client-facing endpoints for payments.
"""
import json
import stripe

from fastapi import APIRouter, Depends, Query, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db_session
from ...core.config import get_settings
from ...core.logging import get_logger
from ...core.responses import create_success_response
from ...core.permissions import Permission
from ...core.dependencies import require_permission
from ...shared.dependencies.auth import get_current_user, get_current_client
from ...models.user import User
from ...models.client import Client
from ...models.stripe_event_log import StripeEventLog
from .schemas import CreatePaymentIntentRequest
from .service import PaymentService

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "/create-intent",
    summary="Crear PaymentIntent para pagar un servicio",
    description="Crea un Stripe PaymentIntent y devuelve el client_secret para confirmar el pago desde la app móvil.",
    dependencies=[Depends(require_permission(Permission.PAYMENT_PROCESS))],
)
async def create_payment_intent(
    request: CreatePaymentIntentRequest,
    current_user: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a Stripe PaymentIntent for paying an incident service."""
    try:
        service = PaymentService(session)
        result = await service.create_payment_intent(
            client_id=current_user.id,
            incident_id=request.incident_id,
        )
        return create_success_response(
            data=result,
            message="PaymentIntent creado exitosamente",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get(
    "/incident/{incident_id}/status",
    summary="Estado de pago del incidente",
    description="Comprueba si un incidente ya fue pagado y retorna su transaction_id",
    dependencies=[Depends(require_permission(Permission.PAYMENT_PROCESS))],
)
async def check_incident_payment_status(
    incident_id: int,
    current_user: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_db_session),
):
    """Check if an incident has a completed payment."""
    service = PaymentService(session)
    result = await service.get_incident_payment_status(
        incident_id=incident_id,
        client_id=current_user.id,
    )
    return create_success_response(data=result)


@router.post(
    "/stripe/webhook",
    summary="Webhook de Stripe",
    description="Endpoint para recibir webhooks de Stripe. No requiere autenticación JWT, pero valida la firma de Stripe.",
    include_in_schema=False,
)
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    # Verify webhook signature
    webhook_secret = settings.stripe_webhook_secret
    
    if webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except ValueError:
            logger.error("Invalid Stripe webhook payload")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError:
            logger.error("Invalid Stripe webhook signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # In development without webhook secret, parse directly
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    event_id = event.get("id", "unknown")
    event_type = event.get("type", "unknown")
    
    # Check for duplicate events (idempotency)
    from sqlalchemy import select
    existing = await session.scalar(
        select(StripeEventLog).where(
            StripeEventLog.stripe_event_id == event_id
        )
    )
    
    if existing and existing.status == "processed":
        logger.info(f"Duplicate Stripe event ignored: {event_id}")
        return {"status": "already_processed"}
    
    # Log the event
    event_log = StripeEventLog(
        stripe_event_id=event_id,
        event_type=event_type,
        payload=json.dumps(event) if isinstance(event, dict) else str(event),
        status="received",
    )
    if not existing:
        session.add(event_log)
        await session.flush()
    else:
        event_log = existing
    
    # Process the event
    try:
        service = PaymentService(session)
        
        if event_type == "payment_intent.succeeded":
            payment_intent_id = event["data"]["object"]["id"]
            transaction = await service.handle_payment_succeeded(payment_intent_id)
            
            if transaction:
                logger.info(f"Payment succeeded: {payment_intent_id}")
        
        elif event_type == "payment_intent.payment_failed":
            payment_intent_id = event["data"]["object"]["id"]
            failure_message = event["data"]["object"].get("last_payment_error", {}).get("message", "Unknown error")
            transaction = await service.handle_payment_failed(payment_intent_id, failure_message)
            
            if transaction:
                logger.info(f"Payment failed: {payment_intent_id}")
        
        else:
            logger.info(f"Unhandled Stripe event type: {event_type}")
        
        event_log.status = "processed"
        event_log.processed_at = __import__("datetime").datetime.utcnow()
        
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {e}", exc_info=True)
        event_log.status = "failed"
        event_log.error_message = str(e)
    
    await session.commit()
    return {"status": "ok"}


@router.get(
    "/my-history",
    summary="Historial de pagos del cliente",
    description="Obtener el historial de pagos del cliente autenticado.",
    dependencies=[Depends(require_permission(Permission.PAYMENT_VIEW_OWN))],
)
async def get_my_payment_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_db_session),
):
    """Get payment history for the authenticated client."""
    service = PaymentService(session)
    result = await service.get_client_payments(
        client_id=current_user.id,
        page=page,
        size=size,
    )
    return create_success_response(data=result)


@router.get(
    "/{transaction_id}/receipt",
    summary="Comprobante de pago",
    description="Obtener el comprobante de un pago específico.",
    dependencies=[Depends(require_permission(Permission.PAYMENT_VIEW_RECEIPT))],
)
async def get_payment_receipt(
    transaction_id: int,
    current_user: Client = Depends(get_current_client),
    session: AsyncSession = Depends(get_db_session),
):
    """Get payment receipt for a specific transaction."""
    try:
        service = PaymentService(session)
        result = await service.get_payment_receipt(
            transaction_id=transaction_id,
            client_id=current_user.id,
        )
        return create_success_response(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
