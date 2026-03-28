from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sodapy import Socrata

from config.settings import get_settings

logger = structlog.get_logger(__name__)

SOCRATA_DOMAIN = "data.cityofnewyork.us"
DATASET_ID = "erm2-nwe9"

FLOOD_COMPLAINT_TYPES = [
    "Catch Basin Clogged/Flooding",
    "Sewer Backup/Flooding",
    "Flooding",
]


async def lookup_flood_history(
    lat: float,
    lng: float,
    radius_meters: float = 500,
) -> dict:
    """Look up flood and drainage 311 complaint history near a location.

    Queries the NYC Open Data 311 Service Requests dataset for flood-related
    complaints within the last 90 days near the given coordinates.

    Args:
        lat: Latitude of the location.
        lng: Longitude of the location.
        radius_meters: Search radius in meters (default 500m).

    Returns:
        Dict with count, recent_incidents (max 5), and last_reported date.
    """
    settings = get_settings()

    # Build bounding box from radius (approximate)
    # 1 degree lat ~ 111,000m; 1 degree lng ~ 111,000m * cos(lat)
    lat_delta = radius_meters / 111_000.0
    lng_delta = radius_meters / (111_000.0 * math.cos(math.radians(lat)))

    min_lat = lat - lat_delta
    max_lat = lat + lat_delta
    min_lng = lng - lng_delta
    max_lng = lng + lng_delta

    ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S")

    complaint_filter = ", ".join(f"'{ct}'" for ct in FLOOD_COMPLAINT_TYPES)
    where_clause = (
        f"complaint_type in ({complaint_filter}) "
        f"AND created_date >= '{ninety_days_ago}' "
        f"AND latitude >= '{min_lat}' AND latitude <= '{max_lat}' "
        f"AND longitude >= '{min_lng}' AND longitude <= '{max_lng}'"
    )

    app_token = settings.nyc_open_data_app_token or None

    try:
        client = Socrata(SOCRATA_DOMAIN, app_token, timeout=15)
        results: list[dict[str, Any]] = client.get(
            DATASET_ID,
            where=where_clause,
            order="created_date DESC",
            limit=100,
        )
        client.close()

        count = len(results)
        recent = results[:5]

        last_reported: str | None = None
        if results:
            last_reported = results[0].get("created_date", "")
            if last_reported:
                # Normalize to date only
                last_reported = last_reported[:10]

        recent_incidents = [
            {
                "date": r.get("created_date", "")[:10],
                "type": r.get("complaint_type", ""),
                "status": r.get("status", ""),
                "address": r.get("incident_address", ""),
                "borough": r.get("borough", ""),
            }
            for r in recent
        ]

        logger.info("lookup_flood_history: found incidents", count=count, lat=lat, lng=lng)

        return {
            "status": "ok",
            "count": count,
            "recent_incidents": recent_incidents,
            "last_reported": last_reported,
            "search_radius_meters": radius_meters,
            "coordinates": {"lat": lat, "lng": lng},
        }

    except Exception as exc:
        logger.error("lookup_flood_history: error querying Open Data", error=str(exc))
        return {
            "status": "error",
            "message": str(exc),
            "count": 0,
            "recent_incidents": [],
            "last_reported": None,
        }
