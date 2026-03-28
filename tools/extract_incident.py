from __future__ import annotations

import json
from pathlib import Path

import structlog

import google.genai as genai
from google.genai import types

from agents.prompts import EXTRACTION_PROMPT
from config.settings import get_settings
from config.taxonomy import AGENCY_MAPPING, IssueType, SafetyRisk, SeverityLevel
from schemas.incident import IncidentReport

logger = structlog.get_logger(__name__)


async def extract_incident(
    image_path: str | None,
    description: str,
    location_text: str,
) -> IncidentReport:
    """Extract a structured incident report from user input.

    Args:
        image_path: Optional path to an image file.
        description: Text description of the issue.
        location_text: Address or intersection text from the user.

    Returns:
        IncidentReport populated with extracted fields.
    """
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    image_present_bool = image_path is not None and Path(image_path).exists() if image_path else False
    image_present_str = "true" if image_present_bool else "false"

    prompt = EXTRACTION_PROMPT.format(
        description=description,
        location_text=location_text or "Not provided",
        image_present=image_present_str,
    )

    contents: list = []

    if image_present_bool and image_path:
        image_file = Path(image_path)
        image_bytes = image_file.read_bytes()
        suffix = image_file.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        mime_type = mime_map.get(suffix, "image/jpeg")
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

    contents.append(prompt)

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        data = json.loads(raw)
        logger.info("extract_incident: extraction complete", issue_type=data.get("issue_type"))

        issue_type = IssueType(data.get("issue_type", "unknown"))
        likely_agency = AGENCY_MAPPING.get(issue_type, "311")

        report = IncidentReport(
            issue_type=issue_type,
            severity=SeverityLevel(data.get("severity", "moderate")),
            safety_risk=SafetyRisk(data.get("safety_risk", "none")),
            location_text=data.get("location_text") or location_text,
            likely_agency=likely_agency,
            report_summary=data.get("report_summary", ""),
            follow_up_questions=data.get("follow_up_questions", []),
            language=data.get("language", "en"),
            media_attached=image_present_bool,
        )
        return report

    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.error("extract_incident: failed to parse response", error=str(exc))
        return IncidentReport(
            location_text=location_text,
            report_summary=description,
            media_attached=image_present_bool,
            follow_up_questions=[
                "Can you clarify what type of issue you are reporting?",
                "What is the exact address or cross street?",
            ],
        )
    except Exception as exc:
        logger.error("extract_incident: unexpected error", error=str(exc))
        return IncidentReport(
            location_text=location_text,
            report_summary=description,
            media_attached=image_present_bool,
        )
