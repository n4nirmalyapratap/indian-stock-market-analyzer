# BSE delivery integration — implementation brief

> Self-contained spec. It assumes **zero prior conversation** — you can paste the
> whole file into a fresh AI session (or hand it to a developer) and act on it cold.
> **Do not start coding — first do Step 1, then confirm the decisions below.**

## Environment

- Repo root: `D:\p_p_project\indian-stock-market-analyzer`
- Backend: Python 3.11 / FastAPI / uvicorn at `artifacts/python-backend` (runs with `--reload`).
  Tests via `pytest`; a venv with `fastapi httpx psycopg pytest` is required (the default
  `python` on PATH may be 2.7 — use the project venv).
- Frontend: React + TS + Vite at `artifacts/stock-market-app`.
- Follow `CLAUDE.md`: surgical changes, match existing style, no speculative abstractions,
  keep the NSE path as a fallback.

## The problem

Per-stock "delivery %" is **NSE-only**. The parser `delivery_service._parse()` keeps **only
`SERIES == "EQ"`** (`artifacts/python-backend/app/services/delivery_service.py`, ~L58:
`cells[1].upper() != "EQ"`) and drops no-trade / 0% rows (~L69). Consequence: stocks in NSE
non-EQ series (BE / Trade-to-Trade / surveillance) or **BSE-only / NSE-SME** listings show
**"Del —"** in the Sector Rotation Cockpit shortlist and elsewhere.

For T2T stocks delivery is actually ~100% (mandatory delivery) — so **"Del —" is a coverage
gap, not "no delivery."** NSE carries ~90%+ of cash volume, so NSE-only is representative for
liquid names but misses the BSE-heavy / illiquid tail.

**Goal:** optionally fetch **BSE delivery**, merge it **quantity-weighted** with NSE, to fill
that gap — WITHOUT hammering BSE (one fetch/day, sealed to disk).

## Key files (function names are stable; line numbers approximate)

- `delivery_service.py`
  - `_NSE_BHAVDATA_URL_TPL` (~L34): `https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv`
  - `_parse(text)` (~L42) → rows `{symbol, tradedQty, delivQty, delivPct, turnover, delivValue}`; EQ-only filter ~L58, positive-trade filter ~L69.
  - `get_delivery_rows()` (~L82): walks back 8 days to the latest published file; **in-memory** `_cache` (4h, 12h when closed + final); returns `(rows, trade_date_iso)`.
  - `aggregate_delivery(groups, rows)` (~L134): **quantity-weighted** ΣdelivQty/ΣtradedQty; pure, unit-tested in `tests/test_sector_rotation.py`.
  - `_delivery_map_for_date(d)` (~L201), `get_recent_day_maps(days, lookback)` (~L218): per-day `{symbol: delivPct}`; in-memory `_DAY_MAP_CACHE`.
- `bse_service.py`: `api.bseindia.com/BseIndiaAPI/api` is **cloud-IP-friendly / no Akamai** (reliable). Has `NSE_TO_BSE_SCRIP` static map (~150 names) + `_resolve_scrip_code()` (static → in-proc cache → `SchrchScrip/w` search). Per-scrip endpoints `/ComHeader/w`, `/StockReachGraph/w`. ⚠️ Per-scrip is the **wrong tool** for full-market delivery (~2000 calls/day = the hammering to avoid).
- `nse_bhavcopy_service.py`: already downloads from `www.bseindia.com/download/BhavCopy/Derivative/` → the BSE **download host is reachable from this app**.
- `routes/insights.py`: BSE XBRL via `www.bseindia.com/xml-data/corpfiling/AttachLive/`, `api.bseindia.com/.../AnnSubCategoryGetData/w`.
- `nse_service.py`: `fetch_nse_archive_text(url, cache_key, ttl, retries=2)` (~L230) — generic archive fetcher (retry + 429 backoff); in-memory `_CACHE` (L31).
- `market_cache_service.py`: disk EOD pattern — `market_cache/<trading-date>/<SYMBOL>.json`; helpers `load_with_meta`, `save_to_disk`, `is_market_open()`, `last_trading_date()`, `current_market_state()`, `cache_version()`. Post-close + startup warm job lives in `main.py`.
- Consumers: `sector_rotation_service.shortlist()` uses `get_recent_day_maps(days=12)`, `delivPct = deliv_map.get(sym)` → "Del —" when missing. Sub-industry grid delivery (`deliveryBuildup`, `avgDeliveryPct`) comes from `synthetic_sectors_service` **stored DB metrics** (separate path — not this fetch). Frontend: `artifacts/stock-market-app/src/pages/SectorRotation.tsx` renders "Del X%" / "—" + sparkline.

## Step 1 — VERIFY first (decides the whole design)

BSE may NOT carry delivery in its common bhavcopy. By analogy to NSE (UDiFF `BhavCopy_NSE_CM_…`
excludes delivery; it lives in `sec_bhavdata_full`), BSE's common bhavcopy **probably excludes
delivery** and BSE likely publishes a **separate scrip-wise delivery file**. Confirm against a
LIVE response — **do not assume URLs**:

- Candidate A (common bhavcopy, likely NO delivery): `https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_<YYYYMMDD>_F_0000.CSV`
- Candidate B (separate delivery file, likely YES): find the current exact URL (BSE downloads page / older `bseindia.com/BSEDATA/...` "gross delivery" paths).

**Deliverable of Step 1:** the exact URL + delivery qty/% column names + the join key available
(ISIN and/or scrip code).

## Step 2 — Design (recommended)

- **Source = ONE EOD file/day** (the file from Step 1), NOT the per-scrip `api.bseindia.com`.
  Use polite headers (copy `bse_service._HEADERS`), timeout, retries, follow_redirects.
- **Disk-seal:** parse once → write `market_cache/<last_trading_date()>/bse_delivery.json`;
  serve from disk when the market is closed; walk back to the most recent available day on a
  miss. Mirror the `market_cache_service` pattern. → ≤1 network call/day, restart-safe,
  outage-tolerant.
- **Join key = ISIN** (both NSE `sec_bhavdata_full` and BSE files carry ISIN) to avoid the
  ticker ↔ scrip-code mismatch. If ISIN isn't usable, load a full BSE scrip master once
  (`List_Scrips` / securities master); the 150-entry static map is insufficient for full
  coverage.
- **Merge (quantity-weighted — never average the two percentages):**
  `consolidated% = (nse_delivQty + bse_delivQty) / (nse_tradedQty + bse_tradedQty) × 100`.
  Extend `aggregate_delivery` / the per-symbol map to pool NSE+BSE quantities. Keep the
  NSE-only path intact behind a flag/fallback.
- **Labeling/UX:** decide provenance ("NSE" vs "NSE+BSE"); flag T2T (~100%) so it isn't read
  as conviction.

## Step 3 — Optional related fix

NSE delivery cache is **in-memory only** (`delivery_service._cache`, `_DAY_MAP_CACHE`,
`nse_service._CACHE`) → a server restart wipes it and the first request re-fetches (fragile if
the NSE archive is momentarily down). Apply the same disk-seal so closed-market delivery is
instant + restart-proof.

## Decisions to confirm before coding

1. Join on **ISIN** (recommended) or scrip-code map?
2. **Consolidate** NSE+BSE into one % (recommended) or expose BSE as a separate column?
3. **T2T labeling** — tag "T2T ~100%", or just show the number?
4. Scope — full universe, or only fill the current "Del —" tail?
5. Also do Step 3 (disk-seal NSE delivery)?

## Acceptance criteria

- A BSE-only / T2T stock that shows "Del —" today shows a delivery % (or a labeled consolidated value).
- ≤1 BSE network call/day in the delivery path (verify in logs); served from disk when closed; survives a restart.
- Liquid-stock numbers essentially unchanged (NSE dominates) OR clearly relabeled as consolidated.
- `tests/test_sector_rotation.py` delivery tests still pass; add tests for the consolidation math + BSE parse.
- No per-scrip BSE calls in the delivery path.

## Honest constraints

- There is **no** official consolidated NSE+BSE delivery feed and **no** reliable free
  third-party API — every provider parses these same exchange EOD files. Reliability comes
  from **fetch-once-daily + disk-seal**, not from a magic source.
- BSE's `www` download host is more bot-hostile than `api.bseindia.com`, but it already works
  in this app for derivative bhavcopy + XBRL. Be polite, cache, never hammer.

## Background: why NSE-only isn't strictly "wrong"

Delivery % is computed per exchange, so NSE% ≠ BSE% for the same stock. But NSE carries
~90%+ of cash volume, so for liquid names the NSE figure ≈ the all-India figure, and it's the
market convention (Trendlyne, Chartink, screener.in all quote NSE delivery). It's
**incomplete for the BSE-heavy / illiquid tail, not incorrect for the liquid majority.** The
cheapest honest improvement (independent of this BSE work) is simply to **label the field
"NSE delivery %"** in the UI so it never implies a consolidated number.
