"""Google Sheets intelligence — paste a link, get analysis. Works keyless
for any link-shared sheet via the CSV export endpoint."""
import io
import re
from typing import Optional, Tuple

import httpx
import pandas as pd

SHEET_URL_RE = re.compile(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)")
GID_RE = re.compile(r"[#&?]gid=(\d+)")


def extract_sheet_id(text: str) -> Optional[Tuple[str, str]]:
    """Return (sheet_id, gid) if the text contains a Google Sheets link."""
    m = SHEET_URL_RE.search(text)
    if not m:
        return None
    gid_m = GID_RE.search(text)
    return m.group(1), (gid_m.group(1) if gid_m else "0")


def fetch_sheet_as_text(sheet_id: str, gid: str = "0") -> Tuple[bool, str]:
    """Download sheet as CSV and return an LLM-friendly text representation.
    Returns (ok, text_or_error)."""
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        if r.status_code != 200 or "text/html" in r.headers.get("content-type", ""):
            return False, (
                "I couldn't open that sheet — it looks private. "
                "Set it to 'Anyone with the link can view' and send it again."
            )
        df = pd.read_csv(io.StringIO(r.text))
    except Exception:
        return False, "I couldn't read that sheet. Is the link correct and shared?"

    if df.empty:
        return False, "The sheet appears to be empty."

    lines = [f"Google Sheet — {len(df)} rows x {len(df.columns)} columns",
             f"Columns: {', '.join(str(c) for c in df.columns)}", ""]

    # numeric column stats give the model instant analytical grounding
    numeric = df.select_dtypes("number")
    if not numeric.empty:
        lines.append("Numeric column stats (sum / mean / min / max):")
        for col in numeric.columns:
            s = numeric[col]
            lines.append(f"  {col}: {s.sum():,.2f} / {s.mean():,.2f} / {s.min():,.2f} / {s.max():,.2f}")
        lines.append("")

    # cap raw data to stay inside context limits
    max_rows = 150
    lines.append(f"Data (first {min(max_rows, len(df))} rows, CSV):")
    lines.append(df.head(max_rows).to_csv(index=False))
    if len(df) > max_rows:
        lines.append(f"... ({len(df) - max_rows} more rows truncated)")

    return True, "\n".join(lines)
