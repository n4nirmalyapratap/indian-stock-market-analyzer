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
