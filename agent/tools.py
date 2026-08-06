"""Tool registry: JSON schemas for the LLM + Python implementations.
Each tool gets `user` injected by the agent core."""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import DEFAULT_TIMEZONE
from db import repo
from services import edgar, market, news

# ---------------------------------------------------------------- schemas

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_quote",
        "description": "Current stock price and day change for a ticker.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string", "description": "e.g. AAPL"}},
            "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "get_fundamentals",
        "description": "Company fundamentals: valuation, margins, growth, analyst view. Use for company analysis and comparisons (call once per company).",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"}}, "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "get_price_history",
        "description": "Price trend over a period (5d, 1mo, 3mo, 6mo, 1y).",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"},
            "period": {"type": "string", "enum": ["5d", "1mo", "3mo", "6mo", "1y"]}},
            "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "get_earnings_info",
        "description": "Next earnings date and recent quarterly revenue/net income.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"}}, "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "market_overview",
        "description": "Snapshot of S&P 500, Nasdaq, Dow — for 'how is the market' questions.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_company_news",
        "description": "Recent news headlines for a company.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"}}, "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "get_market_news",
        "description": "General market news headlines.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_sec_filings",
        "description": "Recent SEC filings (10-K, 10-Q, 8-K...) for a company.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"}}, "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "add_to_watchlist",
        "description": "Add ticker(s) to the user's watchlist.",
        "parameters": {"type": "object", "properties": {
            "tickers": {"type": "array", "items": {"type": "string"}}},
            "required": ["tickers"]}}},
    {"type": "function", "function": {
        "name": "remove_from_watchlist",
        "description": "Remove a ticker from the watchlist.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"}}, "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "create_price_alert",
        "description": "Alert the user when a stock moves more than X percent in a day.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"},
            "threshold_pct": {"type": "number", "description": "e.g. 5 for 5%"}},
            "required": ["ticker", "threshold_pct"]}}},
    {"type": "function", "function": {
        "name": "create_filing_tracker",
        "description": "Notify the user whenever a company publishes a new SEC filing.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"}}, "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "create_reminder",
        "description": "One-time reminder at a specific local date/time (e.g. before an earnings call).",
        "parameters": {"type": "object", "properties": {
            "when_local": {"type": "string", "description": "YYYY-MM-DD HH:MM in the user's timezone"},
            "note": {"type": "string"}}, "required": ["when_local", "note"]}}},
    {"type": "function", "function": {
        "name": "list_alerts",
        "description": "List the user's active alerts, trackers and reminders.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "cancel_alerts",
        "description": "Cancel active alerts for a ticker (or a reminder by its id).",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"},
            "alert_id": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "set_briefing",
        "description": "Set or change the daily briefing time (24h HH:MM, user's local time). Empty string disables it.",
        "parameters": {"type": "object", "properties": {
            "time": {"type": "string", "description": "HH:MM or '' to disable"},
            "timezone": {"type": "string", "description": "IANA tz like Asia/Kolkata, optional"}},
            "required": ["time"]}}},
    {"type": "function", "function": {
        "name": "update_profile",
        "description": "Save the user's role and/or interests to their profile.",
        "parameters": {"type": "object", "properties": {
            "role": {"type": "string"},
            "interests": {"type": "string", "description": "comma-separated"}}}}},
    {"type": "function", "function": {
        "name": "remember_fact",
        "description": "Save a new personal fact learned about the user.",
        "parameters": {"type": "object", "properties": {
            "fact": {"type": "string"}}, "required": ["fact"]}}},
    {"type": "function", "function": {
        "name": "complete_onboarding",
        "description": "Mark onboarding as finished once role + at least one interest/watchlist item are captured.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "read_active_document",
        "description": "Get the content of the PDF or Google Sheet the user most recently shared, to answer questions about it.",
        "parameters": {"type": "object", "properties": {}}}},
]

# ---------------------------------------------------------------- impls


def _user_tz(user) -> str:
    return user.timezone or DEFAULT_TIMEZONE


def execute_tool(name: str, args: dict, user) -> str:
    """Run one tool call, always returning a string for the model."""
    try:
        result = _dispatch(name, args, user)
        return json.dumps(result) if not isinstance(result, str) else result
    except Exception as e:
        return f"ERROR: tool {name} failed ({type(e).__name__}). Tell the user you couldn't fetch this right now."


def _dispatch(name: str, a: dict, user):
    if name == "get_quote":
        return market.get_quote(a["ticker"])
    if name == "get_fundamentals":
        return market.get_fundamentals(a["ticker"])
    if name == "get_price_history":
        return market.get_price_history(a["ticker"], a.get("period", "1mo"))
    if name == "get_earnings_info":
        return market.get_earnings_info(a["ticker"])
    if name == "market_overview":
        return market.market_overview()
    if name == "get_company_news":
        return news.company_news(a["ticker"])
    if name == "get_market_news":
        return news.general_market_news()
    if name == "get_sec_filings":
        return edgar.recent_filings(a["ticker"])

    if name == "add_to_watchlist":
        added = [t for t in a["tickers"] if repo.add_to_watchlist(user.id, t)]
        return {"added": added, "watchlist": repo.get_watchlist(user.id)}
    if name == "remove_from_watchlist":
        ok = repo.remove_from_watchlist(user.id, a["ticker"])
        return {"removed": ok, "watchlist": repo.get_watchlist(user.id)}

    if name == "create_price_alert":
        repo.create_alert(user.id, "price_move", ticker=a["ticker"],
                          threshold_pct=float(a["threshold_pct"]))
        return {"ok": True, "detail": f"Price alert set: {a['ticker'].upper()} ±{a['threshold_pct']}% in a day"}
    if name == "create_filing_tracker":
        acc = edgar.latest_filing_accession(a["ticker"])
        alert = repo.create_alert(user.id, "filing", ticker=a["ticker"])
        repo.update_alert(alert.id, meta=acc)
        return {"ok": True, "detail": f"Now tracking SEC filings for {a['ticker'].upper()}"}
    if name == "create_reminder":
        local = datetime.strptime(a["when_local"], "%Y-%m-%d %H:%M")
        local = local.replace(tzinfo=ZoneInfo(_user_tz(user)))
        utc = local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        if utc < datetime.utcnow():
            return {"ok": False, "detail": "That time is in the past — ask the user for a future time."}
        repo.create_alert(user.id, "reminder", remind_at=utc, note=a["note"])
        return {"ok": True, "detail": f"Reminder set for {a['when_local']} ({_user_tz(user)}): {a['note']}"}

    if name == "list_alerts":
        alerts = repo.active_alerts(user_id=user.id)
        return [{"id": al.id, "type": al.type, "ticker": al.ticker,
                 "threshold_pct": al.threshold_pct,
                 "remind_at_utc": str(al.remind_at) if al.remind_at else None,
                 "note": al.note} for al in alerts]
    if name == "cancel_alerts":
        if a.get("alert_id"):
            repo.deactivate_alert(int(a["alert_id"]))
            return {"ok": True, "detail": "Alert cancelled."}
        if a.get("ticker"):
            n = repo.cancel_alerts_for_ticker(user.id, a["ticker"])
            return {"ok": True, "detail": f"Cancelled {n} alert(s) for {a['ticker'].upper()}"}
        return {"ok": False, "detail": "Need a ticker or alert_id."}

    if name == "set_briefing":
        fields = {"briefing_time": a["time"].strip()}
        if a.get("timezone"):
            fields["timezone"] = a["timezone"]
        repo.update_user(user.id, **fields)
        return {"ok": True, "detail": f"Briefing time set to {a['time'] or 'disabled'}"}

    if name == "update_profile":
        fields = {}
        if a.get("role"):
            fields["role"] = a["role"]
        if a.get("interests"):
            existing = set(x.strip() for x in (user.interests or "").split(",") if x.strip())
            new = set(x.strip() for x in a["interests"].split(",") if x.strip())
            fields["interests"] = ", ".join(sorted(existing | new))
        if fields:
            repo.update_user(user.id, **fields)
        return {"ok": True, "saved": fields}
    if name == "remember_fact":
        repo.add_fact(user.id, a["fact"])
        return {"ok": True}
    if name == "complete_onboarding":
        repo.update_user(user.id, onboarded=True)
        return {"ok": True, "detail": "Onboarding complete."}

    if name == "read_active_document":
        doc = repo.active_document(user.id)
        if not doc:
            return "No document or sheet has been shared yet. Ask the user to upload a PDF or paste a Google Sheets link."
        return f"[{doc.kind.upper()}] {doc.name}\n\n{doc.content}"

    return f"Unknown tool {name}"
