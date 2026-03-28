from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.fixture(autouse=True)
def clear_mta_cache():
    """Clear the MTA elevator cache before each test."""
    import tools.check_mta_elevators as module
    module._cache.clear()
    yield
    module._cache.clear()


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.mta_api_key = "test-mta-key"
    settings.elevator_cache_ttl = 300
    return settings


@pytest.fixture
def mock_settings_no_key():
    settings = MagicMock()
    settings.mta_api_key = ""
    settings.elevator_cache_ttl = 300
    return settings


SAMPLE_MTA_RESPONSE = [
    {
        "station": "Grand Central",
        "equipment": "EL023",
        "type": "EL",
        "serving": "Out of Service",
        "linesServed": "4, 5, 6",
        "isActive": False,
    },
    {
        "station": "Times Square",
        "equipment": "ES045",
        "type": "ES",
        "serving": "In Service",
        "linesServed": "A, C, E",
        "isActive": True,
    },
    {
        "station": "72nd St",
        "equipment": "EL089",
        "type": "EL",
        "serving": "Out of Service",
        "linesServed": "1, 2, 3",
        "isActive": False,
    },
]


@pytest.mark.asyncio
async def test_check_mta_elevators_no_api_key(mock_settings_no_key):
    """Test that missing API key returns unavailable status."""
    with patch("tools.check_mta_elevators.get_settings", return_value=mock_settings_no_key):
        from tools.check_mta_elevators import check_mta_elevators

        result = await check_mta_elevators()

    assert result["status"] == "unavailable"
    assert "MTA API key not configured" in result["message"]


@pytest.mark.asyncio
async def test_check_mta_elevators_all_outages(mock_settings):
    """Test fetching all elevator outages without station filter."""
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_MTA_RESPONSE
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("tools.check_mta_elevators.get_settings", return_value=mock_settings), \
         patch("tools.check_mta_elevators.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

        from tools.check_mta_elevators import check_mta_elevators

        result = await check_mta_elevators()

    assert result["status"] == "ok"
    assert result["total_outages"] == 2  # Two "Out of Service" items
    assert result["station_filter"] is None


@pytest.mark.asyncio
async def test_check_mta_elevators_station_filter(mock_settings):
    """Test filtering outages by station name."""
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_MTA_RESPONSE
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("tools.check_mta_elevators.get_settings", return_value=mock_settings), \
         patch("tools.check_mta_elevators.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

        from tools.check_mta_elevators import check_mta_elevators

        result = await check_mta_elevators(station_name="Grand Central")

    assert result["status"] == "ok"
    assert result["station_filter"] == "Grand Central"
    assert result["total_outages"] == 1
    assert result["outages"][0]["station"] == "Grand Central"


@pytest.mark.asyncio
async def test_check_mta_elevators_caching(mock_settings):
    """Test that results are cached and the API is not called twice."""
    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_MTA_RESPONSE
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("tools.check_mta_elevators.get_settings", return_value=mock_settings), \
         patch("tools.check_mta_elevators.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

        from tools.check_mta_elevators import check_mta_elevators

        result1 = await check_mta_elevators()
        result2 = await check_mta_elevators()

    # API should only be called once due to caching
    assert mock_client.get.call_count == 1
    assert result1 == result2


@pytest.mark.asyncio
async def test_check_mta_elevators_http_error(mock_settings):
    """Test that HTTP errors return error status."""
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.RequestError("Connection failed")

    with patch("tools.check_mta_elevators.get_settings", return_value=mock_settings), \
         patch("tools.check_mta_elevators.httpx.AsyncClient") as mock_async_client:
        mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

        from tools.check_mta_elevators import check_mta_elevators

        result = await check_mta_elevators()

    assert result["status"] == "error"
    assert "message" in result
