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
import sqlite3
import logging
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

_DATA_DIR = os.environ.get(
    "DATA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."),
)
_DB_PATH = os.path.join(_DATA_DIR, "users.db")

_lock = threading.Lock()

# ── KNOWN SECRETS (shown in admin UI with descriptions) ───────────────────────

KNOWN_SECRETS: list[dict] = [
    {
        "key":         "TELEGRAM_BOT_TOKEN",
        "description": "Telegram bot token from @BotFather",
        "masked":      True,
    },
    {
        "key":         "WHATSAPP_ENABLED",
        "description": "Set to 'true' to enable the WhatsApp bot integration",
        "masked":      False,
    },
    {
        "key":         "AI_INTEGRATIONS_OPENROUTER_API_KEY",
        "description": "OpenRouter API key (free-tier OK). Used for Gemma 4 / Qwen / Llama models",
        "masked":      True,
    },
    {
        "key":         "AI_INTEGRATIONS_OPENROUTER_BASE_URL",
        "description": "OpenRouter base URL (leave blank to use Replit proxy default)",
        "masked":      False,
    },
    {
        "key":         "AI_INTEGRATIONS_OPENAI_API_KEY",
        "description": "OpenAI API key. Used as the final fallback for the AI client",
        "masked":      True,
    },
    {
        "key":         "AI_INTEGRATIONS_OPENAI_BASE_URL",
        "description": "OpenAI base URL (leave blank to use Replit proxy default)",
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
]

_KNOWN_MAP = {s["key"]: s for s in KNOWN_SECRETS}


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table() -> None:
    with _lock:
        conn = _get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_secrets (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                masked      INTEGER NOT NULL DEFAULT 1,
                updated_at  INTEGER NOT NULL
            )
        """)
        conn.commit()
        conn.close()


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
        conn = _get_conn()
        row = conn.execute(
            "SELECT value FROM app_secrets WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
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
        conn = _get_conn()
        conn.execute("""
            INSERT INTO app_secrets (key, value, description, masked, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                description= excluded.description,
                masked     = excluded.masked,
                updated_at = excluded.updated_at
        """, (key, value, desc, int(msk), now))
        conn.commit()
        conn.close()


def delete_secret(key: str) -> bool:
    """Delete a DB secret (env var fallback still applies after deletion)."""
    _ready()
    with _lock:
        conn = _get_conn()
        cur = conn.execute("DELETE FROM app_secrets WHERE key = ?", (key,))
        conn.commit()
        conn.close()
        return cur.rowcount > 0


def list_secrets(reveal: bool = False) -> list[dict]:
    """
    Return all known + custom secrets.
    DB values take priority; env vars fill in gaps.
    If `reveal=False`, masked values are replaced with '***'.
    """
    _ready()
    conn = _get_conn()
    db_rows = {
        r["key"]: dict(r)
        for r in conn.execute("SELECT * FROM app_secrets").fetchall()
    }
    conn.close()

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
