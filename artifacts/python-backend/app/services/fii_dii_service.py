"""FII / DII flow data service.

Fetches the daily provisional FII / DII cash-market activity from NSE's
public endpoints and accumulates a rolling day-by-day history on disk.
Supports all 5 F&O segments using historical data chunking.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import pandas as pd
from app.services.nse_service import NseService
import threading

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
            df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True)
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

    async def fetch_fno_historical(self, segment: str, start: datetime, end: datetime) -> pd.DataFrame:
        prefix = SEGMENT_MAP.get(segment)
        if not prefix: return pd.DataFrame()
        all_rows = []
        for cs, ce in date_chunks(start, end):
            s = cs.strftime("%d-%m-%Y")
            e = ce.strftime("%d-%m-%Y")
            url  = f"/api/historical/fnoparticipants?startDate={s}&endDate={e}"
            cache_key = f"hist_fno_{s}_{e}"
            data = await self.nse.fetch_nse(url, cache_key, ttl=300)
            if data:
                rows = data.get("data", data) if isinstance(data, dict) else data
                if isinstance(rows, list):
                    all_rows.extend([parse_fno_row(r, prefix) for r in rows if isinstance(r, dict)])
            await asyncio.sleep(0.5)
            
        df = pd.DataFrame(all_rows)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True)
            df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
        return df

    async def get_historical(self, segment: str, start: datetime, end: datetime) -> pd.DataFrame:
        table = f"fii_dii_{segment}"
        loop = asyncio.get_event_loop()
        
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
            return self._empty_response(segment, "No data available for this segment.")

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
                "monthly": _summary(22),
                "ytd":     _summary(min(252, len(rows))),
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
