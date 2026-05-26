"""
Weather tool for the NEXUS Tool Agent.

Uses open-meteo.com free API (no API key required).
Two-step: geocode city → fetch current weather conditions.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from config import settings

logger = structlog.get_logger(__name__)

_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = f"{settings.weather_api_base_url}/forecast"


class WeatherTool:
    """
    Fetches current weather conditions for a given city using open-meteo.com.

    No API key required. Geocodes the city name first, then fetches
    temperature, weather code, and wind speed.
    """

    async def run(self, city: str) -> dict[str, Any]:
        """
        Return current weather for the given city.

        Args:
            city: City name (e.g. "London", "Paris", "Tokyo").

        Returns:
            Dict with temperature_celsius, weather_description, wind_speed_kmh,
            city, latitude, longitude. On error, returns dict with 'error' key.
        """
        logger.debug("weather.run", city=city)

        try:
            lat, lon, resolved_name = await self._geocode(city)
        except Exception as exc:
            logger.warning("weather.geocode_failed", city=city, error=str(exc))
            return {"error": f"Could not geocode city '{city}': {exc}"}

        try:
            weather = await self._fetch_weather(lat, lon)
        except Exception as exc:
            logger.warning("weather.fetch_failed", city=city, error=str(exc))
            return {"error": f"Could not fetch weather for '{city}': {exc}"}

        return {
            "city": resolved_name,
            "latitude": lat,
            "longitude": lon,
            "temperature_celsius": weather["temperature"],
            "wind_speed_kmh": weather["wind_speed"],
            "weather_code": weather["weather_code"],
        }

    async def _geocode(self, city: str) -> tuple[float, float, str]:
        """
        Geocode a city name to latitude/longitude using open-meteo geocoding API.

        Args:
            city: City name string.

        Returns:
            Tuple of (latitude, longitude, resolved_city_name).

        Raises:
            ValueError: If no results found for the city.
            httpx.RequestError: If the geocoding API is unreachable.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                _GEOCODING_URL,
                params={"name": city, "count": 1, "language": "en", "format": "json"},
            )
            response.raise_for_status()
            data = response.json()

        results = data.get("results", [])
        if not results:
            raise ValueError(f"No location found for '{city}'")

        first = results[0]
        return float(first["latitude"]), float(first["longitude"]), first["name"]

    async def _fetch_weather(self, lat: float, lon: float) -> dict[str, Any]:
        """
        Fetch current weather for a lat/lon coordinate from open-meteo.com.

        Args:
            lat: Latitude.
            lon: Longitude.

        Returns:
            Dict with temperature, wind_speed, weather_code.

        Raises:
            httpx.RequestError: If the weather API is unreachable.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                _FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,wind_speed_10m,weather_code",
                    "temperature_unit": "celsius",
                },
            )
            response.raise_for_status()
            data = response.json()

        current = data["current"]
        return {
            "temperature": current["temperature_2m"],
            "wind_speed": current["wind_speed_10m"],
            "weather_code": current["weather_code"],
        }
