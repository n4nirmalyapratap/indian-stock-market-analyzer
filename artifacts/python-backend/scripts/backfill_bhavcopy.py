"""
backfill_bhavcopy.py
CLI to populate the NSE F&O bhavcopy cache for a date range.

Usage:
    python scripts/backfill_bhavcopy.py --start 2022-01-01 --end 2025-12-31
    python scripts/backfill_bhavcopy.py --days 30           # last 30 calendar days
    python scripts/backfill_bhavcopy.py --resume            # only missing dates

Skips weekends.  Idempotent — already-ingested dates marked 'ok' are skipped
unless --force is passed.  Polite delay between requests: 0.6s by default.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# Allow running as `python scripts/backfill_bhavcopy.py` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.nse_bhavcopy_service import (   # noqa: E402
    ingest_bhavcopy, get_coverage, _connect,
)


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def _date_range(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:        # Mon-Fri
            out.append(d)
        d += timedelta(days=1)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=_parse, help="YYYY-MM-DD (inclusive)")
    p.add_argument("--end",   type=_parse, help="YYYY-MM-DD (inclusive); default=today")
    p.add_argument("--days",  type=int, help="Backfill the last N calendar days")
    p.add_argument("--force", action="store_true",
                   help="Re-ingest dates already marked 'ok'")
    p.add_argument("--resume", action="store_true",
                   help="Skip dates marked 'ok' (default behaviour anyway)")
    p.add_argument("--delay", type=float, default=0.6,
                   help="Seconds between HTTP requests (default 0.6)")
    args = p.parse_args()

    today = date.today()
    if args.days:
        start = today - timedelta(days=args.days)
        end   = today - timedelta(days=1)
    else:
        if not args.start:
            p.error("--start is required (or use --days)")
        start = args.start
        end   = args.end or (today - timedelta(days=1))

    dates = _date_range(start, end)
    if not args.force:
        with _connect() as conn:
            done = {r["trade_date"] for r in conn.execute(
                "SELECT trade_date FROM ingest_log WHERE status='ok'"
            )}
        dates = [d for d in dates if d.isoformat() not in done]

    print(f"Backfilling {len(dates)} dates: {start} → {end}", flush=True)
    ok = empty = err = 0
    for d in dates:
        res = ingest_bhavcopy(d)
        tag = res["status"]
        if tag == "ok":     ok += 1
        elif tag == "empty": empty += 1
        else:                err += 1
        print(f"  {d}  {tag:<11}  rows={res['rows']:>6}  src={res['source'] or '-'}",
              flush=True)
        time.sleep(args.delay)

    cov = get_coverage()
    print(f"\nDone.  ok={ok}  empty={empty}  errors={err}")
    print(f"Cache total rows: {cov['row_count']:,}  range: {cov['date_min']} → {cov['date_max']}")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
