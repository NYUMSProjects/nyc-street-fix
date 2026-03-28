from __future__ import annotations

import json
from pathlib import Path

import structlog

import google.genai as genai
from google.genai import types

from agents.prompts import CLASSIFICATION_PROMPT
from config.settings import get_settings
from config.taxonomy import IssueType, SafetyRisk, SeverityLevel
from schemas.incident import ClassificationResult

logger = structlog.get_logger(__name__)


async def classify_scene(
    image_path: str | None = None,
    description: str | None = None,
) -> ClassificationResult:
    """Classify a NYC street issue from an image and/or text description.

    Args:
        image_path: Optional path to an image file.
        description: Optional text description of the issue.

    Returns:
        ClassificationResult with issue_type, severity, safety_risk, confidence,
        description, and follow_up_questions.
    """
    if not image_path and not description:
        logger.warning("classify_scene called with no inputs")
        return ClassificationResult(
            issue_type=IssueType.UNKNOWN,
            severity=SeverityLevel.MODERATE,
            safety_risk=SafetyRisk.NONE,
            confidence=0.0,
            description="No input provided.",
            follow_up_questions=[
                "Can you describe the issue you see?",
                "Can you share a photo of the problem?",
            ],
        )

    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    image_present = "true" if image_path else "false"
    desc_text = description or "No text description provided."
    prompt = CLASSIFICATION_PROMPT.format(
        description=desc_text,
        image_present=image_present,
    )

    contents: list = []

    if image_path:
        image_file = Path(image_path)
        if not image_file.exists():
            logger.warning("classify_scene: image file not found", path=image_path)
        else:
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
        # Strip markdown fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        data = json.loads(raw)
        logger.info("classify_scene: classification complete", issue_type=data.get("issue_type"), confidence=data.get("confidence"))

        result = ClassificationResult(
            issue_type=IssueType(data.get("issue_type", "unknown")),
            severity=SeverityLevel(data.get("severity", "moderate")),
            safety_risk=SafetyRisk(data.get("safety_risk", "none")),
            confidence=float(data.get("confidence", 0.5)),
            description=data.get("description", ""),
            follow_up_questions=data.get("follow_up_questions", []),
        )

        # Low confidence: force unknown and ensure follow-up questions
        if result.confidence < 0.6:
            result = ClassificationResult(
                issue_type=IssueType.UNKNOWN,
                severity=result.severity,
                safety_risk=result.safety_risk,
                confidence=result.confidence,
                description=result.description,
                follow_up_questions=result.follow_up_questions or [
                    "Can you describe the issue in more detail?",
                    "Can you provide a clearer photo of the problem?",
                ],
            )

        return result

    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.error("classify_scene: failed to parse Gemini response", error=str(exc))
        return ClassificationResult(
            issue_type=IssueType.UNKNOWN,
            severity=SeverityLevel.MODERATE,
            safety_risk=SafetyRisk.NONE,
            confidence=0.0,
            description="Classification failed due to an error.",
            follow_up_questions=[
                "Can you describe the issue you are reporting?",
                "What street or intersection is this located at?",
            ],
        )
    except Exception as exc:
        logger.error("classify_scene: unexpected error", error=str(exc))
        return ClassificationResult(
            issue_type=IssueType.UNKNOWN,
            severity=SeverityLevel.MODERATE,
            safety_risk=SafetyRisk.NONE,
            confidence=0.0,
            description="An unexpected error occurred during classification.",
            follow_up_questions=[
                "Can you describe the issue you are reporting?",
            ],
        )
