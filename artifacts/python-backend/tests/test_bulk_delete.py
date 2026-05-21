"""
Tests for bulk-delete service helpers — the destructive paths.

Saved analyses: covered with a Postgres skip-guard (uses the real PG schema
via auth_store.ensure_primary_schema). Portfolio transactions: same.

Both helpers must:
  * Refuse to delete rows the caller doesn't own (user_id mismatch)
  * Handle empty / nullish input cleanly
  * Reverse cash impact atomically (portfolio_tx only)
"""
from __future__ import annotations

import os
import uuid

import pytest

# These tests need real Postgres because the helpers do array-binding
# (ANY(%s)) and an atomic UPDATE; mocking them out would test nothing.
pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; skipping Postgres-backed bulk-delete tests.",
)


from app.services import ai_analyst_service as ai           # noqa: E402
from app.services import portfolio_service  as ps           # noqa: E402


# ── ai_analyst_service.delete_saved_bulk ─────────────────────────────────────

def _make_saved_rows(user_id: str, n: int) -> list[int]:
    """Insert N dummy single-stock saved rows for `user_id`. Returns the ids."""
    ids: list[int] = []
    for i in range(n):
        # Unique scope_key per row so the UNIQUE(user_id, scope_type, scope_key)
        # constraint doesn't collapse them onto each other.
        sk = f"DUMMY-{uuid.uuid4().hex[:8]}"
        new_id = ai._upsert_saved(
            user_id, "single", sk, [sk], None,
            "HOLD", "LOW", f"test row {i}", {"ticker": sk, "verdict": "HOLD"},
            models=[], sources=[], wall_clock_ms=0,
        )
        ids.append(new_id)
    return ids


def test_delete_saved_bulk_empty_input_returns_zero():
    assert ai.delete_saved_bulk("u1", []) == 0
    assert ai.delete_saved_bulk("u1", [None, None]) == 0  # type: ignore[list-item]


def test_delete_saved_bulk_deletes_my_rows():
    user_id = f"bulktest-{uuid.uuid4().hex}"
    ids = _make_saved_rows(user_id, 3)
    deleted = ai.delete_saved_bulk(user_id, ids)
    assert deleted == 3
    # Subsequent delete is a no-op (already gone)
    assert ai.delete_saved_bulk(user_id, ids) == 0


def test_delete_saved_bulk_skips_rows_not_owned_by_caller():
    """A user can't delete another user's saved analyses even if they
    guess the id."""
    user_a = f"bulkA-{uuid.uuid4().hex}"
    user_b = f"bulkB-{uuid.uuid4().hex}"
    ids_a = _make_saved_rows(user_a, 2)
    # user_b tries to delete user_a's rows
    deleted = ai.delete_saved_bulk(user_b, ids_a)
    assert deleted == 0
    # user_a can still delete their own
    deleted2 = ai.delete_saved_bulk(user_a, ids_a)
    assert deleted2 == 2


# ── portfolio_service.delete_transactions_bulk ───────────────────────────────

def test_delete_transactions_bulk_reverses_cash_atomically():
    """BUY ₹2,000 + BUY ₹3,000 then bulk-delete both — cash must return to
    the pre-trade balance (within float epsilon)."""
    user_id = f"bulkpf-{uuid.uuid4().hex}"
    p = ps.create_portfolio(user_id, "Bulk Test", cash=10_000.0)
    pid = p["id"]

    tx1 = ps.add_transaction(user_id, pid, symbol="RELIANCE",
                             side="BUY", qty=1, price=2000)
    tx2 = ps.add_transaction(user_id, pid, symbol="TCS",
                             side="BUY", qty=1, price=3000)
    assert tx1 is not None and tx2 is not None

    # Cash should now be 10_000 - 2000 - 3000 = 5_000
    pf_after_buys = ps.get_portfolio(user_id, pid)
    assert abs(pf_after_buys["cash"] - 5_000.0) < 1e-6

    res = ps.delete_transactions_bulk(user_id, pid, [tx1["id"], tx2["id"]])
    assert res["deleted"] == 2
    assert res["skipped"] == 0

    pf_after_delete = ps.get_portfolio(user_id, pid)
    assert abs(pf_after_delete["cash"] - 10_000.0) < 1e-6

    # Cleanup
    ps.delete_portfolio(user_id, pid)


def test_delete_transactions_bulk_skips_rows_from_other_portfolios():
    """tx ids belonging to another portfolio in the same user must be
    ignored — the WHERE portfolio_id = %s clause keeps them safe."""
    user_id = f"bulkpf-{uuid.uuid4().hex}"
    p_a = ps.create_portfolio(user_id, "A", cash=5_000.0)
    p_b = ps.create_portfolio(user_id, "B", cash=5_000.0)
    pid_a, pid_b = p_a["id"], p_b["id"]

    tx_a = ps.add_transaction(user_id, pid_a, symbol="RELIANCE",
                              side="BUY", qty=1, price=2000)
    assert tx_a is not None

    # Try to delete tx_a via portfolio B — must be skipped.
    res = ps.delete_transactions_bulk(user_id, pid_b, [tx_a["id"]])
    assert res["deleted"] == 0
    assert res["skipped"] == 1

    # Portfolio B's cash must be untouched.
    assert abs(ps.get_portfolio(user_id, pid_b)["cash"] - 5_000.0) < 1e-6

    # Cleanup
    ps.delete_portfolio(user_id, pid_a)
    ps.delete_portfolio(user_id, pid_b)


def test_delete_transactions_bulk_empty_input():
    user_id = f"bulkpf-{uuid.uuid4().hex}"
    p = ps.create_portfolio(user_id, "Empty Bulk", cash=1000.0)
    pid = p["id"]
    res = ps.delete_transactions_bulk(user_id, pid, [])
    assert res == {"deleted": 0, "skipped": 0}
    ps.delete_portfolio(user_id, pid)


def test_delete_transactions_bulk_unknown_portfolio():
    """Bulk-delete against a portfolio that doesn't exist returns the
    'not found' shape without touching any rows."""
    res = ps.delete_transactions_bulk("nobody", "non-existent-pid", ["x", "y"])
    assert res.get("error") == "portfolio not found"
    assert res["deleted"] == 0
