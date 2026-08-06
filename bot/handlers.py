"""Telegram handlers — text, voice, photos, PDFs, sheet links.
No slash commands, no buttons, no menus. Pure conversation."""
import logging

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from agent.core import handle_user_message
from db import repo
from services import media, pdf, sheets

log = logging.getLogger(__name__)


def _get_user(update: Update):
    tg = update.effective_user
    return repo.get_or_create_user(tg.id, tg.first_name or "")


async def _reply(update: Update, text: str) -> None:
    try:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await update.effective_message.reply_text(text)  # plain fallback


async def _typing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    except Exception:
        pass


async def _process_text(update: Update, context: ContextTypes.DEFAULT_TYPE,
                        user, text: str) -> None:
    """Shared path: sheet links get ingested first, then the agent answers."""
    link = sheets.extract_sheet_id(text)
    if link:
        await _typing(update, context)
        ok, content = sheets.fetch_sheet_as_text(*link)
        if not ok:
            await _reply(update, content)
            return
        repo.save_document(user.id, "sheet", f"Google Sheet {link[0][:8]}…", content)
        text += ("\n[system note: the Google Sheet was fetched successfully and is "
                 "now the active document — use read_active_document to analyze it]")
    await _typing(update, context)
    reply = await handle_user_message(user, text)
    await _reply(update, reply)


# ---------------------------------------------------------------- handlers

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _get_user(update)
    text = (update.effective_message.text or "").strip()
    # /start arrives from Telegram's built-in Start button — treat as a greeting
    if text.startswith("/"):
        text = "Hi!"
    await _process_text(update, context, user, text)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _get_user(update)
    await _typing(update, context)
    voice = update.effective_message.voice or update.effective_message.audio
    file = await context.bot.get_file(voice.file_id)
    data = bytes(await file.download_as_bytearray())
    transcript = media.transcribe_voice(data)
    if not transcript:
        await _reply(update, "Didn't quite catch that — bad audio? Try again or just type it out.")
        return
    await _process_text(update, context, user, transcript)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _get_user(update)
    await _typing(update, context)
    photo = update.effective_message.photo[-1]  # highest resolution
    file = await context.bot.get_file(photo.file_id)
    data = bytes(await file.download_as_bytearray())
    caption = update.effective_message.caption or ""
    analysis = media.analyze_image(data, caption)
    if not analysis:
        await _reply(update, "I couldn't analyze that image right now. "
                             "If it's a report, try sending it as a PDF instead.")
        return
    # keep the analysis in conversation memory so follow-ups work
    prompt = (f"[User sent an image{': ' + caption if caption else ''}. "
              f"Vision analysis of the image: {analysis}]\n"
              "Respond to the user about this image concisely.")
    reply = await handle_user_message(user, prompt)
    await _reply(update, reply)


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _get_user(update)
    doc = update.effective_message.document
    name = doc.file_name or "document"
    if not name.lower().endswith(".pdf"):
        await _reply(update, "I can read PDFs best — could you send it as a PDF?")
        return
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await _reply(update, "That file is over 20MB — Telegram won't let me download it. "
                             "Could you send a smaller version?")
        return
    await _typing(update, context)
    file = await context.bot.get_file(doc.file_id)
    data = bytes(await file.download_as_bytearray())
    ok, content = pdf.extract_pdf_text(data, name)
    if not ok:
        await _reply(update, content)
        return
    repo.save_document(user.id, "pdf", name, content)
    caption = update.effective_message.caption or ""
    prompt = (f"[User uploaded a PDF: {name}. It is now the active document — "
              "use read_active_document to read it.] "
              + (caption if caption else
                 "Give a crisp overview: what this document is, and the 4-5 most "
                 "important takeaways. Then invite questions."))
    reply = await handle_user_message(user, prompt)
    await _reply(update, reply)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("handler error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Something went wrong on my side — try that again?")
        except Exception:
            pass
