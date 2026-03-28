"""Detect the language of user input text using Gemini."""
from __future__ import annotations

import structlog

import google.genai as genai
from google.genai import types

from config.settings import get_settings

logger = structlog.get_logger(__name__)

# Common language code → name mapping (superset of translate_summary)
LANGUAGE_CODE_TO_NAME: dict[str, str] = {
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

DETECT_PROMPT = """Detect the language of the following text and respond with ONLY the ISO 639-1 two-letter language code (e.g. "en", "es", "zh", "ru", "bn", "ko", "hi", "fr", "ar").

If the text is mostly in one language with a few English proper nouns (street names, agency names), detect the primary language, not English.

If you cannot determine the language, respond with "en".

Text:
{text}
"""


async def detect_language(text: str) -> str:
    """Detect the language of the given text.

    Args:
        text: The user's input text.

    Returns:
        ISO 639-1 language code (e.g. "en", "es", "zh").
        Defaults to "en" on failure.
    """
    if not text or not text.strip():
        return "en"

    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[DETECT_PROMPT.format(text=text)],
            config=types.GenerateContentConfig(
                temperature=0.0,
            ),
        )
        if not response.text:
            print("DEBUG: [detect_language] Empty response from Gemini", flush=True)
            return "en"
        
        raw_code = response.text.strip().lower()
        print(f"DEBUG: [detect_language] Raw Gemini response: '{raw_code}'", flush=True)
        # Clean up common debris (quotes, periods, markdown)
        code = raw_code.strip('"`\'.').split()[-1] # Usually the code is the last word if it gave a sentence
        if len(code) > 2 and ":" in code: # Handle "Language: fr"
            code = code.split(":")[-1].strip()
        
        # Validate: should be a 2-3 char code
        if 2 <= len(code) <= 3 and code.isalpha():
            logger.info("detect_language: detected", language=code, raw=raw_code)
            return code
        
        # Try finding ANY 2-letter code in the response as a fallback
        import re
        codes = re.findall(r'\b[a-z]{2}\b', raw_code)
        if codes:
            logger.info("detect_language: fallback match", language=codes[0], raw=raw_code)
            return codes[0]

        logger.warning("detect_language: unexpected response, defaulting to en", raw=raw_code)
        return "en"

    except Exception as exc:
        print(f"DEBUG: [detect_language] API ERROR: {exc}", flush=True)
        logger.error("detect_language: error", error=str(exc))
        return "en"


def language_name(code: str) -> str:
    """Get the human-readable name for a language code."""
    return LANGUAGE_CODE_TO_NAME.get(code, code.upper())
