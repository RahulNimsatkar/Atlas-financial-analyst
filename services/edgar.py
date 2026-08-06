"""SEC EDGAR — free, keyless. Ticker → CIK → recent filings."""
from typing import Dict, List, Optional

import httpx

from config import EDGAR_USER_AGENT

_HEADERS = {"User-Agent": EDGAR_USER_AGENT}
_TIMEOUT = 15
_cik_cache: Dict[str, str] = {}


def _ticker_to_cik(ticker: str) -> Optional[str]:
    ticker = ticker.upper()
    if ticker in _cik_cache:
        return _cik_cache[ticker]
    try:
        r = httpx.get("https://www.sec.gov/files/company_tickers.json",
                      headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        for row in r.json().values():
            _cik_cache[row["ticker"].upper()] = str(row["cik_str"]).zfill(10)
        return _cik_cache.get(ticker)
    except Exception:
        return None


def recent_filings(ticker: str, limit: int = 6) -> List[Dict]:
    """Latest filings: [{form, date, accession, description, url}]"""
    cik = _ticker_to_cik(ticker)
    if not cik:
        return []
    try:
        r = httpx.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                      headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        recent = r.json().get("filings", {}).get("recent", {})
        out = []
        for i in range(min(limit, len(recent.get("form", [])))):
            acc = recent["accessionNumber"][i]
            acc_clean = acc.replace("-", "")
            out.append({
                "form": recent["form"][i],
                "date": recent["filingDate"][i],
                "accession": acc,
                "description": recent.get("primaryDocDescription", [""] * limit)[i] or recent["form"][i],
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{recent['primaryDocument'][i]}",
            })
        return out
    except Exception:
        return []


def latest_filing_accession(ticker: str) -> str:
    """For the filing-tracker poller: newest accession number, '' if unknown."""
    filings = recent_filings(ticker, limit=1)
    return filings[0]["accession"] if filings else ""
