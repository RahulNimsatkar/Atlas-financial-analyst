"""Atlas AI Financial Assistant — entrypoint.
Run:  python main.py
"""
import logging
import os

from telegram.ext import Application, MessageHandler, filters

from bot.handlers import on_document, on_error, on_photo, on_text, on_voice
from config import GROQ_API_KEY, RENDER_URL, TELEGRAM_BOT_TOKEN
from db.models import init_db
from keep_alive import set_self_url, start_health_server
from scheduler.jobs import register_jobs

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("atlas")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN or "paste" in TELEGRAM_BOT_TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env (copy .env.example to .env)")
    if not GROQ_API_KEY or "paste" in GROQ_API_KEY:
        raise SystemExit("Set GROQ_API_KEY in .env (free at console.groq.com)")

    init_db()
    start_health_server(int(os.getenv("PORT", "8080")))
    if RENDER_URL:
        set_self_url(RENDER_URL)
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT, on_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_error_handler(on_error)

    register_jobs(app)

    log.info("Atlas is running — talk to your bot on Telegram.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
