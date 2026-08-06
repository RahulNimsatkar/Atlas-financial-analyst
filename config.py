"""Central configuration — everything comes from .env"""
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

CHAT_MODEL = os.getenv("CHAT_MODEL", "llama-3.1-8b-instant")       # fast primary
RESEARCH_MODEL = os.getenv("RESEARCH_MODEL", "llama-3.3-70b-versatile")  # deep analysis
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-large-v3")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# NVIDIA API — fallback when Groq daily limit is exhausted
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///atlas.db")
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata")

# Render keep-alive — set to your deployed URL e.g. https://atlas-bot.onrender.com
RENDER_URL = os.getenv("RENDER_URL", "")

# EDGAR requires a descriptive User-Agent
EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "AtlasAI-Hackathon contact@example.com")
