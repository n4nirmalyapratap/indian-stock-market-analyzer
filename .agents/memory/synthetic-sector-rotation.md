---
name: Synthetic sector rotation engine
description: Structure + non-obvious math contracts of the hyper-granular sub-industry rotation feature
---

Feature lives alongside (NOT replacing) the existing `/sectors` flow. Engine:
`app/services/synthetic_sectors_service.py`; routes under `/api/sector-analytics/synthetic/*`;
frontend page `/sector-analytics` (`SectorAnalytics.tsx`). Existing `sectors_service.py` is untouched.

Data model: `stocks` (classified universe) + `synthetic_sector_daily_metrics`
(one dated row per sub_industry, PK `(sub_industry, metric_date)`). A reserved
row `sub_industry='__NIFTY50__'` stores the benchmark index chained in lockstep
so read-time relative strength is apples-to-apples.

Non-obvious math contracts (enforce these — they were a code-review FAIL once):
- **30D relative strength** must be **date-aligned** and a **true ~30-day window**.
  `relative_strength_30d` takes `list[(date, value)]` for BOTH series, intersects
  on date, restricts to the trailing `_RS_WINDOW_CAL_DAYS` (30) days, and returns
  None unless the aligned window has >= `_RS_MIN_OBS` (18) observations. Never feed
  it raw value lists or compare unaligned start/end dates.
- **Delivery 20-DMA** (`_delivery_20dma`) returns None unless a FULL
  `_DELIVERY_DMA_WINDOW` (20) sessions exist — partial history would trip the
  build-up flag too early.

**Why:** the label "30D RS / 20-DMA build-up" must match the actual math, and a
sparse/young sub-industry must degrade to None honestly rather than emit a
distorted short-window number.

**How to apply:** nightly worker `run_nightly_metrics(yahoo)` is idempotent
(ON CONFLICT upsert); scheduler fires 16:30 IST (11:00 UTC). Delivery archive
unavailable → `avg_delivery_pct=None` (never fabricated 0). Route handlers wrap
blocking DB/network in `asyncio.to_thread`; constituent fetches use a bounded
`asyncio.Semaphore`.
