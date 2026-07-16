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

# In-process guard: tracks which segments have a background refresh flying.
# asyncio.create_task() re-uses the same event loop, so a plain set is safe.
_refresh_in_progress: set[str] = set()

# Per-segment retry state for today's data fetch.
#
# Logic:
#   - Up to MAX_TODAY_RETRIES attempts are fired, spaced _RETRY_INTERVAL_S apart.
#   - After MAX_TODAY_RETRIES consecutive failures the segment enters a
#     _REFRESH_COOLDOWN_S (30-minute) cooldown.  After that cooldown expires the
#     retry counter resets and a fresh 5-attempt cycle begins.
#   - A force-refresh (user clicks Retry) resets both counters immediately.
_refresh_last_failed: dict[str, float] = {}
_refresh_fail_count: dict[str, int] = {}

MAX_TODAY_RETRIES = 5          # attempts before entering long cooldown
_RETRY_INTERVAL_S = 60        # seconds between individual retry attempts
_REFRESH_COOLDOWN_S = 30 * 60  # 30-minute cooldown after all retries exhausted


def reset_today_fetch(segment: str) -> None:
    """Reset the per-segment retry counter and cooldown (force-refresh path).
    Called when the user explicitly requests a retry from the UI."""
    _refresh_fail_count.pop(segment, None)
    _refresh_last_failed.pop(segment, None)
    logger.info("Today-fetch state reset (force) — segment=%s", segment)

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

# ── Persistence: PostgreSQL ──────────────────────────────────────────────────
#
# Replaces the prior SQLite cache (market_cache/fii_dii_cache.db) which lived
# in a non-persistent Docker volume and was wiped on every container restart.
# All FII/DII history now lives in `fii_dii_history` keyed by (segment, date)
# so the data survives restarts and a scheduler can keep it fresh
# independently of anyone opening the page.

# Columns that exist on the unified history table. Keep aligned with the
# CREATE TABLE in auth_store.ensure_primary_schema.
_PG_COLS = (
    "segment", "date",
    "fii_buy", "fii_sell", "fii_net",
    "dii_buy", "dii_sell", "dii_net",
    "fii_long", "fii_short",
    "dii_long", "dii_short",
    "client_long", "client_short",
    "pro_long", "pro_short",
)
_PG_FLOW_COLS = _PG_COLS[2:]  # everything except segment + date


def _now_ms() -> int:
    import time as _time  # noqa: PLC0415
    return int(_time.time() * 1000)


def _segment_to_table_name(table: str) -> str:
    """Back-compat helper — old code called load_from_db('fii_dii_equity').
    Strip the prefix so we can pass the bare segment name through."""
    if table.startswith("fii_dii_"):
        return table[len("fii_dii_"):]
    return table


def _row_to_pg_params(segment: str, row: dict, now_ms: int) -> tuple:
    """Convert a parsed flow row dict into the positional tuple expected
    by the UPSERT statement, normalising missing fields to None."""
    return (
        segment,
        row.get("date"),
        row.get("fii_buy"),  row.get("fii_sell"), row.get("fii_net"),
        row.get("dii_buy"),  row.get("dii_sell"), row.get("dii_net"),
        row.get("fii_long"), row.get("fii_short"),
        row.get("dii_long"), row.get("dii_short"),
        row.get("client_long"), row.get("client_short"),
        row.get("pro_long"), row.get("pro_short"),
        now_ms,  # created_at_ms (used only on INSERT)
        now_ms,  # updated_at_ms (refreshed on every UPSERT)
    )


def _pg_upsert_rows(segment: str, df: pd.DataFrame) -> int:
    """Upsert a DataFrame of rows into fii_dii_history.

    Each row is keyed by (segment, date). Conflicts UPDATE non-key fields,
    so re-fetching a day's data overwrites placeholders or corrected values
    without inserting duplicates. Returns number of rows written.
    """
    if df is None or df.empty:
        return 0
    from app.lib.auth_store import ensure_primary_schema, get_conn  # noqa: PLC0415
    ensure_primary_schema()

    # Normalise date to a Python date object so psycopg can bind it directly.
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"]).dt.date
    now_ms = _now_ms()

    # Materialise the param tuples first so the cursor.executemany() call
    # below sees a uniform shape and any per-row conversion exception
    # surfaces before we open the connection.
    params: list[tuple] = []
    for r in work.to_dict(orient="records"):
        params.append(_row_to_pg_params(segment, r, now_ms))

    if not params:
        return 0

    cols_sql = ", ".join(_PG_COLS) + ", created_at_ms, updated_at_ms"
    placeholders = ", ".join(["%s"] * (len(_PG_COLS) + 2))
    update_sql = ", ".join(f"{c} = EXCLUDED.{c}" for c in _PG_FLOW_COLS)

    sql = (
        f"INSERT INTO fii_dii_history ({cols_sql}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT (segment, date) DO UPDATE SET "
        f"{update_sql}, updated_at_ms = EXCLUDED.updated_at_ms"
    )
    with _db_lock:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, params)
    return len(params)


def _pg_load_rows(segment: str, start: datetime | None = None,
                  end: datetime | None = None) -> pd.DataFrame | None:
    """Read fii_dii_history rows for a segment, optionally filtered to a
    date range. Returns a pandas DataFrame matching the shape the rest of
    the service expects, or None when no rows exist for that segment."""
    from app.lib.auth_store import ensure_primary_schema, get_conn  # noqa: PLC0415
    ensure_primary_schema()
    where = ["segment = %s"]
    params: list[Any] = [segment]
    if start is not None:
        where.append("date >= %s")
        params.append(pd.Timestamp(start).date())
    if end is not None:
        where.append("date <= %s")
        params.append(pd.Timestamp(end).date())
    sql = (
        f"SELECT {', '.join(_PG_COLS)} FROM fii_dii_history "
        f"WHERE {' AND '.join(where)} ORDER BY date"
    )
    with _db_lock:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _pg_date_range(segment: str) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Return (min_date, max_date) in PG for the given segment, or (None,
    None) when no rows exist. Used by the gap-fill logic to decide what
    needs fetching."""
    from app.lib.auth_store import ensure_primary_schema, get_conn  # noqa: PLC0415
    ensure_primary_schema()
    with _db_lock:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MIN(date), MAX(date) FROM fii_dii_history WHERE segment = %s",
                    (segment,),
                )
                row = cur.fetchone()
    if not row:
        return None, None
    # psycopg with dict_row returns a dict; with default it returns a tuple.
    if isinstance(row, dict):
        values = list(row.values())
    else:
        values = list(row)
    lo, hi = values[0], values[1]
    if lo is None:
        return None, None
    return pd.Timestamp(lo), pd.Timestamp(hi)


# ── Back-compat shims ────────────────────────────────────────────────────────
# Old call sites used these table-name-based helpers. Keep them so any
# external caller (tests, scripts) still works during the transition.

def save_to_db(df: pd.DataFrame, table: str):
    """Back-compat: writes via PG instead of SQLite."""
    segment = _segment_to_table_name(table)
    _pg_upsert_rows(segment, df)


def load_from_db(table: str) -> pd.DataFrame | None:
    """Back-compat: reads from PG instead of SQLite."""
    segment = _segment_to_table_name(table)
    return _pg_load_rows(segment)


def get_cached_date_range(table: str):
    """Back-compat: returns PG min/max for the segment."""
    segment = _segment_to_table_name(table)
    return _pg_date_range(segment)

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

    async def _fetch_fno_archive_day(self, day, verbose: bool = False) -> dict[str, dict]:
        """Download and parse one day's fao_participant_oi CSV. Returns
        a dict {segment_name: row_dict} for all 4 F&O segments. Empty dict
        on weekend/holiday/error.

        Routed through NseService.fetch_nse_archive_text so we share its
        in-process cache and header discipline rather than spinning up an
        ad-hoc httpx client here.

        `verbose=True` raises log level from DEBUG to INFO/WARNING so the
        scheduler's recent-day healer can surface exactly which dates fail
        and why — DEBUG-level failures were invisible in production logs
        and let weeks of F&O gaps accumulate silently.
        """
        date_str = day.strftime("%d%m%Y")
        url = _FNO_ARCHIVE_URL.format(date=date_str)
        cache_key = f"fno_oi_{date_str}"
        try:
            text = await self.nse.fetch_nse_archive_text(url, cache_key, ttl=86400)
            if not text or len(text) < 50:
                if verbose:
                    logger.warning("F&O archive empty for %s (NSE returned no body — "
                                   "likely 404 / not yet published / endpoint blocked)",
                                   day.strftime("%Y-%m-%d"))
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
            if verbose:
                logger.info("F&O archive ok for %s — %d segments parsed",
                            day.strftime("%Y-%m-%d"), len(out))
            return out
        except Exception as e:
            if verbose:
                logger.warning("F&O archive fetch FAILED for %s: %s",
                               day.strftime("%Y-%m-%d"), str(e)[:120])
            else:
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

    async def _load_cache_only(self, segment: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Read only what PostgreSQL (or old JSON) already has — no live NSE fetch.
        Used by get_flows() so the first paint is always fast."""
        table = f"fii_dii_{segment}"
        loop = asyncio.get_running_loop()

        cached_min, _ = await loop.run_in_executor(None, get_cached_date_range, table)

        cached_df: pd.DataFrame | None = None
        if segment == "equity" and not cached_min:
            # One-time migration path: pull old JSON history into PG on first load.
            cached_df = await loop.run_in_executor(None, _load_old_json_history)
            if cached_df is not None and not cached_df.empty:
                await loop.run_in_executor(None, save_to_db, cached_df, table)
        else:
            cached_df = await loop.run_in_executor(None, load_from_db, table)

        if cached_df is None or cached_df.empty:
            return pd.DataFrame()

        cached_df["date"] = pd.to_datetime(cached_df["date"])
        mask = (cached_df["date"] >= pd.Timestamp(start)) & (cached_df["date"] <= pd.Timestamp(end))
        return cached_df[mask].copy()

    async def _background_refresh_segment(self, segment: str, start: datetime, end: datetime) -> None:
        """Fetch any missing date ranges from NSE and persist to the cache.
        Runs as a fire-and-forget asyncio task so get_flows() never blocks on it."""
        global _refresh_in_progress, _refresh_last_failed
        if segment in _refresh_in_progress:
            return
        _refresh_in_progress.add(segment)
        found_today = False
        try:
            table = f"fii_dii_{segment}"
            loop = asyncio.get_running_loop()

            cached_min, cached_max = await loop.run_in_executor(None, get_cached_date_range, table)

            fetch_ranges: list[tuple[datetime, datetime]] = []
            if cached_min and cached_max:
                if start < cached_min:
                    fetch_ranges.append((start, cached_min - timedelta(days=1)))
                if end > cached_max:
                    fetch_ranges.append((cached_max + timedelta(days=1), end))
            else:
                fetch_ranges.append((start, end))

            if not fetch_ranges:
                return

            new_dfs: list[pd.DataFrame] = []
            for rs, re in fetch_ranges:
                try:
                    if segment == "equity":
                        ndf = await self.fetch_equity_historical(rs, re)
                    else:
                        ndf = await self.fetch_fno_historical(segment, rs, re)
                    if not ndf.empty:
                        new_dfs.append(ndf)
                except Exception as exc:
                    logger.warning("Background refresh failed for segment=%s range=%s→%s: %s",
                                   segment, rs.date(), re.date(), exc)

            if not new_dfs:
                return

            cached_df = await loop.run_in_executor(None, load_from_db, table)
            all_dfs = ([cached_df] if cached_df is not None and not cached_df.empty else []) + new_dfs
            combined = pd.concat(all_dfs, ignore_index=True)
            combined["date"] = pd.to_datetime(combined["date"])
            combined = combined.sort_values("date").drop_duplicates("date").reset_index(drop=True)
            await loop.run_in_executor(None, save_to_db, combined, table)

            # Check whether today's row was actually obtained so _today_status
            # can flip to "available" on the next request.
            import time as _time  # noqa: PLC0415
            try:
                import zoneinfo  # noqa: PLC0415
                _ist = zoneinfo.ZoneInfo("Asia/Kolkata")
            except Exception:
                _ist = None  # type: ignore[assignment]
            from datetime import timezone as _tz  # noqa: PLC0415
            _now_ist = datetime.now(_ist) if _ist else datetime.now(_tz.utc)
            today_iso = _now_ist.strftime("%Y-%m-%d")
            if not combined.empty:
                dates_got = set(combined["date"].dt.strftime("%Y-%m-%d").tolist())
                found_today = today_iso in dates_got

            logger.info("Background refresh done — segment=%s, %d new rows added, today=%s",
                        segment, sum(len(d) for d in new_dfs), "yes" if found_today else "no")
        except Exception as exc:
            logger.warning("Background refresh error — segment=%s: %s", segment, exc)
        finally:
            _refresh_in_progress.discard(segment)
            import time as _t  # noqa: PLC0415
            if found_today:
                # Success — reset the retry counter so we're clean for tomorrow.
                _refresh_fail_count.pop(segment, None)
                _refresh_last_failed.pop(segment, None)
            else:
                # This attempt didn't find today's data. Increment counter and
                # record when it finished so _today_status can enforce the retry
                # interval before firing the next task.
                prev = _refresh_fail_count.get(segment, 0)
                _refresh_fail_count[segment] = prev + 1
                _refresh_last_failed[segment] = _t.time()
                attempt = _refresh_fail_count[segment]
                if attempt >= MAX_TODAY_RETRIES:
                    logger.info(
                        "FII/DII today-fetch exhausted %d/%d attempts for %s — "
                        "entering %d-min cooldown.",
                        attempt, MAX_TODAY_RETRIES, segment, _REFRESH_COOLDOWN_S // 60,
                    )
                else:
                    logger.info(
                        "FII/DII today-fetch attempt %d/%d failed for %s — "
                        "retrying in %ds.",
                        attempt, MAX_TODAY_RETRIES, segment, _RETRY_INTERVAL_S,
                    )

    @staticmethod
    def _today_status(df: pd.DataFrame, segment: str) -> tuple[str, int]:
        """Return (status, attempt_number) for today's data.

        status values:
          'available' — today's row is already in the cached DataFrame.
          'fetching'  — a background task is running OR we are within the
                        MAX_TODAY_RETRIES retry budget (task will fire shortly).
          'not_yet'   — market hasn't closed yet, it's a weekend, OR all
                        MAX_TODAY_RETRIES attempts failed and the 30-min
                        cooldown hasn't elapsed.

        attempt_number — how many fetch attempts have been made so far
                         (0 = none yet, 5 = exhausted).
        """
        import time as _time  # noqa: PLC0415
        try:
            import zoneinfo  # noqa: PLC0415
            ist = zoneinfo.ZoneInfo("Asia/Kolkata")
        except Exception:
            ist = None  # type: ignore[assignment]

        from datetime import timezone as _tz  # noqa: PLC0415
        now_ist = datetime.now(ist) if ist else datetime.now(_tz.utc)
        today_iso = now_ist.strftime("%Y-%m-%d")

        if df is not None and not df.empty:
            dates = set(df["date"].dt.strftime("%Y-%m-%d").tolist())
            if today_iso in dates:
                return "available", 0

        # Only eligible on weekdays after 16:00 IST.
        is_weekday = now_ist.weekday() < 5
        after_close = now_ist.hour >= 16
        if not (is_weekday and after_close):
            return "not_yet", 0

        # Task actively running — report fetching so frontend keeps polling.
        if segment in _refresh_in_progress:
            return "fetching", _refresh_fail_count.get(segment, 0)

        fail_count = _refresh_fail_count.get(segment, 0)
        last_fail = _refresh_last_failed.get(segment, 0.0)
        elapsed = _time.time() - last_fail

        if fail_count < MAX_TODAY_RETRIES:
            # Still within the retry budget.  Return "fetching" so the frontend
            # shows the amber chip throughout the sequence.  get_flows() will
            # only fire a new task when _RETRY_INTERVAL_S has elapsed.
            return "fetching", fail_count

        # All retries exhausted — apply the long cooldown.
        if elapsed < _REFRESH_COOLDOWN_S:
            return "not_yet", fail_count

        # Cooldown expired — ready for a fresh 5-attempt cycle.
        # Reset the counter here so _background_refresh_segment starts clean.
        _refresh_fail_count.pop(segment, None)
        _refresh_last_failed.pop(segment, None)
        return "fetching", 0

    async def get_flows(self, segment: str, days: int = 365, force: bool = False) -> dict:
        import time as _time  # noqa: PLC0415
        end_date = datetime.today()
        start_date = end_date - timedelta(days=days)

        # Force-refresh: the user explicitly clicked Retry → reset counters so
        # the full 5-attempt cycle starts fresh regardless of cooldown state.
        if force:
            reset_today_fetch(segment)

        # ── Fast path: serve from cache immediately ───────────────────────────
        df: pd.DataFrame = pd.DataFrame()
        try:
            df = await self._load_cache_only(segment, start_date, end_date)
        except Exception as exc:
            logger.warning("Cache-only load failed for segment=%s: %s — will attempt live fetch", segment, exc)

        today_status, fetch_attempt = self._today_status(df, segment)

        # ── Cold-start fallback: no cached rows at all → blocking fetch ───────
        # Must run BEFORE the background-refresh decision so we only fire a
        # background task when we already have rows to serve immediately.
        # Firing both simultaneously duplicates hundreds of archive requests.
        if df is None or df.empty:
            try:
                df = await self.get_historical(segment, start_date, end_date)
                today_status, fetch_attempt = self._today_status(df, segment)
            except Exception as e:
                return self._empty_response(segment, f"Failed to fetch data: {e}")

        # ── Background refresh decision ───────────────────────────────────────
        # Two independent triggers — only ever one task at a time:
        #
        # 1. HISTORICAL GAP: any confirmed trading day before *yesterday* is
        #    missing from the cache.  These rows are already published by NSE;
        #    there is no reason to wait for market close.  Fire unconditionally,
        #    bypassing the _RETRY_INTERVAL_S throttle.
        #
        # 2. TODAY'S DATA: today's row is missing after market close
        #    (today_status=="fetching").  Gated by the per-segment retry
        #    throttle so we don't hammer NSE on every request.
        #
        # The two triggers are OR-ed so a single task covers both cases in one
        # pass (fetch_ranges in _background_refresh_segment spans the full gap).
        if segment not in _refresh_in_progress:
            loop_bg = asyncio.get_running_loop()
            _, _cached_max_bg = await loop_bg.run_in_executor(
                None, get_cached_date_range, f"fii_dii_{segment}"
            )
            from datetime import date as _date  # noqa: PLC0415
            _yesterday = datetime.utcnow().date() - timedelta(days=1)
            has_historical_gap = (
                _cached_max_bg is not None
                and pd.Timestamp(_cached_max_bg).date() < _yesterday
            )

            last_fail = _refresh_last_failed.get(segment, 0.0)
            elapsed   = _time.time() - last_fail
            today_due = today_status == "fetching" and (
                last_fail == 0.0 or elapsed >= _RETRY_INTERVAL_S
            )

            if has_historical_gap or today_due:
                asyncio.create_task(
                    self._background_refresh_segment(segment, start_date, end_date)
                )
                if has_historical_gap:
                    logger.info(
                        "FII/DII historical gap detected for segment=%s "
                        "(cache ends %s, yesterday=%s) — firing gap-fill",
                        segment,
                        pd.Timestamp(_cached_max_bg).date() if _cached_max_bg else "none",
                        _yesterday,
                    )

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
            # 'available' = today's row in cache
            # 'fetching'  = within the MAX_TODAY_RETRIES budget, task will fire
            # 'not_yet'   = market open/weekend OR cooldown after exhausting retries
            "todayStatus": today_status,
            # Retry progress — lets the frontend show "Attempt 2 of 5"
            "todayFetchAttempt": fetch_attempt,
            "todayMaxAttempts": MAX_TODAY_RETRIES,
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

    # ── Daily-refresh entry points (called by main.py scheduler) ─────────────
    #
    # Two callers:
    #   * Startup gap-fill — walks the last `gap_days` trading days and
    #     fetches any that aren't already in PG. Survives long downtimes
    #     where the scheduler missed runs.
    #   * Daily tick — fetches just today's snapshot + archive. Cheap.

    async def heal_recent_fno_gaps(self, lookback_days: int = 7) -> dict:
        """Aggressively re-check the last `lookback_days` weekdays for F&O
        data and fetch any that PG is missing.

        Why this exists: the daily 24h scheduler missed recent days
        because (a) early ticks ran before NSE published that day's archive
        and (b) cached 'empty response' results from earlier failures
        persisted in the 24h NSE HTTP cache, suppressing retries.

        This method:
          * Builds the list of expected weekdays in the window.
          * Queries PG for which of those dates already have F&O rows
            (using `index_future` as the representative segment — all 4
            F&O segments are written together by `fetch_fno_historical`).
          * Force-refetches only the missing dates with `force_refresh=True`
            on the NSE call so a previously-cached empty body doesn't
            short-circuit the retry.
          * Persists every segment from each successful day.

        Returns a status dict with per-date outcomes for the admin UI.
        """
        from datetime import timezone  # noqa: PLC0415
        today = datetime.now(timezone.utc).date()
        expected_days: list = []
        cur = today - timedelta(days=lookback_days)
        while cur <= today:
            if cur.weekday() < 5:
                expected_days.append(cur)
            cur += timedelta(days=1)

        # Which of those days does PG already have?
        loop = asyncio.get_running_loop()
        existing = await loop.run_in_executor(
            None, _pg_load_rows, "index_future",
            datetime.combine(expected_days[0], datetime.min.time()) if expected_days else None,
            datetime.combine(expected_days[-1], datetime.min.time()) if expected_days else None,
        )
        present_dates: set = set()
        if existing is not None and not existing.empty:
            present_dates = {d.date() for d in pd.to_datetime(existing["date"])}

        missing = [d for d in expected_days if d not in present_dates]
        if not missing:
            return {"checked": len(expected_days), "missing": 0, "filled": 0, "days": []}

        # Bypass any cached empty bodies — recent days that failed earlier
        # need a real retry, not a replay of the cached failure.
        outcomes: list[dict] = []
        all_per_segment: dict[str, list[dict]] = {seg: [] for seg in _FNO_SEGMENT_COLS}
        sem = asyncio.Semaphore(2)  # be polite — recent archive is small

        async def _one(d):
            async with sem:
                # Invalidate the NSE HTTP cache for this specific archive
                # so we make a fresh network call instead of replaying any
                # previously-cached empty body.
                try:
                    self.nse._cache.pop(f"fno_oi_{d.strftime('%d%m%Y')}", None)  # type: ignore[attr-defined]
                except Exception:
                    pass
                rows = await self._fetch_fno_archive_day(d, verbose=True)
                outcomes.append({
                    "date":   d.strftime("%Y-%m-%d"),
                    "ok":     bool(rows),
                    "segments": list(rows.keys()),
                })
                for seg, row in rows.items():
                    all_per_segment[seg].append(row)

        await asyncio.gather(*[_one(d) for d in missing], return_exceptions=True)

        # Persist whatever we got across all 4 F&O segments.
        filled = 0
        for seg, rows in all_per_segment.items():
            if not rows:
                continue
            seg_df = pd.DataFrame(rows)
            seg_df["date"] = pd.to_datetime(seg_df["date"], format="ISO8601")
            seg_df = seg_df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
            written = await loop.run_in_executor(None, _pg_upsert_rows, seg, seg_df)
            # Count each calendar day at most once (rows is per-segment).
            if seg == "index_future":
                filled = written

        return {
            "checked": len(expected_days),
            "missing": len(missing),
            "filled":  filled,
            "days":    outcomes,
        }

    async def scheduled_daily_fetch(self, gap_days: int = 30) -> dict:
        """Pull today's flows + heal any gaps in the last `gap_days` for
        every supported segment, upserting into PG. Called by a background
        scheduler so users never have to open the page for data to refresh.

        Always returns a status dict (never raises) so the caller can log
        without try/except clutter.
        """
        end_date = datetime.today()
        start_date = end_date - timedelta(days=gap_days)
        per_segment: dict[str, dict] = {}
        for seg in ("equity", "index_future", "index_option",
                    "stock_future", "stock_option"):
            try:
                # get_historical handles "what's missing in the cache" via
                # its existing gap-merge logic; switching that cache from
                # SQLite to PG (above) means this single call now fills
                # everything missing in the last `gap_days` window.
                df = await self.get_historical(seg, start_date, end_date)
                per_segment[seg] = {
                    "ok":       True,
                    "rows":     int(0 if df is None or df.empty else len(df)),
                    "latest":   None if df is None or df.empty
                                else df["date"].max().strftime("%Y-%m-%d"),
                }
            except Exception as exc:
                logger.warning("FII/DII scheduled fetch failed for %s: %s",
                               seg, str(exc)[:160])
                per_segment[seg] = {"ok": False, "error": str(exc)[:160]}
        return {
            "ok":       True,
            "from":     start_date.strftime("%Y-%m-%d"),
            "to":       end_date.strftime("%Y-%m-%d"),
            "segments": per_segment,
        }

    async def backfill_all(self, days: int = 400) -> dict:
        """One-shot backfill of every supported segment into the PG history
        table. Returns a summary dict with row counts per segment."""
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
