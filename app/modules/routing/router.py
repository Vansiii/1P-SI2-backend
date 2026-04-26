"""
Routing and geocoding endpoints.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.dependencies import get_current_user
from ...core.responses import success_response
from .services import RoutingService
from .geocoding_service import GeocodingService
from .schemas import (
    RouteRequest,
    ETARequest,
    RouteResponse,
    ETAResponse,
    ReverseGeocodeRequest,
    GeocodeRequest,
    AddressResponse,
    NearbySearchRequest
)
from ...models.user import User

router = APIRouter(prefix="/routing", tags=["routing"])


@router.post("/calculate-route", response_model=RouteResponse)
async def calculate_route(
    request: RouteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate route between two points.
    
    Uses OSRM (Open Source Routing Machine) for route calculation.
    Falls back to Haversine distance if OSRM is unavailable.
    
    **Permissions:** Authenticated user
    """
    routing_service = RoutingService()
    
    try:
        route = await routing_service.calculate_route(
            origin_lat=request.origin_lat,
            origin_lng=request.origin_lng,
            dest_lat=request.dest_lat,
            dest_lng=request.dest_lng,
            profile=request.profile
        )
        
        return route
    
    finally:
        await routing_service.close()


@router.post("/calculate-eta", response_model=ETAResponse)
async def calculate_eta(
    request: ETARequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Calculate estimated time of arrival (ETA).
    
    Optionally uses current speed for more accurate estimation.
    
    **Permissions:** Authenticated user
    """
    routing_service = RoutingService()
    
    try:
        eta = await routing_service.calculate_eta(
            origin_lat=request.origin_lat,
            origin_lng=request.origin_lng,
            dest_lat=request.dest_lat,
            dest_lng=request.dest_lng,
            current_speed=request.current_speed
        )
        
        return eta
    
    finally:
        await routing_service.close()


@router.post("/reverse-geocode", response_model=AddressResponse)
async def reverse_geocode(
    request: ReverseGeocodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Convert coordinates to address (reverse geocoding).
    
    Uses Nominatim (OpenStreetMap) for geocoding.
    
    **Permissions:** Authenticated user
    """
    geocoding_service = GeocodingService()
    
    try:
        address = await geocoding_service.reverse_geocode(
            latitude=request.latitude,
            longitude=request.longitude,
            language=request.language
        )
        
        return address
    
    finally:
        await geocoding_service.close()


@router.post("/geocode", status_code=status.HTTP_200_OK)
async def geocode_address(
    request: GeocodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Convert address to coordinates (forward geocoding).
    
    Uses Nominatim (OpenStreetMap) for geocoding.
    
    **Permissions:** Authenticated user
    """
    geocoding_service = GeocodingService()
    
    try:
        result = await geocoding_service.geocode(
            address=request.address,
            city=request.city,
            country=request.country,
            language=request.language
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Address not found"
            )
        
        return success_response(
            data=result,
            message="Address geocoded successfully"
        )
    
    finally:
        await geocoding_service.close()


@router.post("/search-nearby", status_code=status.HTTP_200_OK)
async def search_nearby_places(
    request: NearbySearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Search for places near a location.
    
    **Permissions:** Authenticated user
    """
    geocoding_service = GeocodingService()
    
    try:
        results = await geocoding_service.search_nearby(
            latitude=request.latitude,
            longitude=request.longitude,
            query=request.query,
            radius_km=request.radius_km,
            limit=request.limit
        )
        
        return success_response(
            data={
                "count": len(results),
                "results": results
            },
            message=f"Found {len(results)} places"
        )
    
    finally:
        await geocoding_service.close()
