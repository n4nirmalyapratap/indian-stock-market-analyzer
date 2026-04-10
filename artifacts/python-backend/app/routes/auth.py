"""
Custom email + password auth routes.

Endpoints (all public — no auth required):
  POST /api/auth/register   { email, password, name? }  → { token, user }
  POST /api/auth/login      { email, password }          → { token, user }

Tokens are HS256 JWTs signed with SESSION_SECRET (30-day expiry).
The ClerkAuthMiddleware accepts these tokens alongside Clerk RS256 tokens.

Database: SQLite at /app/users.db (created automatically on first call).
"""

import os
import time
import uuid
import sqlite3
import logging

import bcrypt
import jwt
from fastapi import APIRouter

from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "users.db")


# ── Database helpers ──────────────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           TEXT PRIMARY KEY,
            email        TEXT UNIQUE NOT NULL,
            name         TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            created_at   INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── JWT helpers ───────────────────────────────────────────────────────────────

def _secret() -> str:
    return os.environ.get("SESSION_SECRET", "changeme-in-production")


def _make_token(user_id: str, email: str, name: str) -> str:
    payload = {
        "sub":   user_id,
        "email": email,
        "name":  name,
        "type":  "custom",          # distinguishes from Clerk RS256 tokens
        "iat":   int(time.time()),
        "exp":   int(time.time()) + 86400 * 30,   # 30 days
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def verify_custom_token(token: str) -> dict:
    """
    Verify a custom HS256 token. Raises jwt.* exceptions on failure.
    Called by ClerkAuthMiddleware.
    """
    return jwt.decode(token, _secret(), algorithms=["HS256"])


# ── Request / Response models ─────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:    str
    password: str
    name:     str = ""


class LoginRequest(BaseModel):
    email:    str
    password: str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register")
async def register(req: RegisterRequest):
    _init_db()

    email = req.email.strip().lower()
    name  = req.name.strip() or email.split("@")[0]

    if not email or "@" not in email:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Enter a valid email address")

    if len(req.password) < 6:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    conn = _get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="An account with this email already exists. Please log in instead.")

        user_id       = str(uuid.uuid4())
        password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()

        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, name, password_hash, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()

    token = _make_token(user_id, email, name)
    logger.info("New user registered: %s", email)
    return {"token": token, "user": {"id": user_id, "email": email, "name": name}}


@router.post("/login")
async def login(req: LoginRequest):
    _init_db()

    email = req.email.strip().lower()

    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT id, email, name, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="No account found with this email. Please register first.")

    if not bcrypt.checkpw(req.password.encode(), row["password_hash"].encode()):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Incorrect password. Please try again.")

    token = _make_token(row["id"], row["email"], row["name"])
    logger.info("User logged in: %s", email)
    return {"token": token, "user": {"id": row["id"], "email": row["email"], "name": row["name"]}}
