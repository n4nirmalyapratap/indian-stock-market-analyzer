from __future__ import annotations

import atexit
import logging
import os
import threading
import time
import uuid
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger("auth_store")

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _database_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required. PostgreSQL is the system of record for app auth data.")
    return url


# ── Connection pool ─────────────────────────────────────────────────────────
#
# Pre-pool: every `with get_conn() as conn:` did a fresh TCP + TLS + auth
# handshake (~50-150ms per call on a non-LAN PG). The app does this on
# essentially every request and every scheduler tick, so it was the
# dominant latency component for short queries.
#
# Pool: psycopg_pool.ConnectionPool keeps a warm pool of connections open
# and hands them out on demand. Same `with ... as conn:` context-manager
# API — pool.connection() returns a context manager that yields a
# psycopg.Connection, identical to psycopg.connect() so zero call-site
# changes were needed.
#
# Sizing:
#   min_size=2   — always-warm baseline so the first request after a
#                  quiet period doesn't pay the cold-start handshake.
#   max_size=20  — cap. Most managed PG instances allow ~100 connections
#                  total, and we run alongside other workers; 20 gives
#                  plenty of headroom without exhausting the server.
#   timeout=30s  — caller waits up to 30s for a free connection. Beats
#                  silently dropping requests under burst load.
#   max_idle=600s — connections that sit idle >10 min get recycled. PG
#                  may close idle connections; this evicts them before
#                  the next request hits a stale socket.
# Override via env vars for production tuning.

_POOL: ConnectionPool | None = None
_POOL_LOCK = threading.Lock()


def _pool_size_envs() -> tuple[int, int, float, float]:
    return (
        int(os.environ.get("DB_POOL_MIN_SIZE", "2")),
        int(os.environ.get("DB_POOL_MAX_SIZE", "20")),
        float(os.environ.get("DB_POOL_TIMEOUT_SEC", "30")),
        float(os.environ.get("DB_POOL_MAX_IDLE_SEC", "600")),
    )


def _init_pool() -> ConnectionPool:
    """Build (or return) the module-level pool. Thread-safe via
    _POOL_LOCK. Called lazily on first get_conn() so import order
    doesn't matter."""
    global _POOL
    if _POOL is not None:
        return _POOL
    with _POOL_LOCK:
        if _POOL is not None:
            return _POOL
        min_sz, max_sz, timeout_s, max_idle_s = _pool_size_envs()
        # `kwargs={"row_factory": dict_row}` applies to every connection
        # the pool hands out — matches the previous get_conn() default.
        pool = ConnectionPool(
            conninfo=_database_url(),
            min_size=min_sz,
            max_size=max_sz,
            timeout=timeout_s,
            max_idle=max_idle_s,
            kwargs={"row_factory": dict_row},
            # `open=True` opens min_size connections at construction so
            # the first request gets warm pool, not a handshake.
            open=True,
            name="auth-store",
        )
        _POOL = pool
        logger.info(
            "PG pool initialised (min=%d, max=%d, timeout=%ds, max_idle=%ds)",
            min_sz, max_sz, int(timeout_s), int(max_idle_s),
        )
        # Defensive: if the process exits without main.py's lifespan
        # cleanup running (scripts, tests, SIGKILL on workers), still
        # try to drain the pool so PG doesn't see orphan connections.
        atexit.register(close_pool)
        return pool


def get_conn():
    """Check out a connection from the pool.

    Returns a context manager — use it the same way as before:

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
                rows = cur.fetchall()

    On `__exit__` the connection is returned to the pool (NOT closed).
    Broken connections are auto-detected and replaced — callers don't
    need to retry.
    """
    return _init_pool().connection()


def close_pool() -> None:
    """Drain and close the pool. Called by main.py's lifespan shutdown
    and by atexit. Safe to call multiple times — second call is a no-op."""
    global _POOL
    if _POOL is None:
        return
    try:
        _POOL.close()
        logger.info("PG pool closed.")
    except Exception as exc:
        logger.warning("PG pool close failed: %s", exc)
    finally:
        _POOL = None


def now_ms() -> int:
    return int(time.time() * 1000)


def ensure_primary_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_users (
                        id            TEXT PRIMARY KEY,
                        email         TEXT NOT NULL UNIQUE,
                        name          TEXT NOT NULL DEFAULT '',
                        google_sub    TEXT NOT NULL UNIQUE,
                        picture_url   TEXT NOT NULL DEFAULT '',
                        auth_provider TEXT NOT NULL DEFAULT 'google',
                        is_admin      BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at    BIGINT NOT NULL,
                        updated_at    BIGINT NOT NULL,
                        last_login_at BIGINT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_secrets (
                        key         TEXT PRIMARY KEY,
                        value       TEXT NOT NULL DEFAULT '',
                        description TEXT NOT NULL DEFAULT '',
                        masked      BOOLEAN NOT NULL DEFAULT TRUE,
                        updated_at  BIGINT NOT NULL
                    )
                    """
                )

                # ── Portfolio tables (migrated from artifacts/python-backend/
                # market_cache/portfolio.db). UUID-string IDs preserved so the
                # external API contract stays identical. inserted_at gives us a
                # deterministic tiebreaker for transactions sharing the same
                # traded_at ISO string (replaces SQLite's implicit `rowid`).
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS portfolios (
                        id            TEXT PRIMARY KEY,
                        user_id       TEXT NOT NULL,
                        name          TEXT NOT NULL,
                        base_currency TEXT NOT NULL DEFAULT 'INR',
                        cash          DOUBLE PRECISION NOT NULL DEFAULT 0,
                        created_at    BIGINT NOT NULL,
                        updated_at    BIGINT NOT NULL
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_portfolios_user "
                    "ON portfolios(user_id)"
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS portfolio_transactions (
                        id            TEXT PRIMARY KEY,
                        portfolio_id  TEXT NOT NULL
                                      REFERENCES portfolios(id) ON DELETE CASCADE,
                        symbol        TEXT NOT NULL,
                        side          TEXT NOT NULL
                                      CHECK (side IN ('BUY','SELL','DIVIDEND')),
                        qty           DOUBLE PRECISION NOT NULL,
                        price         DOUBLE PRECISION NOT NULL,
                        fees          DOUBLE PRECISION NOT NULL DEFAULT 0,
                        traded_at     TEXT NOT NULL,
                        source        TEXT NOT NULL DEFAULT 'manual',
                        note          TEXT,
                        inserted_at   BIGINT NOT NULL
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tx_portfolio "
                    "ON portfolio_transactions(portfolio_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tx_symbol "
                    "ON portfolio_transactions(portfolio_id, symbol)"
                )

                # ── AI Analyst tables (migrated from artifacts/python-backend/
                # market_cache/ai_analyst.db).
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ai_analyst_quota (
                        user_id       TEXT NOT NULL,
                        run_date_ist  TEXT NOT NULL,
                        runs_used     INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, run_date_ist)
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ai_analyst_saved (
                        id            BIGSERIAL PRIMARY KEY,
                        user_id       TEXT NOT NULL,
                        scope_type    TEXT NOT NULL,
                        scope_key     TEXT NOT NULL,
                        tickers_json  TEXT NOT NULL,
                        label         TEXT,
                        verdict       TEXT,
                        confidence    TEXT,
                        headline      TEXT,
                        report_json   TEXT NOT NULL,
                        models_used   TEXT NOT NULL DEFAULT '',
                        sources_used  TEXT NOT NULL DEFAULT '',
                        wall_clock_ms BIGINT NOT NULL DEFAULT 0,
                        created_at    BIGINT NOT NULL,
                        updated_at    BIGINT NOT NULL,
                        UNIQUE (user_id, scope_type, scope_key)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_saved_user_updated "
                    "ON ai_analyst_saved(user_id, scope_type, updated_at DESC)"
                )

                # ── AI Analyst backtest results ────────────────────────────
                # Every BUY/SELL verdict from ai_analyst_saved gets one row
                # per evaluation horizon (1d, 5d, 30d). actual_return_pct is
                # the realised % change from the price at verdict time to the
                # close on the evaluation date. was_correct compares that
                # against the verdict direction with a 0.5% deadband.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ai_analyst_backtest (
                        id                  BIGSERIAL PRIMARY KEY,
                        saved_id            BIGINT NOT NULL
                                            REFERENCES ai_analyst_saved(id) ON DELETE CASCADE,
                        user_id             TEXT NOT NULL,
                        ticker              TEXT NOT NULL,
                        verdict             TEXT NOT NULL,
                        confidence          TEXT,
                        verdict_at_ms       BIGINT NOT NULL,
                        verdict_price       DOUBLE PRECISION,
                        horizon_days        INTEGER NOT NULL,
                        evaluated_at_ms     BIGINT NOT NULL,
                        actual_price        DOUBLE PRECISION,
                        actual_return_pct   DOUBLE PRECISION,
                        was_correct         BOOLEAN,
                        notes               TEXT,
                        UNIQUE (saved_id, horizon_days)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_backtest_user_evaluated "
                    "ON ai_analyst_backtest(user_id, evaluated_at_ms DESC)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_backtest_ticker "
                    "ON ai_analyst_backtest(ticker, horizon_days)"
                )

                # ── Email digest subscriptions + send queue ────────────────
                # Each row = (user_id, group_name, recipient_email) — a user
                # can have multiple subscriptions routed to different inboxes
                # (e.g. their own + their advisor's), each scoped to a
                # different subset of their portfolio's symbols.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS email_digest_subs (
                        id              BIGSERIAL PRIMARY KEY,
                        user_id         TEXT NOT NULL,
                        group_name      TEXT NOT NULL DEFAULT 'default',
                        recipient_email TEXT NOT NULL,
                        symbols         TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
                        send_time_ist   TEXT NOT NULL DEFAULT '18:00',
                        enabled         BOOLEAN NOT NULL DEFAULT TRUE,
                        last_sent_date_ist TEXT,
                        created_at      BIGINT NOT NULL,
                        updated_at      BIGINT NOT NULL,
                        UNIQUE (user_id, group_name)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_digest_subs_user "
                    "ON email_digest_subs(user_id)"
                )

                # The queue. Inserted by the scheduler when a subscription is
                # due; drained by the SMTP worker with token-bucket throttle.
                # Keeping subject/html/text materialised on the row means a
                # subscription edit between enqueue and send doesn't change
                # what gets delivered.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS email_digest_queue (
                        id              BIGSERIAL PRIMARY KEY,
                        sub_id          BIGINT NOT NULL
                                         REFERENCES email_digest_subs(id) ON DELETE CASCADE,
                        recipient_email TEXT NOT NULL,
                        subject         TEXT NOT NULL,
                        body_html       TEXT NOT NULL,
                        body_text       TEXT NOT NULL,
                        status          TEXT NOT NULL DEFAULT 'pending',
                                         -- pending | sent | failed
                        attempts        INTEGER NOT NULL DEFAULT 0,
                        last_error      TEXT,
                        enqueued_at_ms  BIGINT NOT NULL,
                        sent_at_ms      BIGINT,
                        next_retry_ms   BIGINT
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_digest_queue_status "
                    "ON email_digest_queue(status, next_retry_ms NULLS FIRST)"
                )

                # Daily send-counter for token-bucket throttle. One row per
                # `date_ist` so the counter resets cleanly at the IST day
                # boundary without any explicit "reset at midnight" job.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS email_digest_send_counter (
                        date_ist        TEXT PRIMARY KEY,
                        sends_today     INTEGER NOT NULL DEFAULT 0,
                        updated_at_ms   BIGINT NOT NULL
                    )
                    """
                )
                # Admin-set overrides for macro indicators. When set, the
                # macro service uses these instead of the FRED/Trading
                # Economics chain — useful for surfacing fresh values
                # after an RBI meeting before upstream providers publish.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS macro_overrides (
                        indicator      TEXT PRIMARY KEY,
                        value          DOUBLE PRECISION NOT NULL,
                        as_of          TEXT NOT NULL,
                        note           TEXT NOT NULL DEFAULT '',
                        set_by         TEXT NOT NULL DEFAULT '',
                        updated_at_ms  BIGINT NOT NULL
                    )
                    """
                )
                # FII / DII daily flow history. Replaces the prior SQLite
                # cache (market_cache/fii_dii_cache.db) which lived in a
                # non-persistent Docker volume and got wiped on every
                # container restart. Storing here so the data survives
                # restarts and a background scheduler can keep it fresh
                # without relying on someone opening the page.
                #
                # Equity rows populate fii_buy/sell/net + dii_buy/sell/net.
                # F&O rows populate fii_long/short + dii_long/short (+ client
                # and pro long/short). Net is stored explicitly for both.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS fii_dii_history (
                        segment        TEXT NOT NULL,
                        date           DATE NOT NULL,
                        fii_buy        DOUBLE PRECISION,
                        fii_sell       DOUBLE PRECISION,
                        fii_net        DOUBLE PRECISION,
                        dii_buy        DOUBLE PRECISION,
                        dii_sell       DOUBLE PRECISION,
                        dii_net        DOUBLE PRECISION,
                        fii_long       DOUBLE PRECISION,
                        fii_short      DOUBLE PRECISION,
                        dii_long       DOUBLE PRECISION,
                        dii_short      DOUBLE PRECISION,
                        client_long    DOUBLE PRECISION,
                        client_short   DOUBLE PRECISION,
                        pro_long       DOUBLE PRECISION,
                        pro_short      DOUBLE PRECISION,
                        created_at_ms  BIGINT NOT NULL,
                        updated_at_ms  BIGINT NOT NULL,
                        PRIMARY KEY (segment, date)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_fii_dii_history_seg_date "
                    "ON fii_dii_history (segment, date DESC)"
                )
                # Per-user broker API credentials. Each row is one
                # (user, broker) pairing — a user can wire up multiple
                # brokers and have them all queried in priority order.
                # `encrypted_creds` is a Fernet-encrypted JSON blob whose
                # shape varies by broker (e.g. Dhan needs {client_id,
                # access_token}, Zerodha needs {api_key, api_secret,
                # access_token, ...}). Encryption key is derived from
                # SESSION_SECRET so the DB dump alone leaks nothing.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_broker_keys (
                        user_id            TEXT NOT NULL,
                        broker             TEXT NOT NULL,
                        encrypted_creds    TEXT NOT NULL,
                        active             BOOLEAN NOT NULL DEFAULT TRUE,
                        last_test_status   TEXT NOT NULL DEFAULT '',
                        last_test_at_ms    BIGINT,
                        last_test_error    TEXT NOT NULL DEFAULT '',
                        created_at_ms      BIGINT NOT NULL,
                        updated_at_ms      BIGINT NOT NULL,
                        PRIMARY KEY (user_id, broker)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_user_broker_keys_user "
                    "ON user_broker_keys (user_id)"
                )
                # Stock logo cache. Binary PNG/SVG stored once, served from
                # our backend so the Dhan CDN is never called again after the
                # first fetch. `fetch_symbol` is what we ask Dhan for —
                # normally the same as `symbol` but admins can override it
                # (e.g. LTIM → LTIMindtree if Dhan uses the old ticker).
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS stock_logos (
                        symbol          TEXT PRIMARY KEY,
                        fetch_symbol    TEXT NOT NULL,
                        image_data      BYTEA,
                        content_type    TEXT NOT NULL DEFAULT 'image/png',
                        bytes_size      INTEGER,
                        fetch_ok        BOOLEAN NOT NULL DEFAULT FALSE,
                        updated_by      TEXT NOT NULL DEFAULT '',
                        fetched_at_ms   BIGINT NOT NULL,
                        updated_at_ms   BIGINT NOT NULL
                    )
                    """
                )
                # Note: the macro_scraped_data table (TradingEconomics +
                # data.gov.in scrape cache) was removed from the schema
                # bootstrap when the entire scraper pipeline was deleted.
                # The PR-review comment about "DROP destroying history"
                # is moot — no service writes to or reads from this table
                # anymore. If a legacy table still exists in your DB it
                # can be manually dropped with `DROP TABLE IF EXISTS
                # macro_scraped_data;` — leaving it does no harm.

                # ── Hyper-granular sector rotation ───────────────────────
                # `stocks` is the classification store for the synthetic
                # sub-industry rotation engine. One row per NSE symbol in
                # the curated universe, enriched with Yahoo profile data
                # (sector / industry / sub_industry / market_cap). Refreshed
                # weekly by the classifier. `classified_ok` is FALSE when the
                # Yahoo profile fetch failed — those rows are excluded from
                # synthetic-index aggregation so we never fake a sector tag.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS stocks (
                        symbol         TEXT PRIMARY KEY,
                        name           TEXT NOT NULL DEFAULT '',
                        yahoo_ticker   TEXT NOT NULL DEFAULT '',
                        sector         TEXT,
                        industry       TEXT,
                        sub_industry   TEXT,
                        market_cap     DOUBLE PRECISION,
                        cap_category   TEXT,
                        active         BOOLEAN NOT NULL DEFAULT TRUE,
                        classified_ok  BOOLEAN NOT NULL DEFAULT FALSE,
                        classify_error TEXT NOT NULL DEFAULT '',
                        updated_at_ms  BIGINT NOT NULL
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_stocks_sub_industry "
                    "ON stocks (sub_industry) WHERE active AND classified_ok"
                )
                # One dated row per synthetic sub-industry index. The nightly
                # worker writes the market-cap-weighted daily return, the
                # chained synthetic index level (base 1000 at inception), the
                # average NSE delivery % across constituents and its 20-DMA,
                # and the 50-EMA breadth (% of constituents above their own
                # 50-day EMA). Scanner endpoints derive RS / build-up flags
                # from this series at read time.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS synthetic_sector_daily_metrics (
                        sub_industry      TEXT NOT NULL,
                        metric_date       DATE NOT NULL,
                        index_value       DOUBLE PRECISION,
                        daily_return_pct  DOUBLE PRECISION,
                        avg_delivery_pct  DOUBLE PRECISION,
                        delivery_20dma    DOUBLE PRECISION,
                        breadth_50ema_pct DOUBLE PRECISION,
                        constituent_count INTEGER NOT NULL DEFAULT 0,
                        total_market_cap  DOUBLE PRECISION,
                        created_at_ms     BIGINT NOT NULL,
                        PRIMARY KEY (sub_industry, metric_date)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_synth_metrics_date "
                    "ON synthetic_sector_daily_metrics (metric_date DESC)"
                )
                # Admin-managed sub-industry overrides: lets admins add any
                # symbol to a sub-industry when Yahoo/NSE/BSE miss it.
                # These rows are merged with the Yahoo-classified `stocks`
                # rows at query time so the engine always uses both sources.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sub_industry_overrides (
                        id             TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                        symbol         TEXT NOT NULL,
                        sub_industry   TEXT NOT NULL,
                        industry       TEXT NOT NULL DEFAULT '',
                        sector         TEXT NOT NULL DEFAULT '',
                        note           TEXT NOT NULL DEFAULT '',
                        set_by         TEXT NOT NULL DEFAULT '',
                        created_at_ms  BIGINT NOT NULL,
                        updated_at_ms  BIGINT NOT NULL,
                        UNIQUE (symbol, sub_industry)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_overrides_sub_industry "
                    "ON sub_industry_overrides (sub_industry)"
                )

                # ── Shareholding pattern history ─────────────────────────
                # Quarterly shareholding-pattern snapshots per security.
                # One row per (symbol, as_on_date) combination — composite
                # PK so re-fetches naturally upsert without duplicates.
                #
                # Why store rather than always-live-fetch:
                #   1. SEBI LODR filings are immutable per quarter — once a
                #      quarter is filed, the numbers never change. Cache it
                #      forever; only the latest quarter ever needs refresh.
                #   2. NSE/BSE shareholding endpoints are rate-limited and
                #      Akamai-prone; serving from PG is ~1000x faster.
                #   3. Multi-source merge: NSE may only give us summary
                #      (Promoter/Public split), BSE gives the full FII/DII
                #      breakdown. We upsert from whichever source had data,
                #      and the most-detailed source wins per column.
                #
                # NULL is meaningful: when a source only provides
                # Promoter/Public totals (no FII/DII split), the FII and
                # DII columns are NULL. UI distinguishes "data not
                # available" from "0%" using this.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shareholding_history (
                        symbol              TEXT NOT NULL,
                        as_on_date          DATE NOT NULL,
                        promoter_pct        DOUBLE PRECISION,
                        fii_pct             DOUBLE PRECISION,
                        dii_pct             DOUBLE PRECISION,
                        public_pct          DOUBLE PRECISION,
                        govt_pct            DOUBLE PRECISION,
                        num_shareholders    BIGINT,
                        promoter_pledge_pct DOUBLE PRECISION,
                        pledged_shares      BIGINT,
                        demat_pct           DOUBLE PRECISION,
                        locked_in_pct       DOUBLE PRECISION,
                        details             JSONB,
                        source              TEXT NOT NULL,
                        fetched_at_ms       BIGINT NOT NULL,
                        PRIMARY KEY (symbol, as_on_date)
                    )
                    """
                )
                # Migrate pre-existing tables — CREATE TABLE IF NOT EXISTS
                # is a no-op once the table exists, so the XBRL-enrichment
                # columns (govt %, promoter pledge, demat/locked-in, the
                # named-holder/flags JSONB) are added idempotently here.
                for _col, _type in (
                    ("govt_pct",            "DOUBLE PRECISION"),
                    ("promoter_pledge_pct", "DOUBLE PRECISION"),
                    ("pledged_shares",      "BIGINT"),
                    ("demat_pct",           "DOUBLE PRECISION"),
                    ("locked_in_pct",       "DOUBLE PRECISION"),
                    ("details",             "JSONB"),
                ):
                    cur.execute(
                        f"ALTER TABLE shareholding_history "
                        f"ADD COLUMN IF NOT EXISTS {_col} {_type}"
                    )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_shareholding_symbol_date "
                    "ON shareholding_history (symbol, as_on_date DESC)"
                )

                # ── Quarterly financial results (SEBI Reg-33 XBRL) ────────
                # The full P&L per quarter that Yahoo collapses: revenue,
                # the complete expense breakdown, tax split, PAT, basic +
                # diluted EPS, and segment results — for each filed basis
                # (standalone / consolidated). One row per
                # (symbol, period_end, basis). line_items/segments are JSONB
                # because the set of reported lines varies by company/sector.
                # Immutable once filed, so cached like the shareholding data.
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS financial_results (
                        symbol         TEXT NOT NULL,
                        period_end     DATE NOT NULL,
                        basis          TEXT NOT NULL,
                        period_type    TEXT,
                        audited        BOOLEAN,
                        relating_to    TEXT,
                        multi_segment  BOOLEAN,
                        report_format  TEXT,
                        line_items     JSONB NOT NULL,
                        segments       JSONB,
                        source         TEXT NOT NULL,
                        fetched_at_ms  BIGINT NOT NULL,
                        PRIMARY KEY (symbol, period_end, basis)
                    )
                    """
                )
                # Migrate pre-existing tables (CREATE IF NOT EXISTS is a
                # no-op once the table exists) — keeps the schema additive.
                cur.execute(
                    "ALTER TABLE financial_results "
                    "ADD COLUMN IF NOT EXISTS report_format TEXT"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_finresults_symbol_date "
                    "ON financial_results (symbol, period_end DESC)"
                )

                # ── Symbol quarantine ─────────────────────────────────────
                # Tracks symbols where every provider in the price chain
                # has returned empty results for multiple consecutive
                # scans. After a configurable threshold of consecutive
                # failures with zero successes recorded, the symbol is
                # auto-quarantined and silently skipped by the scanner
                # instead of cluttering the error panel.
                #
                # Why this exists:
                #   Universe lists accumulate dead symbols over time —
                #   genuinely delisted (JSWISPL merged into JSWSTEEL),
                #   SME-only listings that aren't on the main board
                #   (DRONEACHARYA), or low-volume names with no recent
                #   trades (SAMEERA). Each one wastes a fetch attempt
                #   per scan AND shows up as an "error" the user has to
                #   visually filter through. The registry can't fix this
                #   — these symbols ARE the canonical NSE ticker; the
                #   underlying security just has no data anywhere.
                #
                #   The quarantine is empirical: if NSE + BSE + Yahoo +
                #   TwelveData + Stooq all return zero bars across N
                #   consecutive attempts (default 3), the system learns
                #   "this symbol has no usable data" and stops surfacing
                #   it as a scanner error. Quarantine auto-expires after
                #   30 days so re-listings get rediscovered.
                #
                #   `manual_override = TRUE` means an admin forced the
                #   release; we skip auto-quarantining it again for
                #   that session (so an operator can investigate without
                #   the system instantly re-quarantining behind them).
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS symbol_quarantine (
                        symbol                 TEXT PRIMARY KEY,
                        first_failed_at_ms     BIGINT NOT NULL,
                        last_attempted_at_ms   BIGINT NOT NULL,
                        last_success_at_ms     BIGINT,
                        consecutive_failures   INTEGER NOT NULL DEFAULT 0,
                        total_failures         INTEGER NOT NULL DEFAULT 0,
                        total_successes        INTEGER NOT NULL DEFAULT 0,
                        quarantined            BOOLEAN NOT NULL DEFAULT FALSE,
                        quarantined_at_ms      BIGINT,
                        reason                 TEXT NOT NULL DEFAULT '',
                        manual_override        BOOLEAN NOT NULL DEFAULT FALSE
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_quarantine_active "
                    "ON symbol_quarantine (quarantined) WHERE quarantined = TRUE"
                )
        _SCHEMA_READY = True


def list_users() -> list[dict[str, Any]]:
    ensure_primary_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, name, google_sub, picture_url, auth_provider,
                       is_admin, created_at, updated_at, last_login_at
                  FROM app_users
              ORDER BY last_login_at DESC, created_at DESC
                """
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def upsert_google_user(*, email: str, name: str, google_sub: str, picture_url: str, is_admin: bool) -> dict[str, Any]:
    ensure_primary_schema()
    current = now_ms()
    user_id = str(uuid.uuid4())
    display_name = (name or email.split("@")[0]).strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app_users
                    (id, email, name, google_sub, picture_url, auth_provider,
                     is_admin, created_at, updated_at, last_login_at)
                VALUES
                    (%(id)s, %(email)s, %(name)s, %(google_sub)s, %(picture_url)s, 'google',
                     %(is_admin)s, %(created_at)s, %(updated_at)s, %(last_login_at)s)
                ON CONFLICT (google_sub) DO UPDATE SET
                    email = EXCLUDED.email,
                    name = EXCLUDED.name,
                    picture_url = EXCLUDED.picture_url,
                    is_admin = EXCLUDED.is_admin,
                    updated_at = EXCLUDED.updated_at,
                    last_login_at = EXCLUDED.last_login_at
                RETURNING id, email, name, google_sub, picture_url, auth_provider,
                          is_admin, created_at, updated_at, last_login_at
                """,
                {
                    "id": user_id,
                    "email": email,
                    "name": display_name,
                    "google_sub": google_sub,
                    "picture_url": picture_url,
                    "is_admin": is_admin,
                    "created_at": current,
                    "updated_at": current,
                    "last_login_at": current,
                },
            )
            row = cur.fetchone()
    if not row:
        raise RuntimeError("Failed to upsert Google user.")
    return dict(row)
