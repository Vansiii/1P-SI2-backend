from pydantic import BaseModel, Field


class CompatibleWorkshopResponse(BaseModel):
    workshop_id: int
    workshop_name: str
    description: str | None = None
    address: str | None = None
    latitude: float
    longitude: float
    distance_km: float
    coverage_radius_km: float | None = None
    estimated_time_minutes: int | None = None
    rating: float | None = None
    rating_count: int = 0
    is_available: bool
    is_open_now: bool = True
    matching_services: list[dict] = Field(default_factory=list)
    available_technicians: int = 0
    score: float = 0.0


class SelectWorkshopRequest(BaseModel):
    workshop_id: int


class SelectWorkshopResponse(BaseModel):
    success: bool
    incident_id: int
    workshop_id: int | None = None
    workshop_name: str | None = None
    estimated_time_minutes: int | None = None
    message: str


class WorkshopPublicProfile(BaseModel):
    workshop_id: int
    workshop_name: str
    description: str | None = None
    address: str | None = None
    latitude: float
    longitude: float
    coverage_radius_km: float | None = None
    rating: float | None = None
    rating_count: int = 0
    active_services: list[dict] = Field(default_factory=list)
    schedules: list[dict] = Field(default_factory=list)
