import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Load .env from project root (two levels up from artifacts/python-backend) ──
# This lets developers set FRED_API_KEY, OpenRouter keys, etc. in a single
# .env file at the repo root without touching shell profiles or Replit Secrets.
# Environment variables already set in the process take priority (override=False).
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
    if os.path.isfile(_env_path):
        load_dotenv(_env_path, override=False)
        print(f"[startup] Loaded .env from {os.path.abspath(_env_path)}")
    # Also try a .env right next to run.py (artifacts/python-backend/.env)
    _local_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(_local_env):
        load_dotenv(_local_env, override=False)
        print(f"[startup] Loaded .env from {os.path.abspath(_local_env)}")
except ImportError:
    print("[startup] python-dotenv not installed — skipping .env load (pip install python-dotenv)")


def _ensure_spacy_model() -> None:
    """Download en_core_web_sm if it is not already installed."""
    try:
        import spacy
        spacy.load("en_core_web_sm")
    except OSError:
        print("[startup] Downloading spaCy model en_core_web_sm …")
        subprocess.run(
            [sys.executable, "-m", "spacy", "download", "en_core_web_sm",
             "--break-system-packages"],
            check=False,
        )


_ensure_spacy_model()

# ── Set up in-memory ring-buffer log handler BEFORE uvicorn starts ────────────
# This captures all Python log records so /api/admin/logs can return them.
from app.services.log_buffer import setup_ring_buffer
setup_ring_buffer()

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8090))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
