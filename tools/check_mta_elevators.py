from __future__ import annotations

import time
from typing import Any

import httpx
import structlog

from config.settings import get_settings

logger = structlog.get_logger(__name__)

MTA_ELEVATOR_URL = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fnyct_ene.json"

# Simple in-memory cache: {cache_key: (timestamp, data)}
_cache: dict[str, tuple[float, Any]] = {}


def _get_cached(key: str, ttl: int) -> Any | None:
    if key in _cache:
        ts, data = _cache[key]
        if time.monotonic() - ts < ttl:
            return data
    return None


def _set_cached(key: str, data: Any) -> None:
    _cache[key] = (time.monotonic(), data)


async def check_mta_elevators(station_name: str | None = None) -> dict:
    """Query MTA elevator and escalator status.

    Fetches live outage data from the MTA NYCT Elevator/Escalator API.
    Results are cached for elevator_cache_ttl seconds (default 5 minutes).

    Args:
        station_name: Optional station name to filter results. If None, returns all outages.

    Returns:
        Dict with 'status', 'outages' list, and optional 'station_filter'.
    """
    settings = get_settings()

    if not settings.mta_api_key:
        logger.warning("check_mta_elevators: MTA_API_KEY not configured")
        return {
            "status": "unavailable",
            "message": "MTA API key not configured",
        }

    cache_key = f"mta_elevators:{station_name or 'all'}"
    cached = _get_cached(cache_key, settings.elevator_cache_ttl)
    if cached is not None:
        logger.info("check_mta_elevators: returning cached result", station=station_name)
        return cached

    headers = {
        "x-api-key": settings.mta_api_key,
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(MTA_ELEVATOR_URL, headers=headers)
            response.raise_for_status()
            data = response.json()

        # The MTA ENE feed returns a list of equipment records
        all_equipment = data if isinstance(data, list) else data.get("equipment", [])

        # Filter to outages (not in service)
        outages = [
            item for item in all_equipment
            if str(item.get("serving", "")).upper() not in ("IN SERVICE", "ACTIVE")
            or item.get("isActive") is False
            or item.get("outages")
        ]

        # Filter by station name if provided
        if station_name:
            station_lower = station_name.lower()
            outages = [
                o for o in outages
                if station_lower in str(o.get("station", "")).lower()
                or station_lower in str(o.get("trainno", "")).lower()
                or station_lower in str(o.get("linesServed", "")).lower()
            ]

        result = {
            "status": "ok",
            "total_outages": len(outages),
            "outages": outages[:20],  # Cap at 20 for response size
            "station_filter": station_name,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        _set_cached(cache_key, result)
        logger.info("check_mta_elevators: fetched data", total_outages=len(outages), station=station_name)
        return result

    except httpx.HTTPStatusError as exc:
        logger.error("check_mta_elevators: HTTP error", status_code=exc.response.status_code)
        return {
            "status": "error",
            "message": f"MTA API returned HTTP {exc.response.status_code}",
        }
    except httpx.RequestError as exc:
        logger.error("check_mta_elevators: request error", error=str(exc))
        return {
            "status": "error",
            "message": f"Failed to reach MTA API: {exc}",
        }
    except Exception as exc:
        logger.error("check_mta_elevators: unexpected error", error=str(exc))
        return {
            "status": "error",
            "message": f"Unexpected error: {exc}",
        }
