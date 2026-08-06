"""Voice transcription (Groq Whisper) + image understanding (Gemini vision)."""
from typing import Optional

from groq import Groq

from config import GEMINI_API_KEY, GEMINI_MODEL, GROQ_API_KEY, WHISPER_MODEL

_groq = Groq(api_key=GROQ_API_KEY)


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
    """Chart / financial-statement screenshot -> analysis text via Gemini."""
    if not GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        prompt = (
            "You are a financial analyst. Analyze this image (likely a stock chart, "
            "financial statement, or business document). Be concise and specific — "
            "key numbers, trends, and what matters. "
            + (f"The user asked: {user_question}" if user_question else "")
        )
        resp = model.generate_content(
            [prompt, {"mime_type": "image/jpeg", "data": data}]
        )
        return resp.text.strip()
    except Exception:
        return None
