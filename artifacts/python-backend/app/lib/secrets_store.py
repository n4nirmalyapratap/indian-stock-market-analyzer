"""
secrets_store.py — Centralised secret/config management.

Priority:
  1. Database (admin-managed, hot-reloadable)
  2. Environment variable (fallback / bootstrap)

Usage:
    from app.lib.secrets_store import get_secret, set_secret

    token = get_secret("TELEGRAM_BOT_TOKEN")           # DB first, then env
    get_secret("MY_KEY", default="fallback-value")     # custom default
"""

from __future__ import annotations

import os
import logging
import threading
import time

log = logging.getLogger(__name__)
from app.lib.auth_store import ensure_primary_schema, get_conn

_lock = threading.Lock()

# ── KNOWN SECRETS (shown in admin UI with descriptions) ───────────────────────

KNOWN_SECRETS: list[dict] = [
    # ── Market Data ──────────────────────────────────────────────────────────
    {
        "key":         "FRED_API_KEY",
        "description": "FRED (St. Louis Fed) API key. Free at fred.stlouisfed.org/docs/api/api_key.html. "
                       "Enables Repo Rate, CPI, IIP, and India 10Y Yield tiles in Macro Pulse. "
                       "Without this key, World Bank annual data is used as fallback for CPI/IIP/GDP.",
        "masked":      True,
    },
    # ── AI / LLM ─────────────────────────────────────────────────────────────
    {
        "key":         "AI_INTEGRATIONS_OPENROUTER_API_KEY",
        "description": "OpenRouter API key. Get one free at openrouter.ai. Powers the AI Analyst and Macro commentary.",
        "masked":      True,
    },
    {
        "key":         "AI_INTEGRATIONS_OPENROUTER_BASE_URL",
        "description": "OpenRouter base URL (default: https://openrouter.ai/api/v1). Leave blank on Replit to use the built-in proxy.",
        "masked":      False,
    },
    {
        "key":         "AI_INTEGRATIONS_OPENAI_API_KEY",
        "description": "OpenAI API key. Used as the final fallback for the AI client if OpenRouter is unavailable.",
        "masked":      True,
    },
    {
        "key":         "AI_INTEGRATIONS_OPENAI_BASE_URL",
        "description": "OpenAI base URL (leave blank to use api.openai.com).",
        "masked":      False,
    },
    {
        "key":         "AI_MODEL",
        "description": "Primary OpenRouter model ID (default: google/gemma-4-31b-it:free)",
        "masked":      False,
    },
    {
        "key":         "AI_FALLBACK_MODEL",
        "description": "Fallback OpenRouter model ID (default: qwen/qwen3-next-80b-a3b-instruct:free)",
        "masked":      False,
    },
    {
        "key":         "AI_ANALYST_DAILY_QUOTA",
        "description": "Deep AI Analyst: max fresh analyses per user per IST day (default: 3). Cached reports don't count.",
        "masked":      False,
    },
    # ── Notifications ────────────────────────────────────────────────────────
    {
        "key":         "TELEGRAM_BOT_TOKEN",
        "description": "Telegram bot token from @BotFather. Leave blank to disable Telegram alerts.",
        "masked":      True,
    },
    {
        "key":         "WHATSAPP_ENABLED",
        "description": "Set to 'true' to enable the WhatsApp bot integration (requires Twilio setup).",
        "masked":      False,
    },
]

_KNOWN_MAP = {s["key"]: s for s in KNOWN_SECRETS}


# ── DB helpers ────────────────────────────────────────────────────────────────

def _ensure_table() -> None:
    with _lock:
        ensure_primary_schema()


_table_ready = False


def _ready() -> None:
    global _table_ready
    if not _table_ready:
        _ensure_table()
        _table_ready = True


# ── Public API ────────────────────────────────────────────────────────────────

def get_secret(key: str, default: str = "") -> str:
    """
    Return the value for `key`.
    Priority: DB value → environment variable → `default`.
    """
    try:
        _ready()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM app_secrets WHERE key = %s", (key,))
                row = cur.fetchone()
        if row and row["value"]:
            return row["value"]
    except Exception as exc:
        log.warning("secrets_store: DB read failed for %s: %s", key, exc)

    return os.environ.get(key, default)


def set_secret(key: str, value: str, description: str = "", masked: bool = True) -> None:
    """Upsert a secret in the DB."""
    _ready()
    meta = _KNOWN_MAP.get(key, {})
    desc = description or meta.get("description", "")
    msk  = masked if not meta else meta.get("masked", masked)
    now  = int(time.time())

    with _lock:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
            INSERT INTO app_secrets (key, value, description, masked, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(key) DO UPDATE SET
                value = EXCLUDED.value,
                description = EXCLUDED.description,
                masked = EXCLUDED.masked,
                updated_at = EXCLUDED.updated_at
        """, (key, value, desc, bool(msk), now))


def delete_secret(key: str) -> bool:
    """Delete a DB secret (env var fallback still applies after deletion)."""
    _ready()
    with _lock:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM app_secrets WHERE key = %s", (key,))
                return cur.rowcount > 0


def list_secrets(reveal: bool = False) -> list[dict]:
    """
    Return all known + custom secrets.
    DB values take priority; env vars fill in gaps.
    If `reveal=False`, masked values are replaced with '***'.
    """
    _ready()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM app_secrets")
            db_rows = {
                r["key"]: dict(r)
                for r in cur.fetchall()
            }

    result: list[dict] = []
    seen: set[str] = set()

    # Known secrets first (in defined order)
    for meta in KNOWN_SECRETS:
        key = meta["key"]
        seen.add(key)
        db = db_rows.get(key)
        env_val = os.environ.get(key, "")

        source = "db" if (db and db["value"]) else ("env" if env_val else "unset")
        raw    = (db["value"] if db and db["value"] else env_val)
        masked = bool(meta.get("masked", True))

        result.append({
            "key":         key,
            "value":       ("***" if masked and not reveal and raw else raw),
            "description": meta.get("description", ""),
            "masked":      masked,
            "source":      source,
            "updated_at":  db["updated_at"] if db else None,
        })

    # Custom (user-added) secrets from DB not in KNOWN_SECRETS
    for key, db in db_rows.items():
        if key in seen:
            continue
        raw    = db["value"]
        masked = bool(db["masked"])
        result.append({
            "key":         key,
            "value":       ("***" if masked and not reveal and raw else raw),
            "description": db["description"],
            "masked":      masked,
            "source":      "db",
            "updated_at":  db["updated_at"],
        })

    return result
