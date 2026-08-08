# Atlas — AI Financial Assistant for Telegram 🤖📈

A personal financial analyst that lives in Telegram. Conversational onboarding,
personalized daily briefings, live market data, SEC filings, natural-language
alerts, Google Sheets analysis, PDF report intelligence, voice + image input —
all through pure natural conversation. **No commands, no buttons, no menus.**

## ✨ What it does

- **Conversational onboarding** — learns your role, watchlist, interests, and
  briefing time through natural chat (every question skippable)
- **☀️ Daily Morning Brief** — personalized, watchlist-first, every item with a
  "why it matters" line. Stays **silent** if nothing important happened.
- **Live research** — quotes, fundamentals, comparisons ("Compare MSFT and
  GOOGL from an investment perspective"), news, earnings, SEC filings
- **Natural-language alerts** — "alert me if TSLA moves 5%", "remind me 1h
  before Apple's earnings", "track Nvidia's SEC filings" → real background jobs
- **📊 Google Sheets intelligence** — paste any link-shared Sheet → instant
  analysis, anomaly detection, Q&A. Works with any "Anyone with the link" sheet.
- **📄 PDF intelligence** — upload an annual report / 10-K → summary + Q&A
- **🎙 Voice + 🖼 images** — voice notes transcribed (Whisper), chart
  screenshots analyzed (Google Gemma vision via OpenRouter)
- **Memory** — remembers everything it learns. Ask it: *"What do you know
  about me?"*

## 🏗 Architecture

```
Telegram ⇄ python-telegram-bot (async)
                │
        Agent core (tool-calling loop)
                │
   ┌────────────┼───────────────┐
 Tools       JobQueue         Memory
 market (yfinance)  briefings   profile + facts
 news (Finnhub/Yahoo)  price alerts  conversation history
 EDGAR filings      filing poller   watchlist
 sheets / pdf       reminders       (SQLite/SQLAlchemy)
```

### 🤖 AI Models (multi-model architecture)

| Task | Model | Provider | Why |
|---|---|---|---|
| **Normal chat** | llama-3.1-8b-instant | Groq | Fast, low-latency responses |
| **Research & analysis** | llama-3.3-70b-versatile | Groq | Deep reasoning for comparisons, fundamentals |
| **Voice transcription** | whisper-large-v3 | Groq | Industry-leading accuracy |
| **Image/chart analysis** | gemma-4-26b-a4b-it:free | OpenRouter | Free vision model |
| **Fallback (Groq daily cap)** | llama-3.1-8b-instruct | NVIDIA | Auto-switches when Groq limit hit |

The bot **automatically chooses** the right model based on your query. Keywords like "compare", "analyze", "fundamentals" → 70B research model. Everything else → fast 8B model.

## 🚀 Setup & Run

### Step 1 — Clone and enter the project

```bash
cd atlas-financial-assistant
```

### Step 2 — Create a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Set up environment variables

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Then open `.env` and fill in your keys:

```env
# Required
TELEGRAM_BOT_TOKEN=your_token_here
GROQ_API_KEY=your_key_here

# Recommended (both free)
OPENROUTER_API_KEY=your_key_here
FINNHUB_API_KEY=your_key_here

# Optional (auto-fallback when Groq daily limit hit)
NVIDIA_API_KEY=your_key_here

# Database
DATABASE_URL=sqlite:///atlas.db  # local dev (auto-created)
# DATABASE_URL=postgresql://...  # production (Neon free tier)
```

| Key | Where to get it | Required? | Cost |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → /newbot | ✅ Required | Free |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | ✅ Required | Free |
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) | 📷 For image analysis | Free |
| `FINNHUB_API_KEY` | [finnhub.io](https://finnhub.io) | 📰 For news | Free |
| `NVIDIA_API_KEY` | [build.nvidia.com](https://build.nvidia.com) | ⚡ Groq fallback | Free |
| `DATABASE_URL` | [neon.tech](https://neon.tech) | 🚀 For deployment | Free |

### Step 5 — Run the bot

```bash
python main.py
```

On first run the bot will automatically create all database tables and start polling Telegram.
You should see:
```
Atlas is running — talk to your bot on Telegram.
```

---

### 🗄️ Database

| Environment | Setting | Notes |
|---|---|---|
| Local dev | `DATABASE_URL=sqlite:///atlas.db` | File created automatically, no setup |
| Deployed | `DATABASE_URL=postgresql://...` | Use free [Neon](https://neon.tech) PostgreSQL |

Tables created automatically on first run: `users`, `messages`, `watchlist`, `alerts`, `documents`, `profile_facts`

---

### 🛑 Stopping the bot

Press `Ctrl + C` in the terminal.

## 💬 Try these

- "Hi" → onboarding begins
- "Compare Microsoft and Google from an investment perspective"
- "Why did Nvidia move today?"
- "Track Tesla and alert me on new SEC filings"
- "Alert me if AAPL moves more than 3% in a day"
- "Remind me tomorrow at 9am to review the Fed minutes"
- Paste a Google Sheets link → "any unusual trends in this?"
- Upload a 10-K PDF → "what are the biggest risks?"
- "What do you know about me?"

## 📁 Project structure

```
atlas-financial-assistant/
├── main.py            # entrypoint
├── config.py          # env config
├── agent/             # LLM core: tool-calling loop, prompts, tool registry
├── bot/               # Telegram handlers (text/voice/photo/pdf)
├── scheduler/         # briefings, price alerts, filing poller, reminders
├── services/          # market, news, edgar, sheets, pdf, media
└── db/                # SQLAlchemy models + repository
*
```


