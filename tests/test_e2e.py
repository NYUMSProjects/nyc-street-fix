from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.taxonomy import IssueType, SeverityLevel, SafetyRisk
from schemas.incident import Coordinates, IncidentReport


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.gemini_api_key = "test-api-key"
    settings.gemini_model = "gemini-2.0-flash"
    settings.google_maps_api_key = "test-maps-key"
    settings.mta_api_key = ""
    settings.nyc_open_data_app_token = "test-token"
    settings.elevator_cache_ttl = 300
    return settings


@pytest.fixture
def flood_incident():
    return IncidentReport(
        issue_type=IssueType.CLOGGED_CATCH_BASIN,
        severity=SeverityLevel.HIGH,
        safety_risk=SafetyRisk.PEDESTRIAN_SLIP_HAZARD,
        location_text="Corner of Newark Ave and Grove St, Jersey City",
        likely_agency="DEP / 311",
        report_summary="Catch basin blocked by debris causing standing water on the sidewalk and roadway.",
        media_attached=False,
    )


@pytest.mark.asyncio
async def test_e2e_full_journey_flood_scenario(tmp_path, mock_settings):
    """End-to-end test of the full NYC StreetFix journey for a flood scenario."""

    classification_data = {
        "issue_type": "clogged_catch_basin",
        "severity": "high",
        "safety_risk": "pedestrian_slip_hazard",
        "confidence": 0.88,
        "description": "Water pooling near a clogged street drain.",
        "follow_up_questions": [],
    }
    extraction_data = {
        "issue_type": "clogged_catch_basin",
        "severity": "high",
        "safety_risk": "pedestrian_slip_hazard",
        "location_text": "Corner of Newark Ave and Grove St",
        "report_summary": "Catch basin blocked causing standing water on sidewalk.",
        "follow_up_questions": [],
        "language": "en",
        "media_attached": False,
    }
    complaint_text = (
        "A clogged catch basin at the corner of Newark Ave and Grove St is causing standing water "
        "on the sidewalk. Requesting immediate inspection by DEP. Category: Catch Basin Clogged/Flooding."
    )
    geocoding_response = {
        "status": "OK",
        "results": [{"geometry": {"location": {"lat": 40.7178, "lng": -74.0431}}}],
    }
    flood_history = {
        "status": "ok",
        "count": 3,
        "recent_incidents": [],
        "last_reported": "2026-03-01",
    }
    translation_es = "Una alcantarilla bloqueada está causando agua estancada en la acera."

    mock_genai_client = MagicMock()

    def side_effect_generate(*args, **kwargs):
        contents = kwargs.get("contents") or (args[1] if len(args) > 1 else [])
        prompt_str = str(contents)
        if "classify" in prompt_str.lower() or "issue_type" in prompt_str.lower() and "confidence" in prompt_str.lower():
            r = MagicMock()
            r.text = json.dumps(classification_data)
            return r
        elif "extract" in prompt_str.lower() or ("issue_type" in prompt_str.lower() and "report_summary" in prompt_str.lower()):
            r = MagicMock()
            r.text = json.dumps(extraction_data)
            return r
        elif "complaint" in prompt_str.lower() or "311" in prompt_str.lower():
            r = MagicMock()
            r.text = complaint_text
            return r
        elif "translate" in prompt_str.lower() or "spanish" in prompt_str.lower():
            r = MagicMock()
            r.text = translation_es
            return r
        else:
            r = MagicMock()
            r.text = json.dumps(extraction_data)
            return r

    mock_genai_client.models.generate_content.side_effect = side_effect_generate

    mock_http_response = MagicMock()
    mock_http_response.json.return_value = geocoding_response
    mock_http_response.raise_for_status = MagicMock()
    mock_http_client = AsyncMock()
    mock_http_client.get.return_value = mock_http_response

    mock_socrata = MagicMock()
    mock_socrata.get.return_value = []
    mock_socrata.close = MagicMock()

    visual_card_path = str(tmp_path / "visual_card.png")

    with patch("tools.classify_scene.get_settings", return_value=mock_settings), \
         patch("tools.classify_scene.genai.Client", return_value=mock_genai_client), \
         patch("tools.extract_incident.get_settings", return_value=mock_settings), \
         patch("tools.extract_incident.genai.Client", return_value=mock_genai_client), \
         patch("tools.draft_311_report.get_settings", return_value=mock_settings), \
         patch("tools.draft_311_report.genai.Client", return_value=mock_genai_client), \
         patch("tools.translate_summary.get_settings", return_value=mock_settings), \
         patch("tools.translate_summary.genai.Client", return_value=mock_genai_client), \
         patch("tools.geocode_location.get_settings", return_value=mock_settings), \
         patch("tools.geocode_location.httpx.AsyncClient") as mock_async_client, \
         patch("tools.lookup_flood_history.get_settings", return_value=mock_settings), \
         patch("tools.lookup_flood_history.Socrata", return_value=mock_socrata), \
         patch("agents.orchestrator.get_settings", return_value=mock_settings):

        mock_async_client.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_async_client.return_value.__aexit__ = AsyncMock(return_value=None)

        from agents.orchestrator import NYCStreetFixOrchestrator

        orchestrator = NYCStreetFixOrchestrator()
        incident = await orchestrator.run_full_journey(
            description="This drain keeps flooding every time it rains. Water is covering the sidewalk.",
            location_text="Corner of Newark Ave and Grove St",
            image_path=None,
            translate_to=["es"],
            visual_card_output_path=visual_card_path,
        )

    assert isinstance(incident, IncidentReport)
    assert incident.issue_type == IssueType.CLOGGED_CATCH_BASIN
    assert incident.severity == SeverityLevel.HIGH
    assert incident.likely_agency == "DEP / 311"
    assert incident.complaint_text is not None
    assert len(incident.complaint_text) > 0
    assert incident.coordinates is not None
    assert incident.coordinates.lat == pytest.approx(40.7178)


@pytest.mark.asyncio
async def test_e2e_orchestrator_process_turn(mock_settings):
    """Test the orchestrator process_turn method returns a string response."""
    mock_genai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "I can help you report that pothole. What is the exact address?"
    mock_genai_client.models.generate_content.return_value = mock_response

    with patch("agents.orchestrator.get_settings", return_value=mock_settings), \
         patch("google.genai.Client", return_value=mock_genai_client):
        from agents.orchestrator import NYCStreetFixOrchestrator

        orchestrator = NYCStreetFixOrchestrator()
        # ADK likely not available in test env, will use fallback
        orchestrator._adk_available = False

        with patch("agents.orchestrator.genai.Client", return_value=mock_genai_client):
            response = await orchestrator.process_turn(
                user_message="There is a pothole on 5th Ave.",
                session_id="test-session-123",
            )

    assert isinstance(response, str)
    assert len(response) > 0
