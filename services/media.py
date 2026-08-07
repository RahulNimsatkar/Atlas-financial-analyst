"""Voice transcription (Groq Whisper) + image understanding (OpenRouter vision w/ NVIDIA fallback)."""
import base64
import logging
from typing import Optional

import httpx
from groq import Groq

from config import GROQ_API_KEY, NVIDIA_API_KEY, NVIDIA_BASE_URL, OPENROUTER_API_KEY, WHISPER_MODEL

_groq = Groq(api_key=GROQ_API_KEY)
_VISION_MODEL = "google/gemma-4-26b-a4b-it:free"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_NVIDIA_VISION_MODEL = "meta/llama-3.2-11b-vision-instruct"
log = logging.getLogger(__name__)


def transcribe_voice(data: bytes, filename: str = "voice.ogg") -> Optional[str]:
    """Telegram voice note bytes -> text via Groq Whisper."""
    try:
        result = _groq.audio.transcriptions.create(
            file=(filename, data), model=WHISPER_MODEL,
        )
        return result.text.strip()
    except Exception:
        log.exception("transcribe_voice failed")
        return None


def _build_vision_payload(image_b64: str, prompt: str, model: str) -> dict:
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }


def analyze_image(data: bytes, user_question: str = "") -> Optional[str]:
    """Chart / screenshot -> analysis. Uses OpenRouter first, NVIDIA as fallback."""
    image_b64 = base64.b64encode(data).decode("utf-8")
    prompt = (
        "You are a financial analyst. Analyze this image (likely a stock chart, "
        "financial statement, or business document). Be concise and specific — "
        "key numbers, trends, and what matters most."
        + (f" The user asked: {user_question}" if user_question else "")
    )

    # Primary: OpenRouter (free Gemma vision)
    if OPENROUTER_API_KEY:
        try:
            resp = httpx.post(
                _OPENROUTER_URL,
                json=_build_vision_payload(image_b64, prompt, _VISION_MODEL),
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            log.warning("OpenRouter vision failed — trying NVIDIA fallback")

    # Fallback: NVIDIA vision
    if NVIDIA_API_KEY:
        try:
            resp = httpx.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                json=_build_vision_payload(image_b64, prompt, _NVIDIA_VISION_MODEL),
                headers={"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            log.exception("NVIDIA vision fallback also failed")

    return None
