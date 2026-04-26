"""FII / DII flow data service.

Fetches the daily provisional FII / DII cash-market activity from NSE's
public JSON endpoint (``/api/fiidiiTradeReact``) and accumulates a rolling
day-by-day history on disk so charts and tables can render a real series
without a paid data feed.

The endpoint returns *only today's* snapshot, so we maintain a small JSON
cache file (``market_cache/fii_dii/history.json``) keyed by trading date,
appending each new snapshot as we see it. After running for a few weeks
this gives the dashboard a real 30-day series.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.nse_service import NseService

# Serialises the read-modify-write of history.json across concurrent
# requests in this worker process. (For multi-worker deployments a real
# file lock would be needed, but uvicorn runs single-worker by default.)
_HISTORY_LOCK = asyncio.Lock()

# Where rolling history lives. Survives restarts in the workspace volume.
_HISTORY_DIR = Path(__file__).resolve().parent.parent.parent / "market_cache" / "fii_dii"
_HISTORY_FILE = _HISTORY_DIR / "history.json"
_MAX_HISTORY_DAYS = 365  # keep ~1y of daily snapshots

_NSE_DATE_FMT = "%d-%b-%Y"   # e.g. "24-Apr-2026"
_ISO_DATE_FMT = "%Y-%m-%d"


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _normalise_date(s: str) -> str:
    """Convert NSE's ``24-Apr-2026`` → ISO ``2026-04-24``. Best-effort."""
    if not s:
        return ""
    try:
        return datetime.strptime(s.strip(), _NSE_DATE_FMT).strftime(_ISO_DATE_FMT)
    except ValueError:
        return s


def _parse_snapshot(raw: list[dict]) -> dict | None:
    """Convert NSE's two-row response into a single-row daily snapshot.

    Input:
        [{"category":"DII","date":"24-Apr-2026","buyValue":"21560.16",...},
         {"category":"FII/FPI","date":"24-Apr-2026","buyValue":"9837.2",...}]
    """
    if not isinstance(raw, list) or not raw:
        return None
    # Defend against malformed entries (e.g. None or strings sneaking in).
    rows = [r for r in raw if isinstance(r, dict)]
    fii_row = next((r for r in rows if "FII" in str(r.get("category", "")).upper()), None)
    dii_row = next((r for r in rows if "DII" in str(r.get("category", "")).upper()), None)
    if not fii_row and not dii_row:
        return None
    raw_date = (fii_row or dii_row).get("date") or ""
    return {
        "date": _normalise_date(raw_date),
        "displayDate": raw_date,
        "fiiBuy":  _to_float((fii_row or {}).get("buyValue")),
        "fiiSell": _to_float((fii_row or {}).get("sellValue")),
        "fiiNet":  _to_float((fii_row or {}).get("netValue")),
        "diiBuy":  _to_float((dii_row or {}).get("buyValue")),
        "diiSell": _to_float((dii_row or {}).get("sellValue")),
        "diiNet":  _to_float((dii_row or {}).get("netValue")),
    }


def _load_history() -> dict[str, dict]:
    """Load the rolling history. Keyed by ISO date."""
    if not _HISTORY_FILE.exists():
        return {}
    try:
        with _HISTORY_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_history(history: dict[str, dict]) -> None:
    try:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        # Atomic-ish write: write to .tmp then rename.
        tmp = _HISTORY_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(history, f, separators=(",", ":"))
        os.replace(tmp, _HISTORY_FILE)
    except OSError:
        pass  # cache failures are non-fatal


def _ingest(snapshot: dict, history: dict[str, dict]) -> dict[str, dict]:
    """Insert today's snapshot into history; trim to last ``_MAX_HISTORY_DAYS``."""
    if not snapshot or not snapshot.get("date"):
        return history
    history[snapshot["date"]] = snapshot
    # Trim by date (string sort works for ISO dates).
    if len(history) > _MAX_HISTORY_DAYS:
        for k in sorted(history.keys())[: len(history) - _MAX_HISTORY_DAYS]:
            history.pop(k, None)
    return history


def _summary(rows: list[dict], n: int) -> dict:
    """Aggregate the latest ``n`` rows for a ``Daily/Weekly/Monthly`` card.

    ``isPartial`` is true when our local cache has fewer than ``n`` days yet,
    so the UI can disclose that the figure is over a shorter window than the
    label suggests (e.g. "Monthly" with only 2 days of history)."""
    if not rows:
        return {"fiiNet": None, "diiNet": None, "label": None,
                "days": 0, "expectedDays": n, "isPartial": True}
    sl = rows[:n]  # rows are descending by date
    fii = sum((r.get("fiiNet") or 0.0) for r in sl)
    dii = sum((r.get("diiNet") or 0.0) for r in sl)
    label = sl[-1].get("displayDate") if sl else None  # earliest date in window
    return {
        "fiiNet": round(fii, 2),
        "diiNet": round(dii, 2),
        "label": label,
        "days": len(sl),
        "expectedDays": n,
        "isPartial": len(sl) < n,
    }


_NSE_BLOCKED_MSG = (
    "NSE blocked this request. Try again in a moment or check the source link."
)


class FiiDiiService:
    """Front-door for the FII/DII flow data."""

    def __init__(self) -> None:
        self.nse = NseService()

    async def get_equity_flows(self) -> dict:
        """Return today's snapshot, the rolling history, and three summary
        cards (Daily / Weekly / Monthly) — all from real NSE data."""
        # Cache the upstream call lightly. Refreshes every 10 min.
        raw = await self.nse.fetch_nse(
            "/api/fiidiiTradeReact", "fii-dii-equity-today", ttl=600,
        )
        today = _parse_snapshot(raw) if raw else None

        # Serialise the read-modify-write so concurrent requests don't
        # clobber each other's writes to history.json.
        async with _HISTORY_LOCK:
            history = _load_history()
            if today:
                history = _ingest(today, history)
                _save_history(history)

        rows_desc = sorted(history.values(), key=lambda r: r.get("date") or "", reverse=True)
        latest = rows_desc[0] if rows_desc else None
        return {
            "available": bool(rows_desc),
            "segment": "equity",
            "source": "NSE India",
            "sourceUrl": "https://www.nseindia.com/reports/fii-dii",
            "latest": latest,
            "rows": rows_desc,           # latest first
            "summary": {
                "daily":   _summary(rows_desc, 1),
                "weekly":  _summary(rows_desc, 5),    # 5 trading days
                "monthly": _summary(rows_desc, 22),   # ~22 trading days
            },
            "message": (
                None if rows_desc else
                "Today's snapshot wasn't returned by NSE and we don't have any cached "
                "history yet. Try again in a few minutes."
            ),
        }

    async def get_derivatives_flows(self, segment: str) -> dict:
        """F&O participant data lives at a different NSE endpoint that
        currently returns 404 from cloud IPs. Surface that cleanly until
        we wire in an alternative source."""
        return {
            "available": False,
            "segment": segment,
            "source": "NSE India (FAO participant report)",
            "sourceUrl": "https://www.nseindia.com/all-reports-derivatives",
            "rows": [],
            "summary": {"daily": {}, "weekly": {}, "monthly": {}},
            "message": (
                "F&O participant flows for this segment require the NSE "
                "FAO-Participant-Wise Trading report, which isn't accessible "
                "from this hosting region. The Equity tab uses live NSE data."
            ),
        }
