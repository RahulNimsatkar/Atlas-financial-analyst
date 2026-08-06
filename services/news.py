"""Company & market news — Finnhub if key present, else Yahoo Finance RSS."""
from typing import Dict, List

import httpx

from config import FINNHUB_API_KEY

_TIMEOUT = 15


def company_news(ticker: str, days: int = 3, limit: int = 8) -> List[Dict]:
    """Recent headlines for one ticker: [{headline, source, summary, url}]"""
    if FINNHUB_API_KEY:
        return _finnhub_company_news(ticker, days, limit)
    return _yahoo_rss(ticker, limit)


def _finnhub_company_news(ticker: str, days: int, limit: int) -> List[Dict]:
    from datetime import date, timedelta
    to = date.today()
    frm = to - timedelta(days=days)
    try:
        r = httpx.get(
            "https://finnhub.io/api/v1/company-news",
            params={"symbol": ticker.upper(), "from": str(frm), "to": str(to),
                    "token": FINNHUB_API_KEY},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        items = r.json()[:limit]
        return [
            {"headline": i.get("headline", ""), "source": i.get("source", ""),
             "summary": (i.get("summary") or "")[:300], "url": i.get("url", "")}
            for i in items
        ]
    except Exception:
        return _yahoo_rss(ticker, limit)


def _yahoo_rss(ticker: str, limit: int) -> List[Dict]:
    """Keyless fallback #1: yfinance's news feed, #2: Google News RSS."""
    try:
        import yfinance as yf
        items = yf.Ticker(ticker).news or []
        out = []
        for i in items[:limit]:
            c = i.get("content", i)  # new/old yfinance news shapes
            title = c.get("title", "")
            if not title:
                continue
            out.append({
                "headline": title,
                "source": (c.get("provider") or {}).get("displayName", "Yahoo Finance")
                if isinstance(c.get("provider"), dict) else "Yahoo Finance",
                "summary": (c.get("summary") or "")[:300],
                "url": (c.get("canonicalUrl") or {}).get("url", "")
                if isinstance(c.get("canonicalUrl"), dict) else c.get("link", ""),
            })
        if out:
            return out
    except Exception:
        pass
    return _google_news_rss(f"{ticker} stock", limit)


def _google_news_rss(query: str, limit: int) -> List[Dict]:
    """Keyless fallback #2: Google News RSS search."""
    import xml.etree.ElementTree as ET
    try:
        r = httpx.get(
            "https://news.google.com/rss/search",
            params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            timeout=_TIMEOUT, follow_redirects=True,
        )
        r.raise_for_status()
        root = ET.fromstring(r.text)
        out = []
        for item in root.iter("item"):
            out.append({
                "headline": item.findtext("title", ""),
                "source": (item.findtext("source") or "Google News"),
                "summary": "",
                "url": item.findtext("link", ""),
            })
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def general_market_news(limit: int = 8) -> List[Dict]:
    """Broad market headlines for the daily brief."""
    if FINNHUB_API_KEY:
        try:
            r = httpx.get(
                "https://finnhub.io/api/v1/news",
                params={"category": "general", "token": FINNHUB_API_KEY},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            return [
                {"headline": i.get("headline", ""), "source": i.get("source", ""),
                 "summary": (i.get("summary") or "")[:300], "url": i.get("url", "")}
                for i in r.json()[:limit]
            ]
        except Exception:
            pass
    # keyless fallback: broad market query
    return _google_news_rss("stock market today", limit)
