import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


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
