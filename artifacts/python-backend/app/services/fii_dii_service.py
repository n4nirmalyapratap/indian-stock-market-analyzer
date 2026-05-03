"""FII / DII flow data service.

Fetches the daily provisional FII / DII cash-market activity from NSE's
public endpoints and accumulates a rolling day-by-day history on disk.
Supports all 5 F&O segments using historical data chunking.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import pandas as pd
from app.services.nse_service import NseService
import threading

logger = logging.getLogger("fii_dii_service")

# nsearchives.nseindia.com publishes a daily participant-wise OI CSV for every
# trading day. URL pattern: /content/nsccl/fao_participant_oi_DDMMYYYY.csv
# This is the only public NSE source for historical F&O participant data;
# we fetch it via NseService so headers, UA and cache rules stay centralised.
_FNO_ARCHIVE_URL = "https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_{date}.csv"

# How "Long" and "Short" totals are constructed per segment from the CSV.
# Each tuple is (long_columns, short_columns) where columns are summed.
_FNO_SEGMENT_COLS = {
    "index_future": (["Future Index Long"], ["Future Index Short"]),
    "stock_future": (["Future Stock Long"], ["Future Stock Short"]),
    "index_option": (["Option Index Call Long",  "Option Index Put Long"],
                     ["Option Index Call Short", "Option Index Put Short"]),
    "stock_option": (["Option Stock Call Long",  "Option Stock Put Long"],
                     ["Option Stock Call Short", "Option Stock Put Short"]),
}

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "market_cache"
_DB_FILE = _CACHE_DIR / "fii_dii_cache.db"
_OLD_HISTORY_FILE = _CACHE_DIR / "fii_dii" / "history.json"

NSE_CHUNK_DAYS = 85

SEGMENT_MAP = {
    "equity":        None,
    "index_future":  "futIdx",
    "index_option":  "optIdx",
    "stock_future":  "futStk",
    "stock_option":  "optStk", # mapped to handle frontend naming
    "stock_options": "optStk", # fallback
}

_db_lock = threading.Lock()

def date_chunks(start: datetime, end: datetime, chunk_days: int = NSE_CHUNK_DAYS):
    current = start
    while current < end:
        chunk_end = min(current + timedelta(days=chunk_days), end)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)

def _f(row: dict, key: str) -> float:
    val = row.get(key, 0)
    if val is None or val == "":
        return 0.0
    if isinstance(val, str):
        val = val.replace(",", "").strip()
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def parse_equity_row(r: dict) -> dict:
    return {
        "date":      r.get("date"),
        "fii_buy":   _f(r, "buyValue")   or _f(r, "fiiBuyVal"),
        "fii_sell":  _f(r, "sellValue")  or _f(r, "fiiSellVal"),
        "fii_net":   _f(r, "netValue")   or _f(r, "fiiNetVal"),
        "dii_buy":   _f(r, "diiBuyVal"),
        "dii_sell":  _f(r, "diiSellVal"),
        "dii_net":   _f(r, "diiNetVal"),
    }

def parse_fno_row(r: dict, prefix: str) -> dict:
    long_  = _f(r, f"{prefix}FiiLong")
    short_ = _f(r, f"{prefix}FiiShort")
    d_long  = _f(r, f"{prefix}DiiLong")
    d_short = _f(r, f"{prefix}DiiShort")
    return {
        "date":              r.get("date"),
        "fii_long":          long_,
        "fii_short":         short_,
        "fii_net":           long_ - short_,
        "dii_long":          d_long,
        "dii_short":         d_short,
        "dii_net":           d_long - d_short,
        "client_long":       _f(r, f"{prefix}ClientLong"),
        "client_short":      _f(r, f"{prefix}ClientShort"),
        "pro_long":          _f(r, f"{prefix}ProLong"),
        "pro_short":         _f(r, f"{prefix}ProShort"),
    }

def save_to_db(df: pd.DataFrame, table: str):
    if df.empty: return
    os.makedirs(_CACHE_DIR, exist_ok=True)
    with _db_lock:
        with sqlite3.connect(_DB_FILE) as conn:
            df.to_sql(table, conn, if_exists="replace", index=False)

def load_from_db(table: str) -> pd.DataFrame | None:
    if not os.path.exists(_DB_FILE): return None
    with _db_lock:
        try:
            with sqlite3.connect(_DB_FILE) as conn:
                df = pd.read_sql(f"SELECT * FROM {table}", conn)
            # SQLite stores datetimes as ISO strings (YYYY-MM-DD HH:MM:SS).
            # Use ISO8601 strict parsing to avoid pandas' dayfirst heuristic
            # mis-interpreting unambiguous ISO strings.
            df["date"] = pd.to_datetime(df["date"], format="ISO8601")
            return df
        except Exception:
            return None

def get_cached_date_range(table: str):
    df = load_from_db(table)
    if df is None or df.empty: return None, None
    return df["date"].min(), df["date"].max()

def _load_old_json_history() -> pd.DataFrame:
    """Migrate the old single-day snapshot cache if it exists."""
    if not _OLD_HISTORY_FILE.exists():
        return pd.DataFrame()
    try:
        with open(_OLD_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = []
        for k, v in data.items():
            rows.append({
                "date": v.get("date"),
                "fii_buy": v.get("fiiBuy"),
                "fii_sell": v.get("fiiSell"),
                "fii_net": v.get("fiiNet"),
                "dii_buy": v.get("diiBuy"),
                "dii_sell": v.get("diiSell"),
                "dii_net": v.get("diiNet"),
            })
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True)
        return df
    except Exception:
        return pd.DataFrame()

class FiiDiiService:
    def __init__(self):
        self.nse = NseService()

    async def fetch_equity_snapshot(self) -> pd.DataFrame:
        """Fetch the latest day's snapshot from NSE's working public endpoint.
        Returns a one-row DataFrame (FII + DII merged) or empty if unavailable."""
        data = await self.nse.fetch_nse("/api/fiidiiTradeReact", "fii_dii_eq_snapshot", ttl=120)
        if not data or not isinstance(data, list):
            return pd.DataFrame()
        fii = next((r for r in data if isinstance(r, dict) and "FII" in (r.get("category") or "").upper()), {})
        dii = next((r for r in data if isinstance(r, dict) and "DII" in (r.get("category") or "").upper()), {})
        date_str = fii.get("date") or dii.get("date")
        if not date_str:
            return pd.DataFrame()
        row = {
            "date":     date_str,
            "fii_buy":  _f(fii, "buyValue"),
            "fii_sell": _f(fii, "sellValue"),
            "fii_net":  _f(fii, "netValue"),
            "dii_buy":  _f(dii, "buyValue"),
            "dii_sell": _f(dii, "sellValue"),
            "dii_net":  _f(dii, "netValue"),
        }
        df = pd.DataFrame([row])
        df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True)
        return df

    async def fetch_equity_historical(self, start: datetime, end: datetime) -> pd.DataFrame:
        all_rows = []
        for cs, ce in date_chunks(start, end):
            s = cs.strftime("%d-%m-%Y")
            e = ce.strftime("%d-%m-%Y")
            url  = f"/api/historical/fiidii?startDate={s}&endDate={e}"
            cache_key = f"hist_eq_{s}_{e}"
            data = await self.nse.fetch_nse(url, cache_key, ttl=300)
            if data:
                rows = data.get("data", data) if isinstance(data, dict) else data
                if isinstance(rows, list):
                    all_rows.extend([parse_equity_row(r) for r in rows if isinstance(r, dict)])
            # Politeness delay inside async loop
            await asyncio.sleep(0.5)

        df = pd.DataFrame(all_rows)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True)
            df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
            return df

        # NSE's bulk historical endpoint is not publicly exposed — fall back
        # to the daily snapshot which always works. The cache then accumulates
        # one new row per trading day over time (and is committed to GitHub).
        snap = await self.fetch_equity_snapshot()
        if not snap.empty:
            snap_date = snap["date"].iloc[0]
            if pd.Timestamp(start) <= snap_date <= pd.Timestamp(end):
                return snap
        return pd.DataFrame()

    async def fetch_fno_historical(self, segment: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Fetch one historical row per trading day for the given F&O segment by
        downloading NSE's daily participant-wise OI archive
        (nsearchives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv).

        Weekends and holidays return 404 from the archive — we skip them
        silently. Concurrency is capped to be polite to the static host."""
        if segment not in _FNO_SEGMENT_COLS:
            return pd.DataFrame()

        days = []
        cur = start.date()
        end_d = end.date()
        while cur <= end_d:
            # Skip Sat (5) / Sun (6) — NSE never publishes on weekends.
            if cur.weekday() < 5:
                days.append(cur)
            cur += timedelta(days=1)

        sem = asyncio.Semaphore(4)
        all_per_segment: dict[str, list[dict]] = {seg: [] for seg in _FNO_SEGMENT_COLS}

        async def _one(d):
            async with sem:
                rows = await self._fetch_fno_archive_day(d)
                for seg, row in rows.items():
                    all_per_segment[seg].append(row)

        # Run all days; failures are absorbed inside _fetch_fno_archive_day.
        await asyncio.gather(*[_one(d) for d in days], return_exceptions=True)

        # Persist EVERY segment we fetched (not just the requested one) so the
        # cache fills up in a single pass instead of needing 4 separate runs.
        loop = asyncio.get_running_loop()
        for seg, rows in all_per_segment.items():
            if not rows:
                continue
            seg_df = pd.DataFrame(rows)
            # The rows have ISO YYYY-MM-DD date strings we built ourselves —
            # parse strictly with format=ISO8601 to avoid pandas mis-applying
            # dayfirst heuristics on ambiguous numerics like "2026-03-12".
            seg_df["date"] = pd.to_datetime(seg_df["date"], format="ISO8601")
            seg_df = seg_df.sort_values("date").drop_duplicates("date").reset_index(drop=True)

            # Merge with existing cached rows so we don't overwrite older data.
            existing = await loop.run_in_executor(None, load_from_db, f"fii_dii_{seg}")
            if existing is not None and not existing.empty:
                seg_df = pd.concat([existing, seg_df], ignore_index=True)
                seg_df["date"] = pd.to_datetime(seg_df["date"])
                seg_df = seg_df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
            await loop.run_in_executor(None, save_to_db, seg_df, f"fii_dii_{seg}")

        # Return just the requested segment's frame.
        rows = all_per_segment.get(segment, [])
        df = pd.DataFrame(rows)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], format="ISO8601")
            df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
        return df

    async def _fetch_fno_archive_day(self, day) -> dict[str, dict]:
        """Download and parse one day's fao_participant_oi CSV. Returns
        a dict {segment_name: row_dict} for all 4 F&O segments. Empty dict
        on weekend/holiday/error.

        Routed through NseService.fetch_nse_archive_text so we share its
        in-process cache and header discipline rather than spinning up an
        ad-hoc httpx client here."""
        date_str = day.strftime("%d%m%Y")
        url = _FNO_ARCHIVE_URL.format(date=date_str)
        cache_key = f"fno_oi_{date_str}"
        try:
            text = await self.nse.fetch_nse_archive_text(url, cache_key, ttl=86400)
            if not text or len(text) < 50:
                return {}
            text = text.strip()
            # Header line is wrapped in stray quotes; skip it and parse the rest.
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if len(lines) < 3:
                return {}
            reader = csv.reader(io.StringIO("\n".join(lines[1:])))
            rows = list(reader)
            if not rows:
                return {}
            header = [h.strip() for h in rows[0]]
            data_rows = {r[0].strip(): r for r in rows[1:] if r and r[0].strip()}
            fii_row = data_rows.get("FII") or data_rows.get("FPI")
            dii_row = data_rows.get("DII")
            client_row = data_rows.get("Client") or data_rows.get("CLIENT")
            pro_row = data_rows.get("Pro") or data_rows.get("PRO")
            if not fii_row and not dii_row:
                return {}

            def _val(row, col):
                if not row:
                    return 0.0
                try:
                    idx = header.index(col)
                except ValueError:
                    return 0.0
                if idx >= len(row):
                    return 0.0
                v = row[idx].strip().replace(",", "")
                try:
                    return float(v) if v else 0.0
                except ValueError:
                    return 0.0

            def _sum(row, cols):
                return sum(_val(row, c) for c in cols)

            iso_date = day.strftime("%Y-%m-%d")
            out: dict[str, dict] = {}
            for seg, (long_cols, short_cols) in _FNO_SEGMENT_COLS.items():
                fii_long  = _sum(fii_row, long_cols)
                fii_short = _sum(fii_row, short_cols)
                dii_long  = _sum(dii_row, long_cols)
                dii_short = _sum(dii_row, short_cols)
                out[seg] = {
                    "date":         iso_date,
                    "fii_long":     fii_long,
                    "fii_short":    fii_short,
                    "fii_net":      fii_long - fii_short,
                    "dii_long":     dii_long,
                    "dii_short":    dii_short,
                    "dii_net":      dii_long - dii_short,
                    "client_long":  _sum(client_row, long_cols),
                    "client_short": _sum(client_row, short_cols),
                    "pro_long":     _sum(pro_row, long_cols),
                    "pro_short":    _sum(pro_row, short_cols),
                }
            return out
        except Exception as e:
            logger.debug("fao archive fetch failed for %s: %s", date_str, e)
            return {}

    async def get_historical(self, segment: str, start: datetime, end: datetime) -> pd.DataFrame:
        table = f"fii_dii_{segment}"
        loop = asyncio.get_running_loop()
        
        cached_min, cached_max = await loop.run_in_executor(None, get_cached_date_range, table)
        
        # Migrate old JSON if cache is empty for equity
        cached_df = None
        if segment == "equity" and not cached_min:
            cached_df = await loop.run_in_executor(None, _load_old_json_history)
            if cached_df is not None and not cached_df.empty:
                cached_min = cached_df["date"].min()
                cached_max = cached_df["date"].max()
        else:
            cached_df = await loop.run_in_executor(None, load_from_db, table)

        if cached_min and cached_max and cached_df is not None and not cached_df.empty:
            fetch_ranges = []
            if start < cached_min:
                fetch_ranges.append((start, cached_min - timedelta(days=1)))
            if end > cached_max:
                fetch_ranges.append((cached_max + timedelta(days=1), end))

            if not fetch_ranges:
                return cached_df[(cached_df["date"] >= pd.Timestamp(start)) & (cached_df["date"] <= pd.Timestamp(end))]

            new_dfs = []
            for rs, re in fetch_ranges:
                if segment == "equity":
                    ndf = await self.fetch_equity_historical(rs, re)
                else:
                    ndf = await self.fetch_fno_historical(segment, rs, re)
                if not ndf.empty:
                    new_dfs.append(ndf)

            valid_dfs = [cached_df] + new_dfs
            combined = pd.concat(valid_dfs, ignore_index=True)
            combined["date"] = pd.to_datetime(combined["date"])
            combined = combined.sort_values("date").drop_duplicates("date").reset_index(drop=True)
            await loop.run_in_executor(None, save_to_db, combined, table)
            return combined[(combined["date"] >= pd.Timestamp(start)) & (combined["date"] <= pd.Timestamp(end))]

        # Fresh fetch
        if segment == "equity":
            df = await self.fetch_equity_historical(start, end)
        else:
            df = await self.fetch_fno_historical(segment, start, end)

        if not df.empty:
            await loop.run_in_executor(None, save_to_db, df, table)
        return df

    async def get_flows(self, segment: str, days: int = 365) -> dict:
        end_date = datetime.today()
        start_date = end_date - timedelta(days=days)
        
        try:
            df = await self.get_historical(segment, start_date, end_date)
        except Exception as e:
            return self._empty_response(segment, f"Failed to fetch data: {e}")

        if df is None or df.empty:
            if segment == "equity":
                msg = "NSE returned no FII/DII activity for this range. Please try again after the next session close."
            else:
                msg = ("NSE does not currently expose its F&O participant history through "
                       "its public API. The dashboard will record one row per trading day "
                       "as it becomes available; equity flows are tracked in full.")
            return self._empty_response(segment, msg)

        df = df.sort_values("date", ascending=False)
        rows = []
        for _, row in df.iterrows():
            d = row["date"]
            if pd.isna(d): continue
            
            if segment == "equity":
                r = {
                    "date": d.strftime("%Y-%m-%d"),
                    "displayDate": d.strftime("%d-%b-%Y"),
                    "fiiBuy": row.get("fii_buy"),
                    "fiiSell": row.get("fii_sell"),
                    "fiiNet": row.get("fii_net"),
                    "diiBuy": row.get("dii_buy"),
                    "diiSell": row.get("dii_sell"),
                    "diiNet": row.get("dii_net"),
                }
            else:
                r = {
                    "date": d.strftime("%Y-%m-%d"),
                    "displayDate": d.strftime("%d-%b-%Y"),
                    "fiiBuy": row.get("fii_long"),
                    "fiiSell": row.get("fii_short"),
                    "fiiNet": row.get("fii_net"),
                    "diiBuy": row.get("dii_long"),
                    "diiSell": row.get("dii_short"),
                    "diiNet": row.get("dii_net"),
                }
            rows.append(r)

        latest = rows[0] if rows else None

        def _summary(n: int):
            """Trailing-N-sessions aggregate (most recent first)."""
            if not rows:
                return {"fiiNet": None, "diiNet": None, "label": None, "days": 0, "expectedDays": n, "isPartial": True}
            sl = rows[:n]
            fii = sum((r.get("fiiNet") or 0.0) for r in sl)
            dii = sum((r.get("diiNet") or 0.0) for r in sl)
            label = sl[-1].get("displayDate") if sl else None
            return {
                "fiiNet": round(fii, 2),
                "diiNet": round(dii, 2),
                "label": label,
                "days": len(sl),
                "expectedDays": n,
                "isPartial": len(sl) < n,
            }

        def _ytd_summary():
            """True calendar YTD — all rows from Jan 1 of the current year onward."""
            if not rows:
                return {"fiiNet": None, "diiNet": None, "label": None, "days": 0, "expectedDays": 0, "isPartial": True, "yearStart": None}
            year = datetime.today().year
            jan1 = f"{year}-01-01"
            ytd_rows = [r for r in rows if (r.get("date") or "") >= jan1]
            fii = sum((r.get("fiiNet") or 0.0) for r in ytd_rows)
            dii = sum((r.get("diiNet") or 0.0) for r in ytd_rows)
            label = ytd_rows[-1].get("displayDate") if ytd_rows else None
            return {
                "fiiNet": round(fii, 2),
                "diiNet": round(dii, 2),
                "label": label,
                "days": len(ytd_rows),
                "expectedDays": len(ytd_rows),
                "isPartial": False,
                "yearStart": jan1,
            }

        # Group rows into calendar months (most recent first)
        monthly = self._group_by_month(rows)

        return {
            "available": True,
            "segment": segment,
            "source": "NSE India",
            "sourceUrl": "https://www.nseindia.com/reports/fii-dii" if segment == "equity" else "https://www.nseindia.com/all-reports-derivatives",
            "latest": latest,
            "rows": rows,
            "summary": {
                "daily":   _summary(1),
                "weekly":  _summary(5),
                # Hero card "Last 30 Sessions" — exact 30 trailing trading days.
                "monthly": _summary(30),
                # True calendar YTD aggregate (Jan 1 → today), not trailing 252.
                "ytd":     _ytd_summary(),
            },
            "monthly": monthly,
            "totalDays": len(rows),
            "rangeDays": days,
        }

    @staticmethod
    def _group_by_month(rows: list[dict]) -> list[dict]:
        """Group descending-date rows into per-calendar-month buckets.
        Each bucket: { key: 'YYYY-MM', label: 'April 2026', fiiNet, diiNet,
        greenDays, redDays, days, rows: [...descending] }."""
        buckets: dict[str, dict] = {}
        order: list[str] = []
        for r in rows:
            d = r.get("date") or ""
            if len(d) < 7:
                continue
            key = d[:7]  # YYYY-MM
            if key not in buckets:
                try:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    label = dt.strftime("%B %Y")
                except Exception:
                    label = key
                buckets[key] = {
                    "key": key,
                    "label": label,
                    "fiiNet": 0.0,
                    "diiNet": 0.0,
                    "greenDays": 0,
                    "redDays": 0,
                    "days": 0,
                    "rows": [],
                }
                order.append(key)
            b = buckets[key]
            fii = r.get("fiiNet") or 0.0
            dii = r.get("diiNet") or 0.0
            b["fiiNet"] += fii
            b["diiNet"] += dii
            b["days"] += 1
            # Use combined FII+DII flow direction for green/red day classification
            net = fii + dii
            if net > 0:
                b["greenDays"] += 1
            elif net < 0:
                b["redDays"] += 1
            b["rows"].append(r)
        # Round to 2 decimals
        for k in order:
            buckets[k]["fiiNet"] = round(buckets[k]["fiiNet"], 2)
            buckets[k]["diiNet"] = round(buckets[k]["diiNet"], 2)
        return [buckets[k] for k in order]

    async def backfill_all(self, days: int = 400) -> dict:
        """One-shot backfill of every supported segment into the local SQLite cache.
        Returns a summary dict with row counts per segment so the caller can
        confirm the cache file is ready to commit."""
        end_date = datetime.today()
        start_date = end_date - timedelta(days=days)
        results = {}
        for seg in ("equity", "index_future", "index_option", "stock_future", "stock_option"):
            try:
                df = await self.get_historical(seg, start_date, end_date)
                results[seg] = {
                    "rows": int(0 if df is None or df.empty else len(df)),
                    "ok": True,
                }
            except Exception as e:
                results[seg] = {"rows": 0, "ok": False, "error": str(e)}
        return {
            "ok": True,
            "days": days,
            "from": start_date.strftime("%Y-%m-%d"),
            "to":   end_date.strftime("%Y-%m-%d"),
            "segments": results,
            "cacheFile": str(_DB_FILE),
        }

    def _empty_response(self, segment: str, message: str) -> dict:
        return {
            "available": False,
            "segment": segment,
            "source": "NSE India",
            "sourceUrl": "https://www.nseindia.com/reports/fii-dii" if segment == "equity" else "https://www.nseindia.com/all-reports-derivatives",
            "rows": [],
            "summary": {"daily": {}, "weekly": {}, "monthly": {}, "ytd": {}},
            "monthly": [],
            "totalDays": 0,
            "rangeDays": 0,
            "message": message
        }
