"""Market data — quotes via direct HTTP, fundamentals/history via yfinance. No API key."""
from typing import Dict, List

import httpx
import yfinance as yf

MAJOR_INDICES = {"^GSPC": "S&P 500", "^IXIC": "Nasdaq", "^DJI": "Dow Jones"}

_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _fmt_big(n) -> str:
    if n is None:
        return "n/a"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "n/a"
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(n) >= div:
            return f"{n / div:.2f}{unit}"
    return f"{n:,.0f}"


def get_quote(ticker: str) -> Dict:
    """Current price + day change via direct Yahoo Finance HTTP call (no pandas/numpy)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
    resp = httpx.get(url, headers=_YAHOO_HEADERS, timeout=10)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice")
    prev = meta.get("previousClose") or meta.get("chartPreviousClose")
    change_pct = ((price - prev) / prev * 100) if (price and prev) else 0.0
    return {
        "ticker": ticker.upper(),
        "price": round(price, 2) if price else None,
        "prev_close": round(prev, 2) if prev else None,
        "change_pct": round(change_pct, 2),
        "currency": meta.get("currency", "USD"),
    }


def get_fundamentals(ticker: str) -> Dict:
    """Key fundamentals used for company profiles and comparisons."""
    t = yf.Ticker(ticker)
    i = t.info or {}
    return {
        "ticker": ticker.upper(),
        "name": i.get("longName") or i.get("shortName") or ticker.upper(),
        "sector": i.get("sector", "n/a"),
        "industry": i.get("industry", "n/a"),
        "market_cap": _fmt_big(i.get("marketCap")),
        "pe_trailing": i.get("trailingPE"),
        "pe_forward": i.get("forwardPE"),
        "peg": i.get("pegRatio"),
        "price_to_sales": i.get("priceToSalesTrailing12Months"),
        "revenue_ttm": _fmt_big(i.get("totalRevenue")),
        "revenue_growth_pct": round(i["revenueGrowth"] * 100, 1) if i.get("revenueGrowth") else None,
        "gross_margin_pct": round(i["grossMargins"] * 100, 1) if i.get("grossMargins") else None,
        "operating_margin_pct": round(i["operatingMargins"] * 100, 1) if i.get("operatingMargins") else None,
        "profit_margin_pct": round(i["profitMargins"] * 100, 1) if i.get("profitMargins") else None,
        "free_cash_flow": _fmt_big(i.get("freeCashflow")),
        "debt_to_equity": i.get("debtToEquity"),
        "dividend_yield_pct": round(i["dividendYield"] * 100, 2) if i.get("dividendYield") else None,
        "beta": i.get("beta"),
        "52w_high": i.get("fiftyTwoWeekHigh"),
        "52w_low": i.get("fiftyTwoWeekLow"),
        "analyst_target": i.get("targetMeanPrice"),
        "recommendation": i.get("recommendationKey", "n/a"),
        "summary": (i.get("longBusinessSummary") or "")[:600],
    }


def get_price_history(ticker: str, period: str = "1mo") -> str:
    """Compact OHLC summary for trend questions."""
    t = yf.Ticker(ticker)
    hist = t.history(period=period)
    if hist.empty:
        return f"No history found for {ticker}."
    first, last = hist["Close"].iloc[0], hist["Close"].iloc[-1]
    change = (last - first) / first * 100
    return (
        f"{ticker.upper()} {period}: start {first:.2f}, end {last:.2f} "
        f"({change:+.1f}%), high {hist['High'].max():.2f}, low {hist['Low'].min():.2f}"
    )


def get_earnings_info(ticker: str) -> Dict:
    """Next earnings date + last quarterly results."""
    t = yf.Ticker(ticker)
    out: Dict = {"ticker": ticker.upper(), "next_earnings": None, "recent_quarters": []}
    try:
        cal = t.calendar
        dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if dates:
            out["next_earnings"] = str(dates[0])
    except Exception:
        pass
    try:
        inc = t.quarterly_income_stmt
        if inc is not None and not inc.empty:
            for col in list(inc.columns)[:2]:
                q = {"quarter": str(col.date())}
                if "Total Revenue" in inc.index:
                    q["revenue"] = _fmt_big(inc.loc["Total Revenue", col])
                if "Net Income" in inc.index:
                    q["net_income"] = _fmt_big(inc.loc["Net Income", col])
                out["recent_quarters"].append(q)
    except Exception:
        pass
    return out


def market_overview() -> List[Dict]:
    """Snapshot of major indices for briefings / 'how's the market' questions."""
    out = []
    for symbol, name in MAJOR_INDICES.items():
        try:
            q = get_quote(symbol)
            q["name"] = name
            out.append(q)
        except Exception:
            continue
    return out
