from __future__ import annotations

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


@pytest.fixture
def sample_incident():
    return IncidentReport(
        issue_type=IssueType.CLOGGED_CATCH_BASIN,
        severity=SeverityLevel.HIGH,
        safety_risk=SafetyRisk.PEDESTRIAN_SLIP_HAZARD,
        location_text="Corner of Bergen St and Smith St, Brooklyn",
        likely_agency="DEP / 311",
        report_summary="Catch basin blocked by debris causing 3-4 inches of standing water.",
        media_attached=True,
    )


@pytest.mark.asyncio
async def test_draft_311_report_success(mock_settings, sample_incident):
    """Test successful 311 report generation returns non-empty text."""
    expected_text = (
        "A clogged catch basin at the corner of Bergen St and Smith St, Brooklyn "
        "is causing significant standing water approximately 3-4 inches deep. "
        "This presents a pedestrian slip hazard and requires immediate attention. "
        "Requesting inspection and cleaning by DEP. Category: Catch Basin Clogged/Flooding."
    )

    mock_response = MagicMock()
    mock_response.text = expected_text
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("tools.draft_311_report.get_settings", return_value=mock_settings), \
         patch("tools.draft_311_report.genai.Client", return_value=mock_client):
        from tools.draft_311_report import draft_311_report

        result = await draft_311_report(sample_incident)

    assert isinstance(result, str)
    assert len(result) > 0
    assert result == expected_text


@pytest.mark.asyncio
async def test_draft_311_report_uses_correct_category_code(mock_settings):
    """Test that the category code is included in the prompt for different issue types."""
    incident = IncidentReport(
        issue_type=IssueType.POTHOLE,
        severity=SeverityLevel.MODERATE,
        safety_risk=SafetyRisk.VEHICLE_DAMAGE,
        location_text="Broadway and 14th St, Manhattan",
        likely_agency="DOT / 311",
        report_summary="Large pothole in the roadway.",
    )

    mock_response = MagicMock()
    mock_response.text = "Pothole at Broadway and 14th St. Requesting repair by DOT. Category: Pothole."
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("tools.draft_311_report.get_settings", return_value=mock_settings), \
         patch("tools.draft_311_report.genai.Client", return_value=mock_client):
        from tools.draft_311_report import draft_311_report

        result = await draft_311_report(incident)

    # Verify the API was called with a prompt containing the category code
    call_args = mock_client.models.generate_content.call_args
    contents = call_args[1].get("contents") or call_args[0][1]
    prompt_text = contents[0] if isinstance(contents, list) else str(contents)
    assert "Pothole" in prompt_text


@pytest.mark.asyncio
async def test_draft_311_report_fallback_on_api_error(mock_settings, sample_incident):
    """Test that API errors result in a template-based fallback complaint."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API unavailable")

    with patch("tools.draft_311_report.get_settings", return_value=mock_settings), \
         patch("tools.draft_311_report.genai.Client", return_value=mock_client):
        from tools.draft_311_report import draft_311_report

        result = await draft_311_report(sample_incident)

    assert isinstance(result, str)
    assert len(result) > 0
    # Should contain key info from the incident even as fallback
    assert "clogged" in result.lower() or "catch" in result.lower() or "DEP" in result
