"""Agent core — the tool-calling loop that powers every conversation."""
import asyncio
import json
import logging
import re
import time

import groq as _groq
from groq import Groq
from openai import OpenAI as _OpenAIClient

from agent.prompts import FACT_EXTRACTION_PROMPT, SYSTEM_PROMPT, build_context_block
from agent.tools import TOOL_SCHEMAS, execute_tool
from config import (
    CHAT_MODEL, RESEARCH_MODEL, GROQ_API_KEY,
    NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL,
)
from db import repo

log = logging.getLogger(__name__)
_client = Groq(api_key=GROQ_API_KEY)
_nvidia_client = (
    _OpenAIClient(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)
    if NVIDIA_API_KEY else None
)

MAX_TOOL_ROUNDS = 6


def _is_daily_limit(exc: _groq.RateLimitError) -> bool:
    """True when the 429 is a tokens-per-day cap (retrying in seconds won't help)."""
    msg = str(exc)
    return "tokens per day" in msg or "TPD" in msg


def _parse_retry_after(exc: _groq.RateLimitError) -> str:
    """Pull the human-readable wait time out of the Groq error message."""
    try:
        match = re.search(r"try again in ([\d]+m[\d.]+s|[\d]+m|[\d.]+s)", str(exc))
        if match:
            return match.group(1)
    except Exception:
        pass
    return "a little while"


def _call_with_retry(messages: list, use_tools: bool = True,
                     max_attempts: int = 3, model: str = None):
    """Groq API call with:
    - Exponential backoff on per-minute rate-limit errors (429)
    - Immediate raise on daily token-cap errors (retrying is pointless)
    - Automatic fallback to no-tools when the model emits a malformed tool call
    """
    model = model or CHAT_MODEL
    for attempt in range(max_attempts):
        try:
            kwargs = dict(model=model, messages=messages,
                          temperature=0.4, max_tokens=1024)
            if use_tools:
                kwargs["tools"] = TOOL_SCHEMAS
                kwargs["tool_choice"] = "auto"
            return _client.chat.completions.create(**kwargs)
        except _groq.RateLimitError as exc:
            if _is_daily_limit(exc):
                raise  # no point retrying a daily cap
            if attempt < max_attempts - 1:
                wait = 2 ** attempt   # 1 s → 2 s → 4 s
                log.warning("rate-limited; retrying in %ds (attempt %d)", wait, attempt + 1)
                time.sleep(wait)
            else:
                raise
        except _groq.BadRequestError as exc:
            if "tool_use_failed" in str(exc) and use_tools:
                log.warning("malformed tool call from model — falling back to no-tools reply")
                return _call_with_retry(messages, use_tools=False,
                                        max_attempts=2, model=model)
            raise
    return None


def _alerts_summary(user_id: int) -> str:
    parts = []
    for al in repo.active_alerts(user_id=user_id):
        if al.type == "price_move":
            parts.append(f"{al.ticker} ±{al.threshold_pct:g}%")
        elif al.type == "filing":
            parts.append(f"{al.ticker} filings")
        elif al.type == "reminder":
            parts.append(f"reminder: {al.note[:40]}")
    return "; ".join(parts)


def _build_messages(user, incoming_text: str):
    facts = repo.get_facts(user.id)
    watchlist = repo.get_watchlist(user.id)
    doc = repo.active_document(user.id)
    context = build_context_block(
        user, facts, watchlist, _alerts_summary(user.id),
        f"{doc.kind}: {doc.name}" if doc else "",
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context}]
    for m in repo.recent_messages(user.id):
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": incoming_text})
    return messages


def _run_agent_sync(user, incoming_text: str, model: str = None) -> str:
    """Run the tool-calling loop. Uses CHAT_MODEL (8B) by default;
    escalates to RESEARCH_MODEL (70B) automatically when the query looks
    like deep research (fundamentals, comparisons, filings analysis)."""
    research_keywords = (
        "research", "analysis", "analyse", "analyze", "compare", "comparison",
        "fundamental", "valuation", "earnings", "annual report", "10-k", "10k",
        "deep dive", "breakdown", "explain", "why did", "outlook",
    )
    text_lower = incoming_text.lower()
    chosen_model = model or (
        RESEARCH_MODEL if any(k in text_lower for k in research_keywords)
        else CHAT_MODEL
    )
    messages = _build_messages(user, incoming_text)
    for _ in range(MAX_TOOL_ROUNDS):
        resp = _call_with_retry(messages, model=chosen_model)
        if resp is None:
            break
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return (msg.content or "").strip()
        messages.append({
            "role": "assistant", "content": msg.content or "",
            "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            log.info("tool call: %s(%s) [model=%s]", tc.function.name, args, chosen_model)
            result = execute_tool(tc.function.name, args, user)
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": result[:12000]})
    return "I gathered the data but ran long — ask me that again in one step?"


def _run_nvidia_fallback(user, incoming_text: str) -> str:
    """Called when Groq daily cap is hit. Uses NVIDIA API (OpenAI-compatible)
    with the same tool schemas so all features still work."""
    messages = _build_messages(user, incoming_text)
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            resp = _nvidia_client.chat.completions.create(
                model=NVIDIA_MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.2,
                top_p=0.7,
                max_tokens=1024,
                stream=False,
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                return (msg.content or "").strip()
            messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                log.info("nvidia tool call: %s(%s)", tc.function.name, args)
                result = execute_tool(tc.function.name, args, user)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": result[:12000]})
    except Exception as exc:
        log.warning("NVIDIA fallback failed: %s", exc)
        return "Both AI providers are temporarily unavailable — try again in a few minutes."
    return "I gathered the data but ran long — ask me that again in one step?"


def _extract_facts_sync(user, user_text: str, assistant_text: str) -> None:
    """Cheap background pass: mine the exchange for new personal facts."""
    try:
        known = repo.get_facts(user.id)
        resp = _client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": FACT_EXTRACTION_PROMPT
                 + "\nAlready known: " + json.dumps(known[-25:])},
                {"role": "user",
                 "content": f"User: {user_text}\nAssistant: {assistant_text}"},
            ],
            temperature=0, max_tokens=200,
        )
        text = (resp.choices[0].message.content or "[]").strip()
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return
        for fact in json.loads(text[start:end + 1])[:5]:
            if isinstance(fact, str) and 3 < len(fact) < 200:
                repo.add_fact(user.id, fact)
    except Exception:
        pass  # personalization is best-effort, never break the chat


async def handle_user_message(user, text: str) -> str:
    """Main entry: run agent, persist history, extract facts in background.
    Falls back to NVIDIA API automatically when Groq daily cap is hit."""
    try:
        reply = await asyncio.to_thread(_run_agent_sync, user, text)
    except _groq.RateLimitError as exc:
        if _is_daily_limit(exc) and _nvidia_client:
            log.warning("Groq daily cap hit — switching to NVIDIA fallback")
            reply = await asyncio.to_thread(_run_nvidia_fallback, user, text)
        elif _is_daily_limit(exc):
            wait = _parse_retry_after(exc)
            log.warning("Groq daily cap hit, no NVIDIA fallback configured")
            return (
                f"I've hit my daily API limit — resets in about *{wait}*. "
                f"Back to full speed after that 🕐\n\n"
                f"Need it sooner? console.groq.com/settings/billing"
            )
        else:
            wait = _parse_retry_after(exc)
            return f"API is throttled right now — give it {wait} and try again."
    if not reply:
        reply = "Hit a snag on my end — give it another shot?"
    repo.add_message(user.id, "user", text)
    repo.add_message(user.id, "assistant", reply)
    asyncio.get_running_loop().run_in_executor(
        None, _extract_facts_sync, user, text, reply
    )
    return reply


async def one_shot(system: str, user_text: str, max_tokens: int = 800) -> str:
    """Single stateless LLM call (used by briefings)."""
    def _call():
        resp = _client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user_text}],
            temperature=0.4, max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    return await asyncio.to_thread(_call)
