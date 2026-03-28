from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from schemas.incident import Coordinates


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.google_maps_api_key = "test-maps-key"
    return settings


@pytest.fixture
def mock_settings_no_key():
    settings = MagicMock()
    settings.google_maps_api_key = ""
    return settings


def _make_geocoding_response(lat: float, lng: float) -> dict:
    return {
        "status": "OK",
        "results": [
            {
                "geometry": {
                    "location": {"lat": lat, "lng": lng}
                },
                "formatted_address": "Corner of Newark Ave & Grove St, Jersey City, NJ",
            }
        ],
    }


@pytest.mark.asyncio
async def test_geocode_location_success(mock_settings):
    """Test successful geocoding returns Coordinates."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _make_geocoding_response(40.7178, -74.0431)
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("tools.geocode_location.get_settings", return_value=mock_settings), \
         patch("tools.geocode_location.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

        from tools.geocode_location import geocode_location

        result = await geocode_location("Newark Ave and Grove St, Jersey City")

    assert isinstance(result, Coordinates)
    assert result.lat == pytest.approx(40.7178)
    assert result.lng == pytest.approx(-74.0431)


@pytest.mark.asyncio
async def test_geocode_location_no_api_key(mock_settings_no_key):
    """Test that missing API key returns None without making HTTP calls."""
    with patch("tools.geocode_location.get_settings", return_value=mock_settings_no_key):
        from tools.geocode_location import geocode_location

        result = await geocode_location("5th Ave, Manhattan")

    assert result is None


@pytest.mark.asyncio
async def test_geocode_location_empty_input(mock_settings):
    """Test that empty location text returns None."""
    with patch("tools.geocode_location.get_settings", return_value=mock_settings):
        from tools.geocode_location import geocode_location

        result = await geocode_location("")

    assert result is None


@pytest.mark.asyncio
async def test_geocode_location_api_zero_results(mock_settings):
    """Test that ZERO_RESULTS API status returns None."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "ZERO_RESULTS", "results": []}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("tools.geocode_location.get_settings", return_value=mock_settings), \
         patch("tools.geocode_location.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

        from tools.geocode_location import geocode_location

        result = await geocode_location("Nonexistent Place XYZ 99999")

    assert result is None


@pytest.mark.asyncio
async def test_geocode_location_http_error(mock_settings):
    """Test that HTTP errors return None gracefully."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.RequestError("Connection refused")

    with patch("tools.geocode_location.get_settings", return_value=mock_settings), \
         patch("tools.geocode_location.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

        from tools.geocode_location import geocode_location

        result = await geocode_location("123 Main St, New York")

    assert result is None
