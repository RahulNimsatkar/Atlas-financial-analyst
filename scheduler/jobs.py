"""Proactive jobs — daily briefings, price alerts, SEC filing tracker,
reminders. Runs on python-telegram-bot's JobQueue (APScheduler)."""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes

from agent.core import one_shot
from config import DEFAULT_TIMEZONE
from db import repo
from keep_alive import ping_self
from services import edgar, market, news

log = logging.getLogger(__name__)

BRIEF_SYSTEM = """You are Atlas, an AI financial analyst writing a personalized \
morning brief for Telegram. Rules:
- Short: 12-18 lines max. Telegram formatting: *bold* tickers, • bullets, an emoji \
or two for section markers (📈 🌍 📅). No markdown tables or headers.
- Lead with the user's watchlist: only items with meaningful news/moves.
- Then 2-3 market items that matter to THIS user's interests.
- EVERY item gets a short 'why it matters' angle. Never just forward a headline.
- If the raw data contains nothing genuinely important for this user, reply with \
exactly: NOTHING_IMPORTANT
- Do not invent numbers not present in the data."""


async def _send(app: Application, tg_id: int, text: str) -> None:
    try:
        await app.bot.send_message(chat_id=tg_id, text=text,
                                   parse_mode=ParseMode.MARKDOWN)
    except Exception:
        try:  # markdown fallback: send plain
            await app.bot.send_message(chat_id=tg_id, text=text)
        except Exception:
            log.exception("send failed for %s", tg_id)


# ------------------------------------------------------------ daily brief

async def _build_brief(user) -> str:
    watchlist = repo.get_watchlist(user.id)
    data_parts = []

    quotes = []
    for t in watchlist[:8]:
        try:
            quotes.append(market.get_quote(t))
        except Exception:
            pass
    if quotes:
        data_parts.append("Watchlist quotes: " + str(quotes))

    for t in watchlist[:5]:
        items = news.company_news(t, days=1, limit=3)
        if items:
            data_parts.append(f"News for {t}: " +
                              str([i["headline"] for i in items]))

    data_parts.append("Indices: " + str(market.market_overview()))
    mkt = news.general_market_news(limit=5)
    if mkt:
        data_parts.append("Market headlines: " +
                          str([i["headline"] for i in mkt]))

    profile = (f"User: {user.name}, role: {user.role}, "
               f"interests: {user.interests}, watchlist: {watchlist}")
    today = datetime.now(ZoneInfo(user.timezone or DEFAULT_TIMEZONE))
    return await one_shot(
        BRIEF_SYSTEM,
        f"{profile}\nDate: {today.strftime('%A, %b %d')}\n\nRAW DATA:\n"
        + "\n\n".join(data_parts),
    )


async def briefing_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs every minute; sends briefs whose local time just arrived."""
    now_utc = datetime.now(ZoneInfo("UTC"))
    for user in repo.all_users():
        if not user.briefing_time:
            continue
        tz = user.timezone or DEFAULT_TIMEZONE
        try:
            local = now_utc.astimezone(ZoneInfo(tz))
        except Exception:
            local = now_utc
        if local.strftime("%H:%M") != user.briefing_time:
            continue
        if user.last_brief_date == local.strftime("%Y-%m-%d"):
            continue  # already sent today
        repo.update_user(user.id, last_brief_date=local.strftime("%Y-%m-%d"))
        try:
            brief = await _build_brief(user)
            if brief and "NOTHING_IMPORTANT" not in brief:
                await _send(context.application, user.tg_id,
                            f"☀️ *Morning Brief — {local.strftime('%a, %b %d')}*\n\n{brief}")
            else:
                log.info("quiet day for user %s — staying silent", user.id)
        except Exception:
            log.exception("brief failed for user %s", user.id)


# ------------------------------------------------------------ price alerts

async def price_alert_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every 5 min: fire alerts whose daily move crossed the threshold."""
    alerts = repo.active_alerts(type="price_move")
    if not alerts:
        return
    today = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d")
    checked = {}
    for al in alerts:
        if al.last_triggered == today:
            continue  # once per day per alert
        try:
            q = checked.get(al.ticker) or await asyncio.to_thread(market.get_quote, al.ticker)
            checked[al.ticker] = q
        except Exception:
            continue
        if q["price"] is None or abs(q["change_pct"]) < al.threshold_pct:
            continue
        repo.update_alert(al.id, last_triggered=today)
        user = next((u for u in repo.all_users() if u.id == al.user_id), None)
        if not user:
            continue
        direction = "📈 up" if q["change_pct"] > 0 else "📉 down"
        await _send(context.application, user.tg_id,
                    f"🚨 *{al.ticker}* is {direction} *{q['change_pct']:+.1f}%* today "
                    f"(now {q['price']}) — crossed your {al.threshold_pct:g}% alert.\n"
                    f"Want me to pull up the news behind the move?")


# ------------------------------------------------------------ filings

async def filing_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Hourly: notify on new SEC filings for tracked tickers."""
    for al in repo.active_alerts(type="filing"):
        try:
            filings = await asyncio.to_thread(edgar.recent_filings, al.ticker, 1)
        except Exception:
            continue
        if not filings:
            continue
        newest = filings[0]
        if newest["accession"] == al.meta:
            continue
        repo.update_alert(al.id, meta=newest["accession"])
        user = next((u for u in repo.all_users() if u.id == al.user_id), None)
        if not user:
            continue
        await _send(context.application, user.tg_id,
                    f"📄 New SEC filing from *{al.ticker}*: {newest['form']} "
                    f"({newest['date']}).\nWant a summary of what it means?")


# ------------------------------------------------------------ reminders

async def reminder_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every minute: fire due one-shot reminders."""
    now = datetime.utcnow()
    for al in repo.active_alerts(type="reminder"):
        if al.remind_at and al.remind_at <= now:
            repo.deactivate_alert(al.id)
            user = next((u for u in repo.all_users() if u.id == al.user_id), None)
            if user:
                await _send(context.application, user.tg_id,
                            f"⏰ Reminder: {al.note}")


def register_jobs(app: Application) -> None:
    jq = app.job_queue
    jq.run_repeating(briefing_tick,    interval=60,   first=10)
    jq.run_repeating(reminder_tick,    interval=60,   first=20)
    jq.run_repeating(price_alert_tick, interval=300,  first=30)
    jq.run_repeating(filing_tick,      interval=3600, first=60)
    jq.run_repeating(
        lambda ctx: ping_self(),       interval=600,  first=120,  # keep-alive every 10 min
    )
    log.info("scheduler jobs registered")
