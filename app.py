"""
NYC StreetFix — Multimodal Chatbot UI
Full conversational 311 Co-Pilot: text, image, audio, and video support
"""
from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
import tempfile
import uuid
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

import google.genai as genai
from google.genai import types

from agents.prompts import SYSTEM_PROMPT, FEW_SHOT_EXAMPLES
from config.settings import get_settings
from config.taxonomy import AGENCY_MAPPING, CATEGORY_311_CODES
from tools.classify_scene import classify_scene
from tools.draft_311_report import draft_311_report
from tools.extract_incident import extract_incident
from tools.generate_visual_card import generate_visual_card
from tools.geocode_location import geocode_location
from tools.communications import make_311_call, send_311_sms, send_311_email

settings = get_settings()

# ── Per-session conversation history (keyed by session_id) ────────────────
_sessions: dict[str, list[types.Content]] = {}

VISUAL_CARD_DIR = Path("/tmp/nyc_streetfix_cards")
VISUAL_CARD_DIR.mkdir(parents=True, exist_ok=True)

# ── MIME helpers ───────────────────────────────────────────────────────────
IMAGE_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
AUDIO_MIME = {".mp3": "audio/mpeg", ".wav": "audio/wav",
              ".ogg": "audio/ogg", ".m4a": "audio/mp4",
              ".aac": "audio/aac", ".flac": "audio/flac"}
VIDEO_MIME = {".mp4": "video/mp4", ".mov": "video/quicktime",
              ".avi": "video/x-msvideo", ".webm": "video/webm"}


def _detect_mime(path: str) -> tuple[str, str]:
    """Return (category, mime_type) for a file path."""
    ext = Path(path).suffix.lower()
    if ext in IMAGE_MIME:
        return "image", IMAGE_MIME[ext]
    if ext in AUDIO_MIME:
        return "audio", AUDIO_MIME[ext]
    if ext in VIDEO_MIME:
        return "video", VIDEO_MIME[ext]
    guessed, _ = mimetypes.guess_type(path)
    return "unknown", guessed or "application/octet-stream"


async def _build_content_parts(
    text: str,
    files: list[str],
    client: genai.Client,
) -> list:
    """Build Gemini content parts from text and file list."""
    parts = []

    for fpath in files:
        category, mime = _detect_mime(fpath)
        file_bytes = Path(fpath).read_bytes()

        if category == "image":
            parts.append(types.Part.from_bytes(data=file_bytes, mime_type=mime))

        elif category in ("audio", "video"):
            # Use Files API for audio/video (may be large)
            try:
                uploaded = client.files.upload(
                    file=fpath,
                    config={"mime_type": mime},
                )
                parts.append(
                    types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime)
                )
            except Exception:
                # Fallback: inline bytes (size permitting)
                parts.append(types.Part.from_bytes(data=file_bytes, mime_type=mime))

    if text.strip():
        parts.append(types.Part(text=text))

    return parts


async def _run_auto_pipeline(image_path: str, description: str) -> str | None:
    """If an image is attached, run classify → extract → geocode → 311 draft automatically."""
    try:
        classification = await classify_scene(
            image_path=image_path, description=description
        )
        if classification.confidence < 0.5 or classification.issue_type.value == "unknown":
            return None  # let the main LLM handle it

        incident = await extract_incident(
            image_path=image_path,
            description=description or classification.description,
            location_text="",
        )
        incident.likely_agency = AGENCY_MAPPING.get(incident.issue_type, "311")

        complaint = await draft_311_report(incident)
        incident.complaint_text = complaint

        card_path = str(VISUAL_CARD_DIR / f"{uuid.uuid4().hex}.png")
        await generate_visual_card(incident, card_path)

        issue_label = incident.issue_type.value.replace("_", " ").title()
        sev = incident.severity.value.upper()
        agency = incident.likely_agency
        cat = CATEGORY_311_CODES.get(incident.issue_type, "Other")

        summary = (
            f"**🏙️ Detected: {issue_label}** | **Severity: {sev}** | "
            f"**Agency: {agency}** | **311 Category: {cat}**\n\n"
            f"{incident.report_summary}\n\n"
            f"---\n**📋 311 Complaint Draft:**\n\n{complaint}\n\n"
        )
        if incident.follow_up_questions:
            qs = "\n".join(f"- {q}" for q in incident.follow_up_questions)
            summary += f"**❓ I need a bit more info:**\n{qs}\n\n"

        # Store card path for display via state
        return summary, card_path

    except Exception:
        return None


async def _generate_audio_summary(text: str, client: genai.Client) -> str | None:
    """Generate a short conversational summary and text-to-speech audio path."""
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Part(text=f"You are an AI 311 voice assistant. Read this street issue report and provide a friendly, conversational 2-3 sentence response acknowledging the issue, summarizing it simply, and asking one relevant follow-up question (e.g. asking for nearby cross streets, if anyone is injured, or if it's blocking traffic).\n\nDo NOT read the entire text, just provide the natural spoken response.\n\nReport:\n{text}")],
            config=types.GenerateContentConfig(
                temperature=0.7,
            ),
        )
        audio_text = response.text.strip()
        print(f"🎤 [TTS Audio Text Generated] -> {audio_text}")
        from gtts import gTTS
        tts = gTTS(text=audio_text, lang='en')
        audio_path = str(VISUAL_CARD_DIR / f"tts_{uuid.uuid4().hex}.mp3")
        tts.save(audio_path)
        return audio_path
    except Exception as e:
        print(f"TTS Summary Error: {e}")
        return None


async def _chat_turn(
    message_text: str,
    attached_files: list[str],
    session_id: str,
) -> tuple[str, str | None, str | None]:
    """Run one conversational turn. Returns (text_reply, optional_card_path, optional_audio_path)."""
    client = genai.Client(api_key=settings.gemini_api_key)
    history = _sessions.setdefault(session_id, [])

    # ── Auto-pipeline for images ───────────────────────────────────────────
    image_files = [f for f in attached_files
                   if _detect_mime(f)[0] == "image"]
    card_path = None

    if image_files:
        result = await _run_auto_pipeline(image_files[0], message_text)
        if result:
            auto_reply, card_path = result
            # Also do a friendly conversational follow-up via LLM
            pass  # we'll just return the structured reply below

            # Add to history
            user_parts = await _build_content_parts(
                message_text or "I'm sending you an image of a street issue.",
                attached_files, client
            )
            history.append(types.Content(role="user", parts=user_parts))
            history.append(
                types.Content(role="model", parts=[types.Part(text=auto_reply)])
            )
            
            # Generate conversational audio summary
            audio_path = await _generate_audio_summary(auto_reply, client)

            return auto_reply, card_path, audio_path

    # ── General LLM turn (text / audio / video / low-confidence image) ────
    user_parts = await _build_content_parts(message_text, attached_files, client)
    if not user_parts:
        return "Please send a message or attach a file.", None, None

    # Use a chat session for automatic function calling
    chat = client.chats.create(
        model=settings.gemini_model,
        history=history,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
            tools=[make_311_call, send_311_sms, send_311_email],
        )
    )

    response = chat.send_message(user_parts)
    reply = response.text.strip()
    
    # Update our persistent history from the chat session
    _sessions[session_id] = chat.get_history()

    # Generate conversational audio summary
    audio_path = await _generate_audio_summary(reply, client)

    return reply, None, audio_path


# ── Gradio helpers ─────────────────────────────────────────────────────────

def _chat_respond(
    message: dict,          # {"text": str, "files": [path, ...]}
    history: list,          # list of Gradio chat message dicts
    session_state: dict,    # {"id": str, "card": str|None}
):
    """Gradio callback: takes multimodal message, returns updated state."""
    text = (message.get("text") or "").strip()
    files = message.get("files") or []

    if not text and not files:
        history.append({"role": "assistant", "content": "Please send a message or attach a file."})
        return history, session_state, None

    session_id = session_state.get("id") or str(uuid.uuid4())
    session_state["id"] = session_id

    try:
        reply, card_path, audio_path = asyncio.run(_chat_turn(text, files, session_id))
    except Exception as e:
        reply = f"❌ Error: {e}"
        card_path = None
        audio_path = None

    session_state["card"] = card_path

    # Build bot message — attach card image and audio inline if available
    bot_content: list = [reply]
    if card_path and Path(card_path).exists():
        bot_content.append({"path": card_path})
    if audio_path and Path(audio_path).exists():
        bot_content.append({"path": audio_path})
        
    if len(bot_content) == 1:
        bot_content = bot_content[0]

    history.append({"role": "user", "content": _format_user_content(text, files)})
    history.append({"role": "assistant", "content": bot_content})
    return history, session_state, None


def _format_user_content(text: str, files: list[str]):
    """Format user message with inline file previews using Gradio 6 format."""
    parts: list = []
    for f in files:
        # Gradio 6 Chatbot accepts {"path": ...} for all file types
        parts.append({"path": f})
    if text:
        parts.append(text)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return parts


def _handle_audio_input(audio_path: str | None, history: list, session_state: dict):
    """Process recorded microphone audio as a chat turn."""
    if audio_path is None:
        return history, session_state
    h, s, _ = _chat_respond(
        {"text": "", "files": [audio_path]},
        history,
        session_state,
    )
    return h, s


def _reset(session_state: dict):
    session_id = session_state.get("id")
    if session_id and session_id in _sessions:
        del _sessions[session_id]
    return [], {"id": str(uuid.uuid4()), "card": None}, None


# ── Initial greeting ───────────────────────────────────────────────────────
GREETING = (
    "👋 **Welcome to NYC StreetFix!** I'm your AI-powered 311 co-pilot.\n\n"
    "You can:\n"
    "- 📷 **Upload a photo** of a street issue and I'll classify it automatically\n"
    "- 🎙️ **Record a voice message** describing the problem\n"
    "- 🎥 **Send a video** of the issue\n"
    "- 💬 **Chat with me** in text — describe what you see and where\n\n"
    "I'll generate a structured 311 report, identify the right NYC agency, "
    "and draft complaint text you can submit immediately at **nyc.gov/311** or by calling **311**.\n\n"
    "**What street issue are you reporting today?**"
)

# ── Build UI ───────────────────────────────────────────────────────────────
THEME = gr.themes.Base(
    primary_hue=gr.themes.Color(
        c50="#f0f9ff", c100="#e0f2fe", c200="#bae6fd", c300="#7dd3fc",
        c400="#38bdf8", c500="#0ea5e9", c600="#0284c7", c700="#0369a1",
        c800="#075985", c900="#0c4a6e", c950="#082f49",
    ),
    neutral_hue=gr.themes.Color(
        c50="#f8fafc", c100="#f1f5f9", c200="#e2e8f0", c300="#cbd5e1",
        c400="#94a3b8", c500="#64748b", c600="#475569", c700="#334155",
        c800="#1e293b", c900="#0f172a", c950="#020617",
    ),
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui"],
).set(
    body_background_fill="#020617",
    body_text_color="#e2e8f0",
    block_background_fill="#0f172a",
    block_border_color="#1e3a5f",
    input_background_fill="#0f172a",
    input_border_color="#1e3a5f",
    button_primary_background_fill="#0ea5e9",
    button_primary_background_fill_hover="#38bdf8",
    button_primary_text_color="white",
)

CSS = """
footer { display: none !important; }
.gradio-container { max-width: 960px !important; margin: auto; }
.chatbot-header { text-align: center; padding: 20px 0 4px; }
.chatbot-header h1 {
    background: linear-gradient(90deg, #38bdf8, #818cf8);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    font-size: 2rem; margin: 0;
}
.chatbot-header p { color: #94a3b8; margin: 4px 0 0; font-size: 14px; }
#chatbot { min-height: 520px; }
.mic-btn { border-radius: 50% !important; width: 48px !important;
           height: 48px !important; padding: 0 !important; }
.reset-btn { color: #f87171 !important; border-color: #7f1d1d !important; }
"""

with gr.Blocks(title="NYC StreetFix — 311 Co-Pilot") as demo:

    # ── State ──────────────────────────────────────────────────────────────
    session_state = gr.State({"id": str(uuid.uuid4()), "card": None})

    gr.HTML("""
    <div class="chatbot-header">
      <h1>🏙️ NYC StreetFix</h1>
      <p>Multimodal 311 Co-Pilot &nbsp;·&nbsp; Text · Image · Audio · Video</p>
    </div>
    """)

    # ── Chatbot ────────────────────────────────────────────────────────────
    chatbot = gr.Chatbot(
        value=[{"role": "assistant", "content": GREETING}],
        elem_id="chatbot",
        show_label=False,
        avatar_images=(
            None,
            "https://em-content.zobj.net/source/twitter/376/cityscape_1f3d9-fe0f.png",
        ),
        height=520,
    )

    # ── Input row ──────────────────────────────────────────────────────────
    with gr.Row(equal_height=True):
        with gr.Column(scale=9):
            chat_input = gr.MultimodalTextbox(
                placeholder="Describe the issue, or attach a photo / audio / video…",
                file_types=["image", "audio", "video"],
                file_count="multiple",
                show_label=False,
                submit_btn=True,
                stop_btn=False,
            )
        with gr.Column(scale=1, min_width=60):
            reset_btn = gr.Button("🗑️", variant="secondary", size="sm",
                                  elem_classes=["reset-btn"],
                                  interactive=True)

    # ── Voice recorder (below input) ───────────────────────────────────────
    with gr.Accordion("🎙️ Voice Input — Record & Send", open=False):
        gr.Markdown(
            "_Record your voice describing the street issue. "
            "The AI will transcribe and respond._",
        )
        with gr.Row():
            mic_input = gr.Audio(
                sources=["microphone"],
                type="filepath",
                label="Hold to record",
                show_label=True,
            )
            mic_send_btn = gr.Button("📤 Send Voice", variant="primary", scale=0)

    # ── Quick examples ─────────────────────────────────────────────────────
    with gr.Accordion("💡 Quick Examples", open=False):
        gr.Examples(
            examples=[
                ["There's a massive pothole on Atlantic Ave and 4th Ave, Brooklyn — it's destroying tires."],
                ["The street light on Broadway & 125th has been out for 3 nights. Very dangerous."],
                ["Someone dumped furniture and trash bags near the Prospect Park entrance on Flatbush Ave."],
                ["Traffic signal at Canal St & Broadway is completely dark — no lights at all."],
                ["Water is gushing up from a crack near the manhole at 5th Ave & 14th St, Manhattan."],
                ["There's graffiti covering the entire wall on Flatbush Ave near the library."],
                ["An abandoned car has been parked on my block (Smith St, Brooklyn) for 2 weeks."],
            ],
            inputs=[chat_input],
            label=None,
        )

    # ── Status bar ─────────────────────────────────────────────────────────
    gr.HTML("""
    <div style="text-align:center;padding:12px 0 4px;color:#475569;font-size:12px;">
      Built with <strong style="color:#38bdf8;">Google Gemini</strong> ·
      <strong style="color:#38bdf8;">Google ADK</strong> ·
      <strong style="color:#38bdf8;">NYC Open Data</strong>
      &nbsp;|&nbsp; Submit at
      <strong style="color:#38bdf8;">nyc.gov/311</strong> or call
      <strong style="color:#38bdf8;">311</strong>
    </div>
    """)

    # ── Event wiring ───────────────────────────────────────────────────────
    chat_input.submit(
        fn=_chat_respond,
        inputs=[chat_input, chatbot, session_state],
        outputs=[chatbot, session_state, chat_input],
    )

    mic_send_btn.click(
        fn=_handle_audio_input,
        inputs=[mic_input, chatbot, session_state],
        outputs=[chatbot, session_state],
    )

    reset_btn.click(
        fn=_reset,
        inputs=[session_state],
        outputs=[chatbot, session_state, chat_input],
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        theme=THEME,
        css=CSS,
        allowed_paths=["/tmp/nyc_streetfix_cards"],
    )
