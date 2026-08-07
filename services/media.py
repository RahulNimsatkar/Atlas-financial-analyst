"""Voice transcription (Groq Whisper) + image understanding (OpenRouter vision)."""
import base64
import logging
from typing import Optional

import httpx
from groq import Groq

from config import GROQ_API_KEY, OPENROUTER_API_KEY, WHISPER_MODEL

_groq = Groq(api_key=GROQ_API_KEY)
_VISION_MODEL = "google/gemma-4-26b-a4b-it:free"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
log = logging.getLogger(__name__)


def transcribe_voice(data: bytes, filename: str = "voice.ogg") -> Optional[str]:
    """Telegram voice note bytes -> text."""
    try:
        result = _groq.audio.transcriptions.create(
            file=(filename, data), model=WHISPER_MODEL,
        )
        return result.text.strip()
    except Exception:
        return None


def analyze_image(data: bytes, user_question: str = "") -> Optional[str]:
    """Chart / financial-statement screenshot -> analysis via OpenRouter vision."""
    if not OPENROUTER_API_KEY:
        log.warning("OPENROUTER_API_KEY not set — image analysis disabled")
        return None
    try:
        image_b64 = base64.b64encode(data).decode("utf-8")
        prompt = (
            "You are a financial analyst. Analyze this image (likely a stock chart, "
            "financial statement, or business document). Be concise and specific — "
            "key numbers, trends, and what matters most."
            + (f" The user asked: {user_question}" if user_question else "")
        )
        payload = {
            "model": _VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        resp = httpx.post(_OPENROUTER_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        log.exception("analyze_image failed")
        return None
