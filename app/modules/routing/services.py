"""
Service for calculating routes and ETA using OSRM.
"""
from typing import Optional, Dict, List, Tuple
from datetime import datetime
import httpx
from math import radians, sin, cos, sqrt, atan2

from ...core.logging import get_logger
from ...core.config import settings

logger = get_logger(__name__)


class RoutingService:
    """
    Service for route calculation and ETA estimation using OSRM.
    """

    # Traffic adjustment factors
    TRAFFIC_BUFFER_FACTOR = 0.25       # +25% buffer urbano por defecto
    RUSH_HOUR_FACTOR = 0.50            # +50% adicional en hora pico
    RUSH_HOUR_MORNING = (7, 9)         # 7-9 AM
    RUSH_HOUR_EVENING = (17, 19)       # 5-7 PM
    MIN_REAL_SPEED_KMH = 5             # Velocidad mínima considerada real
    MAX_REAL_SPEED_KMH = 120           # Velocidad máxima razonable
    FALLBACK_SPEED_KMH = 40.0          # Velocidad promedio urbana para fallback

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=settings.osrm_timeout_seconds)

    def _is_rush_hour(self) -> bool:
        """Check if current time is during rush hour (local server time)."""
        now = datetime.now()
        hour = now.hour
        return (self.RUSH_HOUR_MORNING[0] <= hour < self.RUSH_HOUR_MORNING[1] or
                self.RUSH_HOUR_EVENING[0] <= hour < self.RUSH_HOUR_EVENING[1])

    def _apply_traffic_adjustment(self, duration_minutes: float, using_real_speed: bool = False) -> float:
        """
        Apply traffic adjustment factors to ETA.
        
        - If using technician's real GPS speed: no adjustment (it's already real-time)
        - If using OSRM theoretical speed: add urban buffer + rush hour factor
        """
        if using_real_speed:
            return duration_minutes * 1.05  # Solo +5% margen mínimo
        
        adjusted = duration_minutes * (1.0 + self.TRAFFIC_BUFFER_FACTOR)
        
        if self._is_rush_hour():
            adjusted *= (1.0 + self.RUSH_HOUR_FACTOR)
            logger.info(f"Rush hour adjustment applied: {duration_minutes:.1f} → {adjusted:.1f} min")
        
        return adjusted

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
        
        Attempts HTTPS first, then HTTP as fallback.
        """
        base_url = settings.osrm_base_url
        url_path = f"/route/v1/{profile}/{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true"
        }

        # Intentar con la URL configurada primero
        result = await self._try_osrm_request(base_url, url_path, params)
        if result is not None:
            return result

        # Si la URL configurada es HTTPS y falló, intentar HTTP
        if base_url.startswith("https://"):
            http_url = base_url.replace("https://", "http://", 1)
            logger.info(f"OSRM HTTPS failed, trying HTTP: {http_url}")
            result = await self._try_osrm_request(http_url, url_path, params)
            if result is not None:
                return result

        # Si la URL configurada es HTTP y falló, intentar HTTPS
        if base_url.startswith("http://"):
            https_url = base_url.replace("http://", "https://", 1)
            logger.info(f"OSRM HTTP failed, trying HTTPS: {https_url}")
            result = await self._try_osrm_request(https_url, url_path, params)
            if result is not None:
                return result

        logger.warning("All OSRM attempts failed, using fallback calculation")
        return self._fallback_calculation(origin_lat, origin_lng, dest_lat, dest_lng)

    async def _try_osrm_request(
        self, base_url: str, url_path: str, params: dict
    ) -> Optional[Dict]:
        """Try a single OSRM request. Returns None on failure."""
        try:
            url = f"{base_url}{url_path}"
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != "Ok":
                logger.warning(f"OSRM returned non-OK code from {base_url}: {data.get('code')}")
                return None

            route = data["routes"][0]
            return {
                "distance_km": round(route["distance"] / 1000, 2),
                "duration_minutes": round(route["duration"] / 60, 2),
                "geometry": route["geometry"],
                "steps": self._extract_steps(route.get("legs", [{}])[0].get("steps", [])),
                "source": "osrm"
            }

        except Exception as e:
            logger.warning(f"OSRM request failed for {base_url}: {str(e)}")
            return None

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
        duration_minutes = (distance_km / self.FALLBACK_SPEED_KMH) * 60
        
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
        Calculate estimated time of arrival with traffic adjustment.
        
        ETA logic (in priority order):
        1. Technician's real GPS speed → ETA = distance / speed (+5% margin)
        2. OSRM duration → ETA = OSRM + 25% urban buffer (+50% rush hour)
        3. Fallback → ETA = Haversine / 40 km/h + 25% buffer
        
        Returns:
            dict with distance_km, duration_minutes, eta_text, traffic_factors, source
        """
        route = await self.calculate_route(origin_lat, origin_lng, dest_lat, dest_lng)
        
        distance_km = route["distance_km"]
        traffic_factors = []
        using_real_speed = False
        
        # Priority 1: Use technician's real GPS speed if available and reasonable
        if current_speed and self.MIN_REAL_SPEED_KMH <= current_speed <= self.MAX_REAL_SPEED_KMH:
            raw_minutes = (distance_km / current_speed) * 60
            using_real_speed = True
            traffic_factors.append(f"velocidad_real:{current_speed:.0f}km/h")
        else:
            raw_minutes = route["duration_minutes"]
            traffic_factors.append(f"base_osrm:{raw_minutes:.0f}min" if route["source"] == "osrm" else f"base_haversine:{raw_minutes:.0f}min")
        
        # Apply traffic adjustment
        duration_minutes = self._apply_traffic_adjustment(raw_minutes, using_real_speed)
        
        if not using_real_speed:
            traffic_factors.append(f"buffer_urbano:+{int(self.TRAFFIC_BUFFER_FACTOR*100)}%")
            if self._is_rush_hour():
                traffic_factors.append(f"hora_pico:+{int(self.RUSH_HOUR_FACTOR*100)}%")
        
        duration_minutes = round(duration_minutes, 1)
        
        # Format ETA text
        if duration_minutes < 1:
            eta_text = "Menos de 1 minuto"
        elif duration_minutes < 60:
            eta_text = f"{int(duration_minutes)} minutos"
        else:
            hours = int(duration_minutes // 60)
            minutes = int(duration_minutes % 60)
            eta_text = f"{hours}h {minutes}min"
        
        return {
            "distance_km": distance_km,
            "duration_minutes": duration_minutes,
            "eta_text": eta_text,
            "current_speed": current_speed,
            "traffic_factors": traffic_factors,
            "is_rush_hour": self._is_rush_hour(),
            "using_real_speed": using_real_speed,
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
