"""
Service for calculating routes and ETA using OSRM.
"""
from typing import Optional, Dict, List, Tuple
import httpx
from math import radians, sin, cos, sqrt, atan2

from ...core.logging import get_logger
from ...core.config import settings

logger = get_logger(__name__)


class RoutingService:
    """
    Service for route calculation and ETA estimation using OSRM.
    """

    # OSRM public API endpoint
    OSRM_BASE_URL = "http://router.project-osrm.org"
    
    # Average speeds by road type (km/h)
    AVERAGE_SPEEDS = {
        "motorway": 100,
        "trunk": 80,
        "primary": 60,
        "secondary": 50,
        "tertiary": 40,
        "residential": 30,
        "default": 40
    }

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)

    async def calculate_route(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        profile: str = "driving"
    ) -> Dict:
        """
        Calculate route between two points using OSRM.
        
        Args:
            origin_lat: Origin latitude
            origin_lng: Origin longitude
            dest_lat: Destination latitude
            dest_lng: Destination longitude
            profile: Routing profile (driving, walking, cycling)
            
        Returns:
            Dictionary with route information
        """
        try:
            # Build OSRM request URL
            url = f"{self.OSRM_BASE_URL}/route/v1/{profile}/{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
            params = {
                "overview": "full",
                "geometries": "geojson",
                "steps": "true"
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()

            if data.get("code") != "Ok":
                logger.warning(f"OSRM returned non-OK code: {data.get('code')}")
                return self._fallback_calculation(origin_lat, origin_lng, dest_lat, dest_lng)

            route = data["routes"][0]
            
            return {
                "distance_km": round(route["distance"] / 1000, 2),
                "duration_minutes": round(route["duration"] / 60, 2),
                "geometry": route["geometry"],
                "steps": self._extract_steps(route.get("legs", [{}])[0].get("steps", [])),
                "source": "osrm"
            }

        except Exception as e:
            logger.error(f"Error calculating route with OSRM: {str(e)}")
            return self._fallback_calculation(origin_lat, origin_lng, dest_lat, dest_lng)

    def _extract_steps(self, steps: List[Dict]) -> List[Dict]:
        """
        Extract simplified step information from OSRM response.
        
        Args:
            steps: OSRM steps data
            
        Returns:
            List of simplified steps
        """
        simplified_steps = []
        
        for step in steps:
            simplified_steps.append({
                "distance_m": step.get("distance", 0),
                "duration_s": step.get("duration", 0),
                "instruction": step.get("maneuver", {}).get("instruction", ""),
                "name": step.get("name", "")
            })
        
        return simplified_steps

    def _fallback_calculation(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float
    ) -> Dict:
        """
        Fallback calculation using Haversine distance.
        
        Args:
            origin_lat: Origin latitude
            origin_lng: Origin longitude
            dest_lat: Destination latitude
            dest_lng: Destination longitude
            
        Returns:
            Dictionary with estimated route information
        """
        distance_km = self._haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)
        
        # Estimate duration assuming average city speed (40 km/h)
        duration_minutes = (distance_km / self.AVERAGE_SPEEDS["default"]) * 60
        
        return {
            "distance_km": round(distance_km, 2),
            "duration_minutes": round(duration_minutes, 2),
            "geometry": None,
            "steps": [],
            "source": "haversine"
        }

    @staticmethod
    def _haversine_distance(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calculate distance between two GPS coordinates using Haversine formula.
        
        Args:
            lat1: Latitude of first point
            lon1: Longitude of first point
            lat2: Latitude of second point
            lon2: Longitude of second point
            
        Returns:
            Distance in kilometers
        """
        R = 6371.0  # Earth radius in km

        lat1_rad = radians(lat1)
        lon1_rad = radians(lon1)
        lat2_rad = radians(lat2)
        lon2_rad = radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c

    async def calculate_eta(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        current_speed: Optional[float] = None
    ) -> Dict:
        """
        Calculate estimated time of arrival.
        
        Args:
            origin_lat: Current latitude
            origin_lng: Current longitude
            dest_lat: Destination latitude
            dest_lng: Destination longitude
            current_speed: Current speed in km/h (optional)
            
        Returns:
            Dictionary with ETA information
        """
        route = await self.calculate_route(origin_lat, origin_lng, dest_lat, dest_lng)
        
        distance_km = route["distance_km"]
        
        # If current speed is provided and reasonable, use it for ETA
        if current_speed and 5 <= current_speed <= 120:
            duration_minutes = (distance_km / current_speed) * 60
        else:
            duration_minutes = route["duration_minutes"]
        
        # Format ETA
        if duration_minutes < 1:
            eta_text = "Menos de 1 minuto"
        elif duration_minutes < 60:
            eta_text = f"{int(duration_minutes)} minutos"
        else:
            hours = int(duration_minutes // 60)
            minutes = int(duration_minutes % 60)
            eta_text = f"{hours} hora{'s' if hours > 1 else ''} {minutes} minutos"
        
        return {
            "distance_km": distance_km,
            "duration_minutes": round(duration_minutes, 2),
            "eta_text": eta_text,
            "current_speed": current_speed,
            "source": route["source"]
        }

    async def calculate_multiple_routes(
        self,
        origin: Tuple[float, float],
        destinations: List[Tuple[float, float]]
    ) -> List[Dict]:
        """
        Calculate routes from one origin to multiple destinations.
        
        Args:
            origin: Tuple of (latitude, longitude)
            destinations: List of (latitude, longitude) tuples
            
        Returns:
            List of route information dictionaries
        """
        routes = []
        
        for dest in destinations:
            route = await self.calculate_route(
                origin[0], origin[1],
                dest[0], dest[1]
            )
            routes.append(route)
        
        return routes

    async def find_nearest_destination(
        self,
        origin: Tuple[float, float],
        destinations: List[Tuple[float, float]]
    ) -> Tuple[int, Dict]:
        """
        Find the nearest destination from origin.
        
        Args:
            origin: Tuple of (latitude, longitude)
            destinations: List of (latitude, longitude) tuples
            
        Returns:
            Tuple of (index, route_info) for nearest destination
        """
        routes = await self.calculate_multiple_routes(origin, destinations)
        
        # Find route with minimum distance
        min_index = 0
        min_distance = float('inf')
        
        for i, route in enumerate(routes):
            if route["distance_km"] < min_distance:
                min_distance = route["distance_km"]
                min_index = i
        
        return min_index, routes[min_index]

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
