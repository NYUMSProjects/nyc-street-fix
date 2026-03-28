from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.taxonomy import IssueType, SafetyRisk, SeverityLevel
from schemas.incident import ClassificationResult


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
async def test_classify_scene_high_confidence(mock_settings):
    """Test successful classification with high confidence returns correct result."""
    classification_data = {
        "issue_type": "pothole",
        "severity": "high",
        "safety_risk": "vehicle_damage",
        "confidence": 0.92,
        "description": "Large pothole approximately 12 inches in diameter on the roadway.",
        "follow_up_questions": [],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(classification_data)

    with patch("tools.classify_scene.get_settings", return_value=mock_settings), \
         patch("tools.classify_scene.genai.Client", return_value=mock_client):
        from tools.classify_scene import classify_scene

        result = await classify_scene(description="There is a huge pothole in the road")

    assert isinstance(result, ClassificationResult)
    assert result.issue_type == IssueType.POTHOLE
    assert result.severity == SeverityLevel.HIGH
    assert result.safety_risk == SafetyRisk.VEHICLE_DAMAGE
    assert result.confidence == 0.92
    assert result.follow_up_questions == []


@pytest.mark.asyncio
async def test_classify_scene_low_confidence_returns_unknown(mock_settings):
    """Test that low confidence classification returns UNKNOWN with follow-up questions."""
    classification_data = {
        "issue_type": "flooding",
        "severity": "moderate",
        "safety_risk": "pedestrian_slip_hazard",
        "confidence": 0.45,
        "description": "Unclear image, possibly some water on the ground.",
        "follow_up_questions": ["Can you describe what you see?"],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(classification_data)

    with patch("tools.classify_scene.get_settings", return_value=mock_settings), \
         patch("tools.classify_scene.genai.Client", return_value=mock_client):
        from tools.classify_scene import classify_scene

        result = await classify_scene(description="Something on the ground")

    assert result.issue_type == IssueType.UNKNOWN
    assert result.confidence == 0.45
    assert len(result.follow_up_questions) > 0


@pytest.mark.asyncio
async def test_classify_scene_no_input_returns_unknown():
    """Test that calling with no image and no description returns unknown."""
    from tools.classify_scene import classify_scene

    result = await classify_scene(image_path=None, description=None)

    assert result.issue_type == IssueType.UNKNOWN
    assert result.confidence == 0.0
    assert len(result.follow_up_questions) > 0


@pytest.mark.asyncio
async def test_classify_scene_json_parse_error_returns_unknown(mock_settings):
    """Test that a malformed Gemini response returns unknown gracefully."""
    mock_client = MagicMock()
    bad_response = MagicMock()
    bad_response.text = "This is not valid JSON {{{broken"
    mock_client.models.generate_content.return_value = bad_response

    with patch("tools.classify_scene.get_settings", return_value=mock_settings), \
         patch("tools.classify_scene.genai.Client", return_value=mock_client):
        from tools.classify_scene import classify_scene

        result = await classify_scene(description="A broken traffic light")

    assert result.issue_type == IssueType.UNKNOWN
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_classify_scene_api_exception_returns_unknown(mock_settings):
    """Test that an API exception returns a safe unknown result."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API timeout")

    with patch("tools.classify_scene.get_settings", return_value=mock_settings), \
         patch("tools.classify_scene.genai.Client", return_value=mock_client):
        from tools.classify_scene import classify_scene

        result = await classify_scene(description="Graffiti on the wall")

    assert result.issue_type == IssueType.UNKNOWN
    assert len(result.follow_up_questions) >= 1
