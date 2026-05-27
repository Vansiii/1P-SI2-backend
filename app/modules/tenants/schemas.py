from datetime import datetime

from pydantic import BaseModel, Field


class WorkshopTenantRegistrationRequest(BaseModel):
    workshop_name: str = Field(..., max_length=255)
    legal_name: str = Field(..., max_length=255)
    nit: str = Field(..., max_length=20)
    business_type: str | None = Field(None, max_length=50)
    first_name: str = Field(..., max_length=60)
    last_name: str = Field(..., max_length=60)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    phone: str = Field(..., max_length=20)
    address: str | None = Field(None, max_length=255)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    coverage_radius_km: float = Field(default=10.0, ge=1.0, le=100.0)
    coverage_zone: str | None = Field(None, max_length=255)
    description: str | None = Field(None, max_length=500)
    contact_name: str | None = Field(None, max_length=120)
    contact_phone: str | None = Field(None, max_length=30)
    plan_id: int | None = None


class TenantPublic(BaseModel):
    id: int
    workshop_id: int
    legal_name: str
    nit: str
    slug: str | None
    business_type: str | None
    status: str
    rejection_reason: str | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PendingTenantPublic(BaseModel):
    tenant_id: int
    legal_name: str
    nit: str
    business_type: str | None
    workshop_name: str
    owner_name: str
    owner_email: str
    address: str | None
    plan_name: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ApproveTenantRequest(BaseModel):
    plan_id: int | None = None


class RejectTenantRequest(BaseModel):
    rejection_reason: str = Field(..., min_length=1, max_length=500)


class PlanPublic(BaseModel):
    id: int
    code: str
    name: str
    description: str | None
    price: float
    billing_period: str
    max_technicians: int
    max_services: int
    enable_kpis: bool
    enable_reports: bool
    enable_realtime_tracking: bool
    enable_quotes: bool
    enable_voice_reports: bool
    enable_priority_support: bool

    model_config = {"from_attributes": True}
