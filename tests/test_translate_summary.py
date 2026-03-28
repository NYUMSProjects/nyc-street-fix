from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.gemini_api_key = "test-api-key"
    settings.gemini_model = "gemini-2.0-flash"
    return settings


@pytest.mark.asyncio
async def test_translate_summary_to_spanish(mock_settings):
    """Test successful translation to Spanish."""
    translated_text = "Hay un bache grande en la carretera. Por favor inspeccione y repare."

    mock_response = MagicMock()
    mock_response.text = translated_text
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("tools.translate_summary.get_settings", return_value=mock_settings), \
         patch("tools.translate_summary.genai.Client", return_value=mock_client):
        from tools.translate_summary import translate_summary

        result = await translate_summary(
            "There is a large pothole in the road. Please inspect and repair.",
            "es",
        )

    assert result == translated_text


@pytest.mark.asyncio
async def test_translate_summary_english_returns_original(mock_settings):
    """Test that English target language returns the original text without API call."""
    original = "Standing water on the sidewalk after heavy rain."

    with patch("tools.translate_summary.get_settings", return_value=mock_settings), \
         patch("tools.translate_summary.genai.Client") as mock_client_cls:
        from tools.translate_summary import translate_summary

        result = await translate_summary(original, "en")

    assert result == original
    mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_translate_summary_unsupported_language_returns_original(mock_settings):
    """Test that an unsupported language code returns the original text."""
    original = "A fallen tree is blocking the street."

    with patch("tools.translate_summary.get_settings", return_value=mock_settings), \
         patch("tools.translate_summary.genai.Client") as mock_client_cls:
        from tools.translate_summary import translate_summary

        result = await translate_summary(original, "fr")  # French not in SUPPORTED_LANGUAGES

    assert result == original


@pytest.mark.asyncio
async def test_translate_summary_empty_text_returns_empty():
    """Test that empty input returns empty string."""
    from tools.translate_summary import translate_summary

    result = await translate_summary("", "es")
    assert result == ""


@pytest.mark.asyncio
async def test_translate_summary_api_error_returns_original(mock_settings):
    """Test that API errors return the original text as fallback."""
    original = "Illegal dumping reported on the corner."

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API error")

    with patch("tools.translate_summary.get_settings", return_value=mock_settings), \
         patch("tools.translate_summary.genai.Client", return_value=mock_client):
        from tools.translate_summary import translate_summary

        result = await translate_summary(original, "zh")

    assert result == original


@pytest.mark.asyncio
async def test_translate_summary_all_supported_languages(mock_settings):
    """Test that all supported non-English languages trigger API calls."""
    supported_non_english = ["es", "zh", "ru", "bn", "ko"]

    for lang in supported_non_english:
        mock_response = MagicMock()
        mock_response.text = f"Translated text in {lang}"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("tools.translate_summary.get_settings", return_value=mock_settings), \
             patch("tools.translate_summary.genai.Client", return_value=mock_client):
            from tools.translate_summary import translate_summary

            result = await translate_summary("Test complaint text.", lang)

        assert result == f"Translated text in {lang}"
        mock_client.models.generate_content.assert_called_once()
