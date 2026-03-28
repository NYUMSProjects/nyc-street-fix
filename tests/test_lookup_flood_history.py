from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.nyc_open_data_app_token = "test-token"
    return settings


@pytest.fixture
def mock_settings_no_token():
    settings = MagicMock()
    settings.nyc_open_data_app_token = ""
    return settings


SAMPLE_311_RESULTS = [
    {
        "created_date": "2026-03-15T10:00:00.000",
        "complaint_type": "Catch Basin Clogged/Flooding",
        "status": "Closed",
        "incident_address": "100 NEWARK AVE",
        "borough": "BROOKLYN",
        "latitude": "40.7178",
        "longitude": "-74.0431",
    },
    {
        "created_date": "2026-02-20T14:30:00.000",
        "complaint_type": "Sewer Backup/Flooding",
        "status": "Open",
        "incident_address": "150 GROVE ST",
        "borough": "BROOKLYN",
        "latitude": "40.7175",
        "longitude": "-74.0428",
    },
    {
        "created_date": "2026-01-10T08:00:00.000",
        "complaint_type": "Flooding",
        "status": "Closed",
        "incident_address": "200 NEWARK AVE",
        "borough": "BROOKLYN",
        "latitude": "40.7181",
        "longitude": "-74.0435",
    },
]


@pytest.mark.asyncio
async def test_lookup_flood_history_success(mock_settings):
    """Test successful flood history lookup returns count and incidents."""
    mock_socrata = MagicMock()
    mock_socrata.get.return_value = SAMPLE_311_RESULTS
    mock_socrata.close = MagicMock()

    with patch("tools.lookup_flood_history.get_settings", return_value=mock_settings), \
         patch("tools.lookup_flood_history.Socrata", return_value=mock_socrata):
        from tools.lookup_flood_history import lookup_flood_history

        result = await lookup_flood_history(lat=40.7178, lng=-74.0431)

    assert result["status"] == "ok"
    assert result["count"] == 3
    assert len(result["recent_incidents"]) <= 5
    assert result["last_reported"] is not None


@pytest.mark.asyncio
async def test_lookup_flood_history_empty_results(mock_settings):
    """Test flood history with no matching incidents."""
    mock_socrata = MagicMock()
    mock_socrata.get.return_value = []
    mock_socrata.close = MagicMock()

    with patch("tools.lookup_flood_history.get_settings", return_value=mock_settings), \
         patch("tools.lookup_flood_history.Socrata", return_value=mock_socrata):
        from tools.lookup_flood_history import lookup_flood_history

        result = await lookup_flood_history(lat=40.7, lng=-74.0)

    assert result["status"] == "ok"
    assert result["count"] == 0
    assert result["recent_incidents"] == []
    assert result["last_reported"] is None


@pytest.mark.asyncio
async def test_lookup_flood_history_recent_incidents_capped_at_5(mock_settings):
    """Test that recent_incidents list is capped at 5 items."""
    many_results = SAMPLE_311_RESULTS * 4  # 12 results

    mock_socrata = MagicMock()
    mock_socrata.get.return_value = many_results
    mock_socrata.close = MagicMock()

    with patch("tools.lookup_flood_history.get_settings", return_value=mock_settings), \
         patch("tools.lookup_flood_history.Socrata", return_value=mock_socrata):
        from tools.lookup_flood_history import lookup_flood_history

        result = await lookup_flood_history(lat=40.7178, lng=-74.0431)

    assert result["count"] == 12
    assert len(result["recent_incidents"]) == 5


@pytest.mark.asyncio
async def test_lookup_flood_history_socrata_error(mock_settings):
    """Test that Socrata API errors return error status gracefully."""
    mock_socrata = MagicMock()
    mock_socrata.get.side_effect = Exception("Socrata API error: 500")
    mock_socrata.close = MagicMock()

    with patch("tools.lookup_flood_history.get_settings", return_value=mock_settings), \
         patch("tools.lookup_flood_history.Socrata", return_value=mock_socrata):
        from tools.lookup_flood_history import lookup_flood_history

        result = await lookup_flood_history(lat=40.7, lng=-74.0)

    assert result["status"] == "error"
    assert result["count"] == 0
    assert "message" in result


@pytest.mark.asyncio
async def test_lookup_flood_history_incident_format(mock_settings):
    """Test that recent incidents have the expected field structure."""
    mock_socrata = MagicMock()
    mock_socrata.get.return_value = SAMPLE_311_RESULTS[:1]
    mock_socrata.close = MagicMock()

    with patch("tools.lookup_flood_history.get_settings", return_value=mock_settings), \
         patch("tools.lookup_flood_history.Socrata", return_value=mock_socrata):
        from tools.lookup_flood_history import lookup_flood_history

        result = await lookup_flood_history(lat=40.7178, lng=-74.0431)

    incident = result["recent_incidents"][0]
    assert "date" in incident
    assert "type" in incident
    assert "status" in incident
    assert "address" in incident
    assert "borough" in incident
    assert incident["type"] == "Catch Basin Clogged/Flooding"
