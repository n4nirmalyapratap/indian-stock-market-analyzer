from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any

import psycopg
from psycopg.rows import dict_row

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def _database_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required. PostgreSQL is the system of record for app auth data.")
    return url


def get_conn() -> psycopg.Connection[Any]:
    return psycopg.connect(_database_url(), row_factory=dict_row)


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
