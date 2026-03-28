from __future__ import annotations

import structlog

import google.genai as genai
from google.genai import types

from config.settings import get_settings

logger = structlog.get_logger(__name__)

LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "zh": "Chinese (Simplified)",
    "ru": "Russian",
    "bn": "Bengali",
    "ko": "Korean",
    "hi": "Hindi",
    "ht": "Haitian Creole",
    "ar": "Arabic",
    "fr": "French",
    "ur": "Urdu",
    "pl": "Polish",
    "pt": "Portuguese",
    "ja": "Japanese",
    "it": "Italian",
    "de": "German",
    "yi": "Yiddish",
}

TRANSLATE_PROMPT_TEMPLATE = """Translate the following NYC 311 incident report into {language_name}.

Maintain a professional, civic tone. Keep place names (street names, agencies like DOT, DEP, DSNY) in English.
Output ONLY the translated text, no labels or explanations.

Text to translate:
{text}
"""


async def translate_summary(text: str, target_language: str) -> str:
    """Translate a summary text into the target language using Gemini.

    Args:
        text: The text to translate.
        target_language: ISO language code (e.g., "es", "zh", "ru", "bn", "ko").

    Returns:
        Translated text, or the original text if language is "en" or unsupported.
    """
    if not text or not text.strip():
        return text

    target_language = target_language.strip().lower()

    if target_language == "en":
        return text

    language_name = LANGUAGE_NAMES.get(target_language, target_language.upper())
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    prompt = TRANSLATE_PROMPT_TEMPLATE.format(
        language_name=language_name,
        text=text,
    )

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=500,
            ),
        )
        translated = response.text.strip()
        logger.info("translate_summary: translated", target_language=target_language, length=len(translated))
        return translated

    except Exception as exc:
        logger.error("translate_summary: error during translation", error=str(exc), language=target_language)
        return text
