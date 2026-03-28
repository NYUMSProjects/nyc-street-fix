from __future__ import annotations

import structlog

import google.genai as genai
from google.genai import types

from config.settings import get_settings
from config.taxonomy import CATEGORY_311_CODES
from schemas.incident import IncidentReport
from tools.detect_language import language_name

logger = structlog.get_logger(__name__)

DRAFT_PROMPT_TEMPLATE = """You are an NYC 311 complaint writer. Generate a professional, factual complaint for the following incident.

Issue type: {issue_type}
311 Category: {category_code}
Severity: {severity}
Safety risk: {safety_risk}
Location: {location_text}
Agency responsible: {likely_agency}
Summary: {report_summary}
Photo attached: {media_attached}

Write a concise 311 complaint in 2-4 sentences. Requirements:
- Factual and professional, no emotional language
- Include the location, type of issue, and urgency level
- Mention the 311 category code
- End with a clear request for inspection/repair
- Do NOT include greetings or sign-offs

Respond with ONLY the complaint text, no quotes or labels.
{language_instruction}
"""


async def draft_311_report(incident: IncidentReport, user_lang: str = "en") -> str:
    """Generate a professional 311 complaint text for a given incident.

    Args:
        incident: The populated IncidentReport.

    Returns:
        311 complaint text as a string.
    """
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    category_code = CATEGORY_311_CODES.get(incident.issue_type, "Other")
    location = incident.location_text or "Location not specified"
    summary = incident.report_summary or "Street issue reported by resident."

    lang_instruction = ""
    if user_lang != "en":
        target_name = language_name(user_lang)
        lang_instruction = (
            f"\nCRITICAL: The user speaks {target_name}. You MUST provide TWO versions of the "
            f"complaint. First in {target_name}, and then in English. "
            f"Format it exactly like this:\n\n"
            f"**{target_name} Draft**:\n[draft in {target_name} here]\n\n"
            f"---\n\n**English / 311 Official Version**:\n[English draft here]"
        )

    prompt = DRAFT_PROMPT_TEMPLATE.format(
        issue_type=incident.issue_type.value,
        category_code=category_code,
        severity=incident.severity.value,
        safety_risk=incident.safety_risk.value,
        location_text=location,
        likely_agency=incident.likely_agency or "311",
        report_summary=summary,
        media_attached="Yes" if incident.media_attached else "No",
        language_instruction=lang_instruction,
    )

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.3,
            ),
        )
        complaint_text = response.text.strip()
        logger.info("draft_311_report: generated complaint", issue_type=incident.issue_type.value)
        return complaint_text

    except Exception as exc:
        logger.error("draft_311_report: error generating complaint", error=str(exc))
        # Fallback to a template-based complaint
        fallback = (
            f"Reporting a {incident.issue_type.value.replace('_', ' ')} at {location}. "
            f"Issue severity: {incident.severity.value}. {summary} "
            f"Requesting inspection and repair by {incident.likely_agency or '311'}. "
            f"311 Category: {category_code}."
        )
        return fallback
