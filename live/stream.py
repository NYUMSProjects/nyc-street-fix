from __future__ import annotations

from pathlib import Path

import structlog

import google.genai as genai
from google.genai import types

from agents.prompts import SYSTEM_PROMPT
from config.settings import get_settings

logger = structlog.get_logger(__name__)


class TextChat:
    """Phase 1 — Simple text-in, text-out chat using standard Gemini chat API.

    No Live API required. Maintains a basic conversation history.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = genai.Client(api_key=self.settings.gemini_api_key)
        self._history: list[types.Content] = []

    async def chat(self, message: str) -> str:
        """Send a message and receive a text response.

        Args:
            message: User's text message.

        Returns:
            Agent response as a string.
        """
        logger.info("TextChat.chat: sending message", length=len(message))

        self._history.append(
            types.Content(role="user", parts=[types.Part(text=message)])
        )

        try:
            response = self._client.models.generate_content(
                model=self.settings.gemini_model,
                contents=self._history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.7,
                    max_output_tokens=800,
                ),
            )

            reply = response.text.strip()
            self._history.append(
                types.Content(role="model", parts=[types.Part(text=reply)])
            )
            logger.info("TextChat.chat: received response", length=len(reply))
            return reply

        except Exception as exc:
            logger.error("TextChat.chat: error", error=str(exc))
            raise

    def reset(self) -> None:
        """Reset conversation history."""
        self._history = []


class AudioChat:
    """Phase 2 — Audio file upload and text response using Gemini Files API.

    Uploads an audio file, transcribes it, and generates a structured response.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = genai.Client(api_key=self.settings.gemini_api_key)

    async def transcribe_and_respond(self, audio_file_path: str) -> str:
        """Upload an audio file and get a text response.

        Args:
            audio_file_path: Path to an audio file (mp3, wav, ogg, etc.).

        Returns:
            Agent's text response based on the audio content.
        """
        audio_path = Path(audio_file_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

        logger.info("AudioChat.transcribe_and_respond: uploading audio", path=audio_file_path)

        suffix = audio_path.suffix.lower()
        mime_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".flac": "audio/flac",
        }
        mime_type = mime_map.get(suffix, "audio/mpeg")

        try:
            # Upload the file using the Files API
            uploaded_file = self._client.files.upload(
                file=audio_file_path,
                config={"mime_type": mime_type},
            )

            prompt = (
                f"{SYSTEM_PROMPT}\n\n"
                "The user has sent a voice message describing a street issue. "
                "Transcribe what they said, identify the issue type and location, "
                "and respond helpfully to help them file a 311 report."
            )

            response = self._client.models.generate_content(
                model=self.settings.gemini_model,
                contents=[
                    types.Part.from_uri(file_uri=uploaded_file.uri, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(temperature=0.7),
            )

            reply = response.text.strip()
            logger.info("AudioChat.transcribe_and_respond: got response", length=len(reply))
            return reply

        except Exception as exc:
            logger.error("AudioChat.transcribe_and_respond: error", error=str(exc))
            raise


class LiveStream:
    """Phase 3 — Full real-time Live API streaming with microphone and camera.

    This is a stub implementation. Full Live API streaming requires:
    - A running event loop with asyncio audio capture (e.g., PyAudio or sounddevice)
    - Microphone and camera hardware access
    - The google-genai Live API (BidiGenerateContent endpoint)
    - Proper environment setup including audio output for spoken responses

    See docs/architecture.md for the full setup requirements.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = genai.Client(api_key=self.settings.gemini_api_key)

    async def start_stream(self) -> None:
        """Start the Live API stream. Requires microphone and camera access."""
        raise NotImplementedError(
            "Full Live API streaming requires environment setup. "
            "See docs/architecture.md for requirements."
        )

    async def send_audio_chunk(self, audio_bytes: bytes) -> None:
        """Send a raw audio chunk to the Live API stream.

        This method is a placeholder for the real-time audio streaming integration.
        In a full implementation, audio chunks captured from the microphone would
        be sent here and the agent would respond with audio output.
        """
        raise NotImplementedError(
            "Full Live API streaming requires environment setup. "
            "See docs/architecture.md for requirements."
        )

    async def send_video_frame(self, frame_bytes: bytes, mime_type: str = "image/jpeg") -> None:
        """Send a video frame to the Live API stream for visual analysis.

        In a full implementation, frames from a camera feed would be sent here
        and the agent would analyze them in real time.
        """
        raise NotImplementedError(
            "Full Live API streaming requires environment setup. "
            "See docs/architecture.md for requirements."
        )
