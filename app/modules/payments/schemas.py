"""
Pydantic schemas for the Payments module.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field


# ============================================================================
# Payment Schemas
# ============================================================================

class CreatePaymentIntentRequest(BaseModel):
    """Request to create a Stripe PaymentIntent for an incident."""
    incident_id: int = Field(..., description="ID del incidente a pagar")


class CreatePaymentIntentResponse(BaseModel):
    """Response with Stripe client_secret for confirming payment on mobile."""
    transaction_id: int
    client_secret: str
    stripe_payment_intent_id: str
    amount: float
    commission: float
    workshop_amount: float
    publishable_key: str


class PaymentResponse(BaseModel):
    """Response for a single payment/transaction."""
    id: int
    incident_id: int
    workshop_id: int
    client_id: int
    amount: float
    commission: float
    workshop_amount: float
    status: str
    payment_method: str
    receipt_number: Optional[str] = None
    description: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class PaymentHistoryResponse(BaseModel):
    """Paginated payment history."""
    payments: List[PaymentResponse]
    total: int
    page: int
    size: int


class PaymentReceiptResponse(BaseModel):
    """Payment receipt/comprobante."""
    receipt_number: str
    transaction_id: int
    incident_id: int
    client_name: str
    workshop_name: str
    amount: float
    commission: float
    workshop_amount: float
    payment_method: str
    status: str
    paid_at: Optional[datetime] = None
    description: Optional[str] = None


# ============================================================================
# Wallet Schemas
# ============================================================================

class WalletResponse(BaseModel):
    """Workshop wallet/balance information."""
    workshop_id: int
    available_balance: float
    pending_balance: float
    total_earned: float
    total_withdrawn: float
    updated_at: Optional[datetime] = None


class FinancialMovementResponse(BaseModel):
    """Single financial movement entry."""
    id: int
    movement_type: str
    amount: float
    balance_after: float
    description: Optional[str] = None
    transaction_id: Optional[int] = None
    withdrawal_id: Optional[int] = None
    created_at: Optional[datetime] = None


class FinancialHistoryResponse(BaseModel):
    """Paginated financial history."""
    movements: List[FinancialMovementResponse]
    total: int
    page: int
    size: int


# ============================================================================
# Withdrawal Schemas
# ============================================================================

class CreateWithdrawalRequest(BaseModel):
    """Request to create a withdrawal."""
    amount: float = Field(..., gt=0, description="Monto a retirar")
    bank_name: Optional[str] = Field(None, max_length=100)
    account_number: Optional[str] = Field(None, max_length=50)
    account_holder: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)


class WithdrawalResponse(BaseModel):
    """Response for a single withdrawal."""
    id: int
    workshop_id: int
    amount: float
    status: str
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    account_holder: Optional[str] = None
    notes: Optional[str] = None
    admin_notes: Optional[str] = None
    processed_by: Optional[int] = None
    failure_reason: Optional[str] = None
    requested_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class WithdrawalListResponse(BaseModel):
    """Paginated list of withdrawals."""
    withdrawals: List[WithdrawalResponse]
    total: int
    page: int
    size: int


class AdminWithdrawalActionRequest(BaseModel):
    """Admin request to approve/reject a withdrawal."""
    admin_notes: Optional[str] = Field(None, max_length=500)


# ============================================================================
# Settlement Schemas
# ============================================================================

class GenerateSettlementRequest(BaseModel):
    """Request to generate a settlement for a workshop."""
    period_start: datetime
    period_end: datetime
    notes: Optional[str] = Field(None, max_length=500)


class SettlementResponse(BaseModel):
    """Response for a single settlement."""
    id: int
    workshop_id: int
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    total_collected: float
    total_commission: float
    total_net: float
    total_withdrawn: float
    balance_at_close: float
    transactions_count: int
    status: str
    generated_by: Optional[int] = None
    notes: Optional[str] = None
    generated_at: Optional[datetime] = None


class SettlementListResponse(BaseModel):
    """Paginated list of settlements."""
    settlements: List[SettlementResponse]
    total: int
    page: int
    size: int
