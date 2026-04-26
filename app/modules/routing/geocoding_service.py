"""
Service for geocoding and reverse geocoding using Nominatim.
"""
from typing import Optional, Dict, List
import httpx
from urllib.parse import quote

from ...core.logging import get_logger

logger = get_logger(__name__)


class GeocodingService:
    """
    Service for geocoding operations using Nominatim (OpenStreetMap).
    """

    # Nominatim API endpoint
    NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
    
    # User agent for API requests (required by Nominatim)
    USER_AGENT = "MecanicoYa/1.0"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": self.USER_AGENT}
        )

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
        language: str = "es"
    ) -> Dict:
        """
        Convert coordinates to address (reverse geocoding).
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            language: Language for results (default: Spanish)
            
        Returns:
            Dictionary with address information
        """
        try:
            url = f"{self.NOMINATIM_BASE_URL}/reverse"
            params = {
                "lat": latitude,
                "lon": longitude,
                "format": "json",
                "addressdetails": 1,
                "accept-language": language
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()

            if "error" in data:
                logger.warning(f"Nominatim error: {data['error']}")
                return self._fallback_address(latitude, longitude)

            address = data.get("address", {})
            
            return {
                "display_name": data.get("display_name", ""),
                "address": {
                    "road": address.get("road", ""),
                    "house_number": address.get("house_number", ""),
                    "neighbourhood": address.get("neighbourhood", ""),
                    "suburb": address.get("suburb", ""),
                    "city": address.get("city") or address.get("town") or address.get("village", ""),
                    "state": address.get("state", ""),
                    "postcode": address.get("postcode", ""),
                    "country": address.get("country", "")
                },
                "formatted_address": self._format_address(address),
                "latitude": latitude,
                "longitude": longitude,
                "source": "nominatim"
            }

        except Exception as e:
            logger.error(f"Error in reverse geocoding: {str(e)}")
            return self._fallback_address(latitude, longitude)

    async def geocode(
        self,
        address: str,
        city: Optional[str] = None,
        country: str = "Bolivia",
        language: str = "es"
    ) -> Optional[Dict]:
        """
        Convert address to coordinates (forward geocoding).
        
        Args:
            address: Address to geocode
            city: Optional city name
            country: Country name (default: Bolivia)
            language: Language for results
            
        Returns:
            Dictionary with coordinates or None if not found
        """
        try:
            # Build search query
            query_parts = [address]
            if city:
                query_parts.append(city)
            query_parts.append(country)
            
            query = ", ".join(query_parts)

            url = f"{self.NOMINATIM_BASE_URL}/search"
            params = {
                "q": query,
                "format": "json",
                "addressdetails": 1,
                "limit": 1,
                "accept-language": language
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()

            if not data:
                logger.warning(f"No results found for address: {query}")
                return None

            result = data[0]
            address_data = result.get("address", {})
            
            return {
                "display_name": result.get("display_name", ""),
                "latitude": float(result.get("lat", 0)),
                "longitude": float(result.get("lon", 0)),
                "address": {
                    "road": address_data.get("road", ""),
                    "house_number": address_data.get("house_number", ""),
                    "neighbourhood": address_data.get("neighbourhood", ""),
                    "suburb": address_data.get("suburb", ""),
                    "city": address_data.get("city") or address_data.get("town") or address_data.get("village", ""),
                    "state": address_data.get("state", ""),
                    "postcode": address_data.get("postcode", ""),
                    "country": address_data.get("country", "")
                },
                "formatted_address": self._format_address(address_data),
                "source": "nominatim"
            }

        except Exception as e:
            logger.error(f"Error in geocoding: {str(e)}")
            return None

    async def search_nearby(
        self,
        latitude: float,
        longitude: float,
        query: str,
        radius_km: float = 5.0,
        limit: int = 10
    ) -> List[Dict]:
        """
        Search for places near a location.
        
        Args:
            latitude: Center latitude
            longitude: Center longitude
            query: Search query (e.g., "taller mecánico", "gasolinera")
            radius_km: Search radius in kilometers
            limit: Maximum number of results
            
        Returns:
            List of nearby places
        """
        try:
            url = f"{self.NOMINATIM_BASE_URL}/search"
            params = {
                "q": query,
                "format": "json",
                "addressdetails": 1,
                "limit": limit,
                "bounded": 1,
                "viewbox": self._calculate_viewbox(latitude, longitude, radius_km)
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()

            results = []
            for item in data:
                address_data = item.get("address", {})
                results.append({
                    "display_name": item.get("display_name", ""),
                    "latitude": float(item.get("lat", 0)),
                    "longitude": float(item.get("lon", 0)),
                    "address": self._format_address(address_data),
                    "type": item.get("type", ""),
                    "category": item.get("category", "")
                })

            return results

        except Exception as e:
            logger.error(f"Error searching nearby: {str(e)}")
            return []

    def _format_address(self, address: Dict) -> str:
        """
        Format address components into a readable string.
        
        Args:
            address: Address components dictionary
            
        Returns:
            Formatted address string
        """
        parts = []
        
        # Street address
        if address.get("road"):
            street = address["road"]
            if address.get("house_number"):
                street = f"{street} {address['house_number']}"
            parts.append(street)
        
        # Neighbourhood or suburb
        if address.get("neighbourhood"):
            parts.append(address["neighbourhood"])
        elif address.get("suburb"):
            parts.append(address["suburb"])
        
        # City
        city = address.get("city") or address.get("town") or address.get("village")
        if city:
            parts.append(city)
        
        # State
        if address.get("state"):
            parts.append(address["state"])
        
        return ", ".join(parts) if parts else "Dirección no disponible"

    def _fallback_address(self, latitude: float, longitude: float) -> Dict:
        """
        Generate fallback address when geocoding fails.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            Dictionary with basic location info
        """
        return {
            "display_name": f"Ubicación: {latitude:.6f}, {longitude:.6f}",
            "address": {
                "road": "",
                "house_number": "",
                "neighbourhood": "",
                "suburb": "",
                "city": "Santa Cruz",  # Default city
                "state": "Santa Cruz",
                "postcode": "",
                "country": "Bolivia"
            },
            "formatted_address": f"Coordenadas: {latitude:.6f}, {longitude:.6f}",
            "latitude": latitude,
            "longitude": longitude,
            "source": "fallback"
        }

    def _calculate_viewbox(
        self,
        latitude: float,
        longitude: float,
        radius_km: float
    ) -> str:
        """
        Calculate viewbox for bounded search.
        
        Args:
            latitude: Center latitude
            longitude: Center longitude
            radius_km: Radius in kilometers
            
        Returns:
            Viewbox string in format "left,top,right,bottom"
        """
        # Approximate degrees per km (varies by latitude)
        km_per_degree_lat = 111.0
        km_per_degree_lon = 111.0 * abs(cos(radians(latitude)))
        
        from math import radians, cos
        
        delta_lat = radius_km / km_per_degree_lat
        delta_lon = radius_km / km_per_degree_lon
        
        left = longitude - delta_lon
        right = longitude + delta_lon
        top = latitude + delta_lat
        bottom = latitude - delta_lat
        
        return f"{left},{top},{right},{bottom}"

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
