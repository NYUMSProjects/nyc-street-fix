from __future__ import annotations

from typing import Optional

import httpx
import structlog

from config.settings import get_settings
from schemas.incident import Coordinates

logger = structlog.get_logger(__name__)

GEOCODING_API_URL = "https://maps.googleapis.com/maps/api/geocode/json"


async def geocode_location(location_text: str) -> Optional[Coordinates]:
    """Geocode a text location to lat/lng coordinates using Google Maps API.

    Args:
        location_text: Address, intersection, or place description.

    Returns:
        Coordinates with lat/lng, or None if geocoding fails.
    """
    if not location_text or not location_text.strip():
        logger.warning("geocode_location: empty location_text")
        return None

    settings = get_settings()

    if not settings.google_maps_api_key:
        logger.warning("geocode_location: GOOGLE_MAPS_API_KEY not set")
        return None

    # Append NYC context if not already present
    query = location_text.strip()
    if "new york" not in query.lower() and "nyc" not in query.lower():
        query = f"{query}, New York City, NY"

    params = {
        "address": query,
        "key": settings.google_maps_api_key,
        "region": "us",
        "components": "country:US|administrative_area:NY",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(GEOCODING_API_URL, params=params)
            response.raise_for_status()
            data = response.json()

        status = data.get("status")
        if status != "OK":
            logger.warning("geocode_location: API returned non-OK status", status=status, query=query)
            return None

        results = data.get("results", [])
        if not results:
            logger.warning("geocode_location: no results returned", query=query)
            return None

        location = results[0]["geometry"]["location"]
        coords = Coordinates(lat=location["lat"], lng=location["lng"])
        logger.info("geocode_location: success", query=query, lat=coords.lat, lng=coords.lng)
        return coords

    except httpx.HTTPStatusError as exc:
        logger.error("geocode_location: HTTP error", status_code=exc.response.status_code, error=str(exc))
        return None
    except httpx.RequestError as exc:
        logger.error("geocode_location: request error", error=str(exc))
        return None
    except (KeyError, IndexError, ValueError) as exc:
        logger.error("geocode_location: failed to parse response", error=str(exc))
        return None
    except Exception as exc:
        logger.error("geocode_location: unexpected error", error=str(exc))
        return None
