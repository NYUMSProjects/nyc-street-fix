from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from config.taxonomy import IssueType, SafetyRisk, SeverityLevel
from schemas.incident import IncidentReport


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.gemini_api_key = "test-api-key"
    settings.gemini_model = "gemini-2.0-flash"
    return settings


def _make_mock_response(data: dict) -> MagicMock:
    response = MagicMock()
    response.text = json.dumps(data)
    return response


@pytest.mark.asyncio
async def test_extract_incident_full_data(mock_settings):
    """Test successful extraction of a complete incident report."""
    extraction_data = {
        "issue_type": "clogged_catch_basin",
        "severity": "high",
        "safety_risk": "pedestrian_slip_hazard",
        "location_text": "Corner of Bergen St and Smith St, Brooklyn",
        "report_summary": "Catch basin blocked by debris causing standing water on the sidewalk.",
        "follow_up_questions": [],
        "language": "en",
        "media_attached": False,
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(extraction_data)

    with patch("tools.extract_incident.get_settings", return_value=mock_settings), \
         patch("tools.extract_incident.genai.Client", return_value=mock_client):
        from tools.extract_incident import extract_incident

        result = await extract_incident(
            image_path=None,
            description="The drain is clogged and there is standing water on the sidewalk.",
            location_text="Bergen St and Smith St",
        )

    assert isinstance(result, IncidentReport)
    assert result.issue_type == IssueType.CLOGGED_CATCH_BASIN
    assert result.severity == SeverityLevel.HIGH
    assert result.safety_risk == SafetyRisk.PEDESTRIAN_SLIP_HAZARD
    assert result.likely_agency == "DEP / 311"
    assert "Bergen" in result.location_text


@pytest.mark.asyncio
async def test_extract_incident_agency_mapping(mock_settings):
    """Test that the correct agency is mapped for different issue types."""
    test_cases = [
        ("pothole", "DOT / 311"),
        ("flooding", "DEP / OEM"),
        ("illegal_dumping", "DSNY / 311"),
        ("fallen_tree", "DPR / 311"),
    ]

    for issue_type_str, expected_agency in test_cases:
        extraction_data = {
            "issue_type": issue_type_str,
            "severity": "moderate",
            "safety_risk": "none",
            "location_text": "5th Ave, Manhattan",
            "report_summary": f"A {issue_type_str} was reported.",
            "follow_up_questions": [],
            "language": "en",
            "media_attached": False,
        }

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = _make_mock_response(extraction_data)

        with patch("tools.extract_incident.get_settings", return_value=mock_settings), \
             patch("tools.extract_incident.genai.Client", return_value=mock_client):
            from tools.extract_incident import extract_incident

            result = await extract_incident(
                image_path=None,
                description=f"There is a {issue_type_str} here.",
                location_text="5th Ave, Manhattan",
            )

        assert result.likely_agency == expected_agency, f"Failed for {issue_type_str}"


@pytest.mark.asyncio
async def test_extract_incident_fallback_on_parse_error(mock_settings):
    """Test that a parse error results in a fallback IncidentReport with the original inputs."""
    mock_client = MagicMock()
    bad_response = MagicMock()
    bad_response.text = "not valid json"
    mock_client.models.generate_content.return_value = bad_response

    with patch("tools.extract_incident.get_settings", return_value=mock_settings), \
         patch("tools.extract_incident.genai.Client", return_value=mock_client):
        from tools.extract_incident import extract_incident

        result = await extract_incident(
            image_path=None,
            description="Something is wrong on Main St.",
            location_text="Main St and 1st Ave",
        )

    assert isinstance(result, IncidentReport)
    assert result.issue_type == IssueType.UNKNOWN
    assert result.location_text == "Main St and 1st Ave"


@pytest.mark.asyncio
async def test_extract_incident_api_exception_fallback(mock_settings):
    """Test graceful degradation when the API raises an exception."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("Connection refused")

    with patch("tools.extract_incident.get_settings", return_value=mock_settings), \
         patch("tools.extract_incident.genai.Client", return_value=mock_client):
        from tools.extract_incident import extract_incident

        result = await extract_incident(
            image_path=None,
            description="Broken streetlight on Broadway.",
            location_text="Broadway and 42nd St",
        )

    assert isinstance(result, IncidentReport)
    assert result.report_summary == "Broken streetlight on Broadway."
