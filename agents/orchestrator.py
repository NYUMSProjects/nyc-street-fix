from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

import google.genai as genai
import structlog
from google.genai import types

from agents.prompts import SYSTEM_PROMPT
from config.settings import get_settings
from config.taxonomy import AGENCY_MAPPING
from schemas.incident import IncidentReport
from tools.check_mta_elevators import check_mta_elevators
from tools.classify_scene import classify_scene
from tools.draft_311_report import draft_311_report
from tools.extract_incident import extract_incident
from tools.generate_visual_card import generate_visual_card
from tools.geocode_location import geocode_location
from tools.lookup_flood_history import lookup_flood_history
from tools.translate_summary import translate_summary

logger = structlog.get_logger(__name__)


@dataclass
class ConversationState:
    """Tracks the state of a multi-turn conversation."""

    image_path: Optional[str] = None
    location_text: Optional[str] = None
    description: Optional[str] = None
    incident: Optional[IncidentReport] = None
    step: str = "greeting"  # greeting | collecting_image | collecting_location | generating_report | complete


class NYCStreetFixOrchestrator:
    """Orchestrates the NYC StreetFix agent using Google ADK."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._sessions: dict[str, ConversationState] = {}
        self._agent = None
        self._runner = None
        self._session_service = None
        self._adk_available = False
        self._setup_adk()

    def _setup_adk(self) -> None:
        """Initialize Google ADK components."""
        try:
            from google.adk.agents import Agent
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService

            self._session_service = InMemorySessionService()

            self._agent = Agent(
                model=self.settings.gemini_model,
                name="nyc_streetfix_agent",
                description="NYC 311 Co-Pilot — helps New Yorkers report street issues",
                instruction=SYSTEM_PROMPT,
                tools=[
                    classify_scene,
                    extract_incident,
                    geocode_location,
                    draft_311_report,
                    generate_visual_card,
                    translate_summary,
                    check_mta_elevators,
                    lookup_flood_history,
                ],
            )

            self._runner = Runner(
                agent=self._agent,
                app_name="nyc_streetfix",
                session_service=self._session_service,
            )

            self._adk_available = True
            logger.info("NYCStreetFixOrchestrator: ADK initialized successfully")

        except ImportError as exc:
            logger.warning("NYCStreetFixOrchestrator: ADK not available, using fallback", error=str(exc))
            self._adk_available = False
        except Exception as exc:
            logger.error("NYCStreetFixOrchestrator: ADK setup failed", error=str(exc))
            self._adk_available = False

    def _get_or_create_session(self, session_id: str) -> ConversationState:
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationState()
        return self._sessions[session_id]

    async def process_turn(
        self,
        user_message: str,
        image_path: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Handle one conversation turn.

        Args:
            user_message: The user's text input.
            image_path: Optional path to an image file.
            session_id: Session identifier; creates a new one if not provided.

        Returns:
            Agent response as a string.
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        state = self._get_or_create_session(session_id)

        if image_path:
            state.image_path = image_path

        logger.info("process_turn: processing", session_id=session_id, step=state.step)

        if self._adk_available and self._runner and self._session_service:
            return await self._process_with_adk(user_message, image_path, session_id, state)
        else:
            return await self._process_fallback(user_message, image_path, session_id, state)

    async def _process_with_adk(
        self,
        user_message: str,
        image_path: Optional[str],
        session_id: str,
        state: ConversationState,
    ) -> str:
        """Process a turn using the ADK runner."""
        try:
            from google.adk.sessions import Session

            # Ensure session exists in ADK session service
            try:
                await self._session_service.get_session(
                    app_name="nyc_streetfix",
                    user_id="user",
                    session_id=session_id,
                )
            except Exception:
                await self._session_service.create_session(
                    app_name="nyc_streetfix",
                    user_id="user",
                    session_id=session_id,
                )

            content_parts = [types.Part(text=user_message)]
            if image_path:
                import pathlib
                img_bytes = pathlib.Path(image_path).read_bytes()
                suffix = pathlib.Path(image_path).suffix.lower()
                mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
                mime_type = mime_map.get(suffix, "image/jpeg")
                content_parts.insert(0, types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

            user_content = types.Content(role="user", parts=content_parts)

            final_response = ""
            async for event in self._runner.run_async(
                user_id="user",
                session_id=session_id,
                new_message=user_content,
            ):
                if hasattr(event, "content") and event.content:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            final_response += part.text

            return final_response or "I'm processing your report. Please continue."

        except Exception as exc:
            logger.error("_process_with_adk: error", error=str(exc))
            return await self._process_fallback(user_message, image_path, session_id, state)

    async def _process_fallback(
        self,
        user_message: str,
        image_path: Optional[str],
        session_id: str,
        state: ConversationState,
    ) -> str:
        """Fallback processing using Gemini directly when ADK is unavailable."""
        client = genai.Client(api_key=self.settings.gemini_api_key)

        parts = []
        if image_path:
            import pathlib
            img_bytes = pathlib.Path(image_path).read_bytes()
            suffix = pathlib.Path(image_path).suffix.lower()
            mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
            mime_type = mime_map.get(suffix, "image/jpeg")
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

        parts.append(f"{SYSTEM_PROMPT}\n\nUser: {user_message}")

        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=parts,
            config=types.GenerateContentConfig(temperature=0.7),
        )
        return response.text.strip()

    async def run_full_journey(
        self,
        description: str,
        location_text: str,
        image_path: Optional[str] = None,
        translate_to: Optional[list[str]] = None,
        visual_card_output_path: Optional[str] = None,
    ) -> IncidentReport:
        """Run the complete automated workflow end-to-end.

        Args:
            description: Text description of the street issue.
            location_text: Address or intersection.
            image_path: Optional path to an image.
            translate_to: Optional list of language codes to translate the summary into.
            visual_card_output_path: Optional path to save visual card PNG.

        Returns:
            Fully populated IncidentReport.
        """
        logger.info("run_full_journey: starting", location=location_text)

        # Step 1: Classify
        classification = await classify_scene(image_path=image_path, description=description)
        logger.info("run_full_journey: classified", issue_type=classification.issue_type.value)

        # Step 2: Extract
        incident = await extract_incident(
            image_path=image_path,
            description=description,
            location_text=location_text,
        )

        # Step 3: Geocode
        if location_text:
            coords = await geocode_location(location_text)
            if coords:
                incident.coordinates = coords
                logger.info("run_full_journey: geocoded", lat=coords.lat, lng=coords.lng)

        # Step 4: Draft 311 complaint
        complaint_text = await draft_311_report(incident)
        incident.complaint_text = complaint_text

        # Step 5: Generate visual card
        if visual_card_output_path:
            card_path = await generate_visual_card(incident, visual_card_output_path)
            incident.visual_card_path = card_path

        # Step 6: Translations
        if translate_to:
            for lang in translate_to:
                if incident.report_summary:
                    translated = await translate_summary(incident.report_summary, lang)
                    incident.translations[lang] = translated

        # Step 7: Flood history (if coords available)
        if incident.coordinates:
            flood_data = await lookup_flood_history(
                lat=incident.coordinates.lat,
                lng=incident.coordinates.lng,
            )
            incident.flood_history = flood_data

        logger.info("run_full_journey: complete", issue_type=incident.issue_type.value)
        return incident
