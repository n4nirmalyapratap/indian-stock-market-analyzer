"""Groww broker client — placeholder until their public API reaches GA.

Status (May 2026)
-----------------
Groww's trading API is in closed beta. Their developer portal lists
"coming soon" for retail access. This module implements the same
interface as the other brokers so:

  * The Settings page can still show a Groww card (already wired in
    Phase 3's BROKER_DEFINITIONS).
  * When GA lands, only this file changes — no upstream refactor.
  * Phase 9's PriceService wiring works for Groww the same as the
    others (returns None ⇒ chain falls through cleanly).

Until then `test_connection` returns False with a clear "not yet
generally available" message, and `get_quote` / `get_historical`
both return None / [] so the user-priority tier in PriceService
falls through to the next configured broker (or to NSE/BSE/Yahoo).
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("groww_service")


async def test_connection(creds: dict) -> tuple[bool, str]:
    return (
        False,
        "Groww's public trading API is not yet generally available. "
        "Your credentials are stored encrypted and will activate "
        "automatically when Groww ships their public API."
    )


async def get_quote(symbol: str, creds: dict) -> Optional[dict]:
    # No-op until GA. Returns None so PriceService's chain proceeds.
    return None


async def get_historical(symbol: str, days: int = 90, creds: dict | None = None) -> list[dict]:
    return []
