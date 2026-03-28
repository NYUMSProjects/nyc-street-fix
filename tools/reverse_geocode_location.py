from __future__ import annotations

import httpx
import structlog

from config.settings import get_settings

logger = structlog.get_logger(__name__)

REVERSE_GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"


async def reverse_geocode_location(lat: float, lon: float) -> str | None:
    """Reverse geocode lat/lon to a human-readable address.

    Returns the formatted address string, or None on failure.
    """
    settings = get_settings()
    if not settings.google_maps_api_key:
        logger.warning("reverse_geocode_location: GOOGLE_MAPS_API_KEY not set")
        return None

    params = {
        "latlng": f"{lat},{lon}",
        "key": settings.google_maps_api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(REVERSE_GEOCODING_URL, params=params)
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            logger.warning("reverse_geocode_location: no results", status=data.get("status"))
            return None

        address = data["results"][0]["formatted_address"]
        logger.info("reverse_geocode_location: success", address=address)
        return address

    except Exception as exc:
        logger.error("reverse_geocode_location: error", error=str(exc))
        return None
