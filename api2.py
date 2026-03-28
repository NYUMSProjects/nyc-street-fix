"""
NYC StreetFix — Voice-first REST API.

Same guided pipeline as api.py but every interaction is primarily audio:
  - User input: audio is auto-transcribed before processing
  - Every response includes a spoken TTS audio file (autoplay on client)

Run:  uvicorn api2:app --host 0.0.0.0 --port 8001 --reload
"""
from __future__ import annotations

import json
import mimetypes
import re
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

import google.genai as genai
from google.genai import types

from agents.prompts import SYSTEM_PROMPT, FEW_SHOT_EXAMPLES
from config.settings import get_settings
from config.taxonomy import AGENCY_MAPPING, CATEGORY_311_CODES

from tools.classify_scene import classify_scene
from tools.detect_language import detect_language, language_name
from tools.extract_incident import extract_incident
from tools.geocode_location import geocode_location
from tools.reverse_geocode_location import reverse_geocode_location
from tools.draft_311_report import draft_311_report
from tools.generate_visual_card import generate_visual_card
from tools.translate_summary import translate_summary
from tools.check_mta_elevators import check_mta_elevators
from tools.lookup_flood_history import lookup_flood_history
from tools.submit_complaint import submit_311_complaint

settings = get_settings()

VISUAL_CARD_DIR = Path("/tmp/nyc_streetfix_cards")
VISUAL_CARD_DIR.mkdir(parents=True, exist_ok=True)

_sessions: dict[str, list[types.Content]] = {}
_pipeline_states: dict[str, dict] = {}

# ── MIME helpers ────────────────────────────────────────────────────────────
IMAGE_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
}
AUDIO_MIME = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".ogg": "audio/ogg", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".flac": "audio/flac",
}
VIDEO_MIME = {
    ".mp4": "video/mp4", ".mov": "video/quicktime",
    ".avi": "video/x-msvideo", ".webm": "video/webm",
}


def _detect_mime(path: str) -> tuple[str, str]:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_MIME:
        return "image", IMAGE_MIME[ext]
    if ext in AUDIO_MIME:
        return "audio", AUDIO_MIME[ext]
    if ext in VIDEO_MIME:
        return "video", VIDEO_MIME[ext]
    guessed, _ = mimetypes.guess_type(path)
    return "unknown", guessed or "application/octet-stream"


# ── Intent detection ──────────────────────────────────────────────────────

def _is_affirmative(text: str) -> bool:
    return bool(re.search(
        r"\b(yes|correct|right|confirm|ok|sure|yeah|yep|looks good|good|"
        r"that'?s right|affirmative|proceed|sounds good|go ahead)\b",
        text.lower().strip(),
    ))


def _is_negative(text: str) -> bool:
    return bool(re.search(
        r"\b(no|wrong|incorrect|not right|nope|negative|different|that'?s wrong)\b",
        text.lower().strip(),
    ))


def _extract_inline_correction(text: str) -> str | None:
    """Return inline address correction from messages like 'no, the correct address is X'."""
    patterns = [
        r"\b(?:no|wrong|incorrect|nope)\b.{0,30}?\b(?:address\s+is|it'?s?|should\s+be|is\s+actually)\s+(.{5,})",
        r"^\s*(?:no|wrong|incorrect|nope)[,\s]+(.{10,})$",
    ]
    for pattern in patterns:
        m = re.search(pattern, text.strip(), re.IGNORECASE)
        if m:
            correction = m.group(1).strip().rstrip(".")
            if len(correction) >= 5:
                return correction
    return None


def _detect_submission_mode(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\b(sms|text)\b", t):
        return "sms"
    if re.search(r"\b(email|mail)\b", t):
        return "email"
    if re.search(r"\b(call|phone)\b", t):
        return "call"
    return None


# ── Response model ────────────────────────────────────────────────────────

class ReportDraft(BaseModel):
    issueType: str
    locationHint: str
    agency: str
    complaintPreview: str


class VoiceChatResponse(BaseModel):
    text: str
    sessionId: str = ""
    transcript: Optional[str] = None
    reportDraft: Optional[ReportDraft] = None
    cardUrl: Optional[str] = None
    audioUrl: Optional[str] = None
    pipelineStep: Optional[str] = None


# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(title="NYC StreetFix Voice API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _save_upload(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "file").suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=str(VISUAL_CARD_DIR))
    tmp.write(upload.file.read())
    tmp.close()
    return tmp.name


def _card_url(path: str | None) -> str | None:
    if path and Path(path).exists():
        return f"/api/cards/{Path(path).name}"
    return None


# ── TTS — every response is spoken ───────────────────────────────────────

async def _localize(text: str, lang: str) -> str:
    """Translate a short system message to the user's language. Returns original on failure."""
    if lang == "en":
        return text
    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        resp = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                f"Translate the following message to {language_name(lang)}. "
                f"Keep proper nouns (street names, agency names like DOT, DEP, DSNY, '311') in English. "
                f"Return ONLY the translated text, nothing else.\n\n{text}"
            ],
            config=types.GenerateContentConfig(temperature=0.0),
        )
        return resp.text.strip() if resp.text else text
    except Exception:
        return text


async def _generate_tts(text: str, lang: str = "en") -> str | None:
    try:
        from gtts import gTTS
        try:
            tts = gTTS(text=text, lang=lang)
        except ValueError:
            tts = gTTS(text=text, lang="en")
        audio_path = str(VISUAL_CARD_DIR / f"tts_{uuid.uuid4().hex}.mp3")
        tts.save(audio_path)
        return audio_path
    except Exception as e:
        print(f"TTS Error: {e}")
        return None


async def _speak_text(text: str, client: genai.Client, lang: str = "en") -> str | None:
    """Convert a text response into natural spoken audio via Gemini + gTTS."""
    try:
        lang_hint = f" Respond in {language_name(lang)}." if lang != "en" else ""
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Part(text=(
                f"You are a friendly NYC 311 voice assistant.{lang_hint} Rewrite the following "
                "text as a natural, conversational spoken response. Keep it concise "
                "(2-4 sentences). Do not include markdown, bullet points, or any "
                "formatting. Just plain spoken words.\n\n"
                f"Text:\n{text}"
            ))],
            config=types.GenerateContentConfig(temperature=0.7),
        )
        spoken = response.text.strip()
        print(f"[Voice API TTS ({lang})] -> {spoken}")
        return await _generate_tts(spoken, lang=lang)
    except Exception as e:
        print(f"Speak error: {e}")
        return await _generate_tts(text[:500], lang=lang)


async def _generate_complaint_audio_summary(incident_dict: dict, client: genai.Client) -> str | None:
    prompt = (
        "You are an AI 311 voice assistant. Produce a friendly 3-4 sentence spoken summary "
        "of this complaint for the user. Cover: what the issue is, where it is, how severe "
        "it is, and which agency will handle it. End with: 'Are these details correct?'\n\n"
        f"Issue: {incident_dict.get('issue_type', '').replace('_', ' ')}\n"
        f"Severity: {incident_dict.get('severity', '')}\n"
        f"Location: {incident_dict.get('location_text', 'the reported location')}\n"
        f"Agency: {incident_dict.get('likely_agency', '311')}\n"
        f"Summary: {incident_dict.get('report_summary', '')}"
    )
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Part(text=prompt)],
            config=types.GenerateContentConfig(temperature=0.7),
        )
        return await _generate_tts(response.text.strip())
    except Exception as e:
        print(f"Complaint audio summary error: {e}")
        return await _generate_tts("I've generated the complaint. Are these details correct?")


# ── Transcription — every audio input is transcribed ─────────────────────

async def _transcribe_audio(audio_path: str, client: genai.Client) -> str:
    try:
        _, mime = _detect_mime(audio_path)
        file_bytes = Path(audio_path).read_bytes()
        try:
            uploaded = client.files.upload(file=audio_path, config={"mime_type": mime})
            audio_part = types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime)
        except Exception:
            audio_part = types.Part.from_bytes(data=file_bytes, mime_type=mime)

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                audio_part,
                types.Part(text="Transcribe exactly what is spoken in this audio. Return only the spoken words, nothing else."),
            ],
            config=types.GenerateContentConfig(temperature=0.0),
        )
        transcript = response.text.strip()
        print(f"[Voice API Transcribed] -> {transcript}")
        return transcript
    except Exception as e:
        print(f"Transcription error: {e}")
        return ""


# ── Content builder ────────────────────────────────────────────────────────

async def _build_content_parts(text: str, files: list[str], client: genai.Client) -> list:
    parts = []
    for fpath in files:
        category, mime = _detect_mime(fpath)
        file_bytes = Path(fpath).read_bytes()
        if category == "image":
            parts.append(types.Part.from_bytes(data=file_bytes, mime_type=mime))
        elif category in ("audio", "video"):
            try:
                uploaded = client.files.upload(file=fpath, config={"mime_type": mime})
                parts.append(types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime))
            except Exception:
                parts.append(types.Part.from_bytes(data=file_bytes, mime_type=mime))
    if text.strip():
        parts.append(types.Part(text=text))
    return parts


# ── Auto pipeline ──────────────────────────────────────────────────────────

async def _run_auto_pipeline(image_path: str, description: str, address: str = "", user_lang: str = "en"):
    try:
        classification = await classify_scene(image_path=image_path, description=description)
        if classification.confidence < 0.5 or classification.issue_type.value == "unknown":
            return None

        incident = await extract_incident(
            image_path=image_path,
            description=description or classification.description,
            location_text=address,
        )
        incident.likely_agency = AGENCY_MAPPING.get(incident.issue_type, "311")

        complaint = await draft_311_report(incident, user_lang="en")
        incident.complaint_text = complaint

        card_path = str(VISUAL_CARD_DIR / f"{uuid.uuid4().hex}.png")
        await generate_visual_card(incident, card_path, image_path=image_path)

        issue_label = incident.issue_type.value.replace("_", " ").title()
        sev = incident.severity.value.upper()
        agency = incident.likely_agency
        cat = CATEGORY_311_CODES.get(incident.issue_type, "Other")

        summary = (
            f"**Detected: {issue_label}** | **Severity: {sev}** | "
            f"**Agency: {agency}** | **311 Category: {cat}**\n\n"
            f"{incident.report_summary}\n\n"
            f"---\n**311 Complaint Draft:**\n\n{complaint}\n\n"
        )
        if incident.follow_up_questions:
            qs = "\n".join(f"- {q}" for q in incident.follow_up_questions)
            summary += f"**Additional info needed:**\n{qs}\n\n"

        incident_dict = {
            "complaint_text": incident.complaint_text,
            "location_text": incident.location_text or address,
            "likely_agency": incident.likely_agency,
            "issue_type": incident.issue_type.value,
            "severity": incident.severity.value,
            "report_summary": incident.report_summary,
        }
        return summary, card_path, incident_dict

    except Exception as exc:
        print(f"Auto-pipeline error: {exc}")
        return None


# ── Correction helper ──────────────────────────────────────────────────────

async def _apply_complaint_corrections(incident_dict: dict, corrections: str, client: genai.Client) -> dict:
    prompt = (
        "You are updating a 311 complaint based on user corrections. "
        "Apply the corrections and return a JSON object with exactly three keys: "
        "'complaint_text', 'report_summary', and 'location_text'. "
        "If a field is not affected by the correction, repeat its current value unchanged.\n\n"
        f"Current complaint text:\n{incident_dict.get('complaint_text', '')}\n\n"
        f"Current summary:\n{incident_dict.get('report_summary', '')}\n\n"
        f"Current location:\n{incident_dict.get('location_text', '')}\n\n"
        f"User corrections:\n{corrections}\n\n"
        "Return only valid JSON, no markdown."
    )
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Part(text=prompt)],
            config=types.GenerateContentConfig(temperature=0.3),
        )
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.text.strip(), flags=re.MULTILINE)
        updated = json.loads(text)
        result = dict(incident_dict)
        result["complaint_text"] = updated.get("complaint_text", result["complaint_text"])
        result["report_summary"] = updated.get("report_summary", result["report_summary"])
        result["location_text"] = updated.get("location_text", result.get("location_text", ""))
    except Exception as e:
        print(f"Correction apply error: {e}")
        result = dict(incident_dict)
    return result


# ── Core voice chat turn ──────────────────────────────────────────────────

async def _voice_chat_turn(
    message_text: str,
    file_paths: list[str],
    session_id: str,
    lat: float | None,
    lon: float | None,
) -> VoiceChatResponse:
    client = genai.Client(api_key=settings.gemini_api_key)
    history = _sessions.setdefault(session_id, [])
    state = _pipeline_states.setdefault(session_id, {})

    # Always transcribe audio input first (voice-first mode)
    audio_files = [f for f in file_paths if _detect_mime(f)[0] == "audio"]
    transcript = ""
    if audio_files:
        transcript = await _transcribe_audio(audio_files[0], client)
        if not message_text:
            message_text = transcript

    # ── Detect user language ──────────────────────────────────────────────
    current_lang = state.get("lang", "en")
    if current_lang != "en":
        user_lang = current_lang
    elif message_text.strip():
        detected = await detect_language(message_text)
        user_lang = detected if detected != "en" else current_lang
    else:
        user_lang = current_lang
    state["lang"] = user_lang
    print(f"DEBUG: [api2] lang detect: input='{message_text[:80]}' detected='{user_lang}' prev='{current_lang}'", flush=True)

    pipeline_step = state.get("pipeline_step")

    # ── Route ongoing pipeline steps ───────────────────────────────────────
    if pipeline_step == "awaiting_address_confirmation":
        inline = _extract_inline_correction(message_text)
        if inline:
            resp = await _step_process_incident(state, inline, client)
            resp.transcript = transcript or None
            return resp
        elif _is_affirmative(message_text):
            address = state.get("pending_address", "")
            resp = await _step_process_incident(state, address, client)
            resp.transcript = transcript or None
            return resp
        else:
            state["pipeline_step"] = "awaiting_address_correction"
            text = await _localize("What is the correct address for the incident?", user_lang)
            audio = await _generate_tts(text, lang=user_lang)
            return VoiceChatResponse(
                text=text, audioUrl=_card_url(audio),
                pipelineStep="awaiting_address_correction", transcript=transcript or None,
            )

    elif pipeline_step == "awaiting_address_correction":
        resp = await _step_process_incident(state, message_text.strip(), client)
        resp.transcript = transcript or None
        return resp

    elif pipeline_step == "awaiting_details_confirmation":
        if _is_affirmative(message_text):
            resp = await _step_ask_submission_mode(state)
            resp.transcript = transcript or None
            return resp
        else:
            state["pipeline_step"] = "awaiting_details_correction"
            text = await _localize("What needs to be corrected in the complaint?", user_lang)
            audio = await _generate_tts(text, lang=user_lang)
            return VoiceChatResponse(
                text=text, audioUrl=_card_url(audio),
                pipelineStep="awaiting_details_correction", transcript=transcript or None,
            )

    elif pipeline_step == "awaiting_details_correction":
        updated = await _apply_complaint_corrections(
            state.get("pending_incident", {}), message_text, client,
        )
        state["pending_incident"] = updated
        state["pipeline_step"] = "awaiting_details_confirmation"
        confirm_msg = await _localize("Are these details correct now? (yes / no)", user_lang)
        text = (
            f"**Updated 311 Complaint Draft:**\n\n{updated.get('complaint_text', '')}\n\n"
            f"**{confirm_msg}**"
        )
        audio = await _generate_complaint_audio_summary(updated, client)
        draft = ReportDraft(
            issueType=updated.get("issue_type", "").replace("_", " ").title(),
            locationHint=updated.get("location_text", ""),
            agency=updated.get("likely_agency", "311"),
            complaintPreview=updated.get("complaint_text", ""),
        )
        return VoiceChatResponse(
            text=text, reportDraft=draft,
            cardUrl=_card_url(state.get("pending_card")),
            audioUrl=_card_url(audio),
            pipelineStep="awaiting_details_confirmation",
            transcript=transcript or None,
        )

    elif pipeline_step == "awaiting_submission_mode":
        mode = _detect_submission_mode(message_text)
        if mode:
            resp = await _step_submit(mode, state, client)
            resp.transcript = transcript or None
            return resp
        else:
            text = await _localize("Please choose a submission mode: SMS, Email, or Call.", user_lang)
            audio = await _generate_tts(text, lang=user_lang)
            return VoiceChatResponse(
                text=text, audioUrl=_card_url(audio),
                pipelineStep="awaiting_submission_mode", transcript=transcript or None,
            )

    # ── New submission: image + lat/lon → guided pipeline ──────────────────
    image_files = [f for f in file_paths if _detect_mime(f)[0] == "image"]

    if image_files and lat is not None and lon is not None:
        resp = await _step_reverse_geocode(lat, lon, image_files[0], message_text, state)
        resp.transcript = transcript or None
        return resp

    # ── Image without lat/lon → immediate auto-pipeline ───────────────────
    if image_files:
        result = await _run_auto_pipeline(image_files[0], message_text, user_lang=user_lang)
        if result:
            auto_reply, card_path, incident_dict = result
            non_audio_files = [f for f in file_paths if _detect_mime(f)[0] != "audio"]
            user_parts = await _build_content_parts(
                message_text or "I'm sending you an image of a street issue.",
                non_audio_files, client,
            )
            history.append(types.Content(role="user", parts=user_parts))
            history.append(types.Content(role="model", parts=[types.Part(text=auto_reply)]))

            audio_path = await _speak_text(auto_reply, client, lang=user_lang)
            draft = ReportDraft(
                issueType=f"{incident_dict['issue_type'].replace('_', ' ').title()}",
                locationHint=incident_dict.get("location_text", "Confirm intersection or address."),
                agency=incident_dict.get("likely_agency", "311"),
                complaintPreview=incident_dict.get("complaint_text", ""),
            )
            return VoiceChatResponse(
                text=auto_reply, reportDraft=draft,
                cardUrl=_card_url(card_path), audioUrl=_card_url(audio_path),
                transcript=transcript or None,
            )

    # ── General LLM turn ──────────────────────────────────────────────────
    non_audio_files = [f for f in file_paths if _detect_mime(f)[0] != "audio"]
    user_parts = await _build_content_parts(message_text, non_audio_files, client)
    if not user_parts:
        text = "I didn't catch that. Could you repeat?"
        audio = await _generate_tts(text)
        return VoiceChatResponse(text=text, audioUrl=_card_url(audio))

    history.append(types.Content(role="user", parts=user_parts))

    system_instruction = SYSTEM_PROMPT
    if user_lang != "en":
        lang_label = language_name(user_lang)
        lang_prefix = (
            f"CRITICAL INSTRUCTION — LANGUAGE REQUIREMENT:\n"
            f"The user is communicating in {lang_label} ({user_lang}). "
            f"You MUST write your ENTIRE response in {lang_label}. "
            f"Do NOT respond in English. Every sentence must be in {lang_label}. "
            f"Only keep proper nouns in English: street names, agency names (DOT, DEP, DSNY), and \"311\".\n\n"
        )
        system_instruction = lang_prefix + system_instruction

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=history,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
            max_output_tokens=1024,
        ),
    )
    reply = response.text.strip()
    history.append(types.Content(role="model", parts=[types.Part(text=reply)]))

    audio_path = await _speak_text(reply, client, lang=user_lang)
    return VoiceChatResponse(
        text=reply, audioUrl=_card_url(audio_path), transcript=transcript or None,
    )


# ── Pipeline step functions (return VoiceChatResponse with audio) ─────────

async def _step_reverse_geocode(lat: float, lon: float, image_path: str, description: str, state: dict) -> VoiceChatResponse:
    address = await reverse_geocode_location(lat, lon)
    lang = state.get("lang", "en")
    state["pipeline_step"] = "awaiting_address_confirmation"
    state["pending_image"] = image_path
    state["pending_description"] = description

    if address:
        state["pending_address"] = address
        text = await _localize(
            f"I found this address for the provided coordinates:\n\n"
            f"**{address}**\n\n"
            "Is this the correct location for the incident? (yes / no)",
            lang,
        )
        audio = await _generate_tts(
            await _localize(f"I found this address: {address}. Is this the correct location?", lang),
            lang=lang,
        )
    else:
        state["pending_address"] = ""
        state["pipeline_step"] = "awaiting_address_correction"
        text = await _localize(
            "I couldn't determine the address from those coordinates. "
            "Please tell me the correct address for the incident.",
            lang,
        )
        audio = await _generate_tts(text, lang=lang)

    return VoiceChatResponse(text=text, audioUrl=_card_url(audio), pipelineStep=state["pipeline_step"])


async def _step_process_incident(state: dict, confirmed_address: str, client: genai.Client) -> VoiceChatResponse:
    image_path = state.get("pending_image", "")
    description = state.get("pending_description", "")
    lang = state.get("lang", "en")

    result = await _run_auto_pipeline(image_path, description, confirmed_address)
    if result:
        summary, card_path, incident_dict = result
        state["pipeline_step"] = "awaiting_details_confirmation"
        state["pending_incident"] = incident_dict
        state["pending_card"] = card_path
        confirm_msg = await _localize("Are these details correct? (yes / no)", lang)
        text = summary + f"\n\n**{confirm_msg}**"
        audio = await _generate_complaint_audio_summary(incident_dict, client)

        draft = ReportDraft(
            issueType=f"{incident_dict['issue_type'].replace('_', ' ').title()} - {CATEGORY_311_CODES.get(incident_dict['issue_type'], 'Other')}",
            locationHint=incident_dict.get("location_text", confirmed_address),
            agency=incident_dict.get("likely_agency", "311"),
            complaintPreview=incident_dict.get("complaint_text", ""),
        )
        return VoiceChatResponse(
            text=text, reportDraft=draft,
            cardUrl=_card_url(card_path), audioUrl=_card_url(audio),
            pipelineStep=state["pipeline_step"],
        )
    else:
        state["pipeline_step"] = None
        text = await _localize("I couldn't automatically classify the issue. Could you describe it in more detail?", lang)
        audio = await _generate_tts(text, lang=lang)
        return VoiceChatResponse(text=text, audioUrl=_card_url(audio))


async def _step_ask_submission_mode(state: dict) -> VoiceChatResponse:
    lang = state.get("lang", "en")
    state["pipeline_step"] = "awaiting_submission_mode"
    text = await _localize(
        "**How would you like to submit your complaint?**\n\n"
        "Please choose one:\n"
        "- **SMS** -- text message\n"
        "- **Email** -- email to the agency\n"
        "- **Call** -- phone call to 311",
        lang,
    )
    audio = await _generate_tts(
        await _localize("How would you like to submit your complaint? You can say SMS, Email, or Call.", lang),
        lang=lang,
    )
    return VoiceChatResponse(text=text, audioUrl=_card_url(audio), pipelineStep="awaiting_submission_mode")


async def _step_submit(mode: str, state: dict, client: genai.Client) -> VoiceChatResponse:
    lang = state.get("lang", "en")
    incident = state.get("pending_incident", {})
    success = await submit_311_complaint(mode, incident)
    state["pipeline_step"] = None
    state["pending_incident"] = None
    state["pending_card"] = None

    if success:
        agency = incident.get("likely_agency", "311")
        text = await _localize(
            f"**Your complaint has been submitted via {mode.upper()}.**\n\n"
            f"Agency **{agency}** will follow up on your report.\n\n"
            "Thank you for helping keep NYC streets safe.",
            lang,
        )
        audio = await _generate_tts(
            await _localize(f"Your complaint has been successfully submitted via {mode}. Thank you for reporting this issue!", lang),
            lang=lang,
        )
    else:
        text = await _localize(f"Submission via {mode.upper()} failed. Please try again or contact 311 directly.", lang)
        audio = await _generate_tts(text, lang=lang)
    return VoiceChatResponse(text=text, audioUrl=_card_url(audio))


# ── Routes ─────────────────────────────────────────────────────────────────

@app.post("/api/voice-chat", response_model=VoiceChatResponse)
async def voice_chat_endpoint(
    text: str = Form(""),
    session_id: str = Form(""),
    lat: Optional[str] = Form(None),
    lon: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
):
    if not session_id:
        session_id = str(uuid.uuid4())

    saved_paths: list[str] = []
    for f in files:
        if f.filename:
            saved_paths.append(_save_upload(f))

    lat_f: float | None = None
    lon_f: float | None = None
    try:
        if lat and lat.strip():
            lat_f = float(lat.strip())
        if lon and lon.strip():
            lon_f = float(lon.strip())
    except (ValueError, AttributeError):
        pass

    try:
        result = await _voice_chat_turn(text, saved_paths, session_id, lat_f, lon_f)
    except Exception as exc:
        error_text = f"Sorry, something went wrong: {exc}"
        audio = await _generate_tts("Sorry, something went wrong. Please try again.")
        result = VoiceChatResponse(text=error_text, audioUrl=_card_url(audio))

    result.sessionId = session_id
    return result


@app.get("/api/cards/{filename}")
async def serve_card(filename: str):
    path = VISUAL_CARD_DIR / filename
    if not path.exists():
        return {"error": "not found"}
    mime = "audio/mpeg" if path.suffix == ".mp3" else "image/png"
    return FileResponse(str(path), media_type=mime)


@app.delete("/api/sessions/{session_id}")
async def reset_session(session_id: str):
    _sessions.pop(session_id, None)
    _pipeline_states.pop(session_id, None)
    return {"ok": True}
