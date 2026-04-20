"""
Schemas for routing and geocoding operations.
"""
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    """Schema for route calculation request."""
    origin_lat: float = Field(..., ge=-90, le=90)
    origin_lng: float = Field(..., ge=-180, le=180)
    dest_lat: float = Field(..., ge=-90, le=90)
    dest_lng: float = Field(..., ge=-180, le=180)
    profile: str = Field("driving", description="Routing profile: driving, walking, cycling")


class ETARequest(BaseModel):
    """Schema for ETA calculation request."""
    origin_lat: float = Field(..., ge=-90, le=90)
    origin_lng: float = Field(..., ge=-180, le=180)
    dest_lat: float = Field(..., ge=-90, le=90)
    dest_lng: float = Field(..., ge=-180, le=180)
    current_speed: Optional[float] = Field(None, ge=0, le=200, description="Current speed in km/h")


class RouteResponse(BaseModel):
    """Schema for route response."""
    distance_km: float
    duration_minutes: float
    geometry: Optional[Dict]
    steps: List[Dict]
    source: str


class ETAResponse(BaseModel):
    """Schema for ETA response."""
    distance_km: float
    duration_minutes: float
    eta_text: str
    current_speed: Optional[float]
    source: str


class ReverseGeocodeRequest(BaseModel):
    """Schema for reverse geocoding request."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    language: str = Field("es", description="Language code")


class GeocodeRequest(BaseModel):
    """Schema for forward geocoding request."""
    address: str = Field(..., min_length=3, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    country: str = Field("Bolivia", max_length=100)
    language: str = Field("es", description="Language code")


class AddressResponse(BaseModel):
    """Schema for address response."""
    display_name: str
    address: Dict[str, str]
    formatted_address: str
    latitude: float
    longitude: float
    source: str


class NearbySearchRequest(BaseModel):
    """Schema for nearby search request."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    query: str = Field(..., min_length=2, max_length=100)
    radius_km: float = Field(5.0, ge=0.1, le=50)
    limit: int = Field(10, ge=1, le=50)
