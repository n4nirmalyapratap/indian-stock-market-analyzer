"""
Safety regression tests for the Deep AI Analyst pipeline.

These lock in two SEBI / quota guarantees that are easy to break with
future edits:

  1. SEBI compliance scrub (`_scrub_report`) — every prohibited phrase
     pattern in `_ADVICE_REPLACEMENTS` is rewritten away when it appears
     in any user-visible field of a synthetic report.

  2. Atomic quota reservation (`_try_reserve_quota`) — under N concurrent
     callers for the same user with limit=3, exactly 3 reservations
     succeed (closes the check-then-increment race fixed during code
     review).

  3. Per-user cache isolation (`get_cached_report`) — a report saved for
     user A is not returned when looked up for user B on the same ticker
     / IST day.
"""
from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from app.services import ai_analyst_service as ai


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_db():
    """Provide a per-test user-id namespace inside the shared Postgres.

    The service now writes to Postgres tables managed centrally by
    app.lib.auth_store.ensure_primary_schema(). We can't (cheaply) give
    each test a brand-new database, but every row written by the saved
    store and quota table is keyed on ``user_id`` — so generating a fresh
    random ``user_id`` per test and cleaning up its rows at teardown is
    enough to keep tests independent.

    Tests requiring this fixture are skipped if ``DATABASE_URL`` is unset
    (e.g. CI without a Postgres service) — the surrounding code paths
    can still be unit-tested without DB access.
    """
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set; skipping Postgres-backed test.")

    # Make sure schema exists.
    from app.lib.auth_store import ensure_primary_schema, get_conn
    ensure_primary_schema()

    # Yield a unique prefix so tests can build user-ids like
    # f"{prefix}-userA" or pass the prefix directly as the user-id.
    prefix = f"test-{uuid.uuid4().hex}"
    yield prefix

    # Teardown: scrub anything written under this prefix.
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM ai_analyst_saved WHERE user_id LIKE %s",
                (f"{prefix}%",),
            )
            cur.execute(
                "DELETE FROM ai_analyst_quota WHERE user_id LIKE %s",
                (f"{prefix}%",),
            )
        conn.commit()


# ── 1. SEBI compliance scrub ─────────────────────────────────────────────────


# Build an exhaustive list of probe phrases by enumerating every
# alternative in every regex of `_ADVICE_REPLACEMENTS`. Each block below
# corresponds to one pattern in that table, in source order. The probe
# is the substring we expect to NOT find after `_scrub_report`.
def _build_probes() -> list[str]:
    from itertools import product
    probes: list[str] = []

    # 1. \byou (should|must|need to|ought to) (buy|sell|hold|short|exit|
    #         enter|invest|accumulate|book|trim|add|reduce)\b
    for adv, verb in product(
        ["should", "must", "need to", "ought to"],
        ["buy", "sell", "hold", "short", "exit", "enter",
         "invest", "accumulate", "book", "trim", "add", "reduce"],
    ):
        probes.append(f"you {adv} {verb}")

    # 2. \b(I|we|our team) (recommend|advise|suggest)s? (buying|selling|
    #         holding|shorting|accumulating|booking|trimming|adding|reducing)\b
    for subj, verb, gerund in product(
        ["I", "we", "our team"],
        ["recommend", "advise", "suggest"],
        ["buying", "selling", "holding", "shorting", "accumulating",
         "booking", "trimming", "adding", "reducing"],
    ):
        # Cover both the bare and "+s" inflections (recommends / advises / suggests).
        probes.append(f"{subj} {verb} {gerund}")
        probes.append(f"{subj} {verb}s {gerund}")

    # 3. \b(strong|firm|clear|sure-shot|sureshot)\s+(buy|sell|hold)\b
    for adj, verb in product(
        ["strong", "firm", "clear", "sure-shot", "sureshot"],
        ["buy", "sell", "hold"],
    ):
        probes.append(f"{adj} {verb}")

    # 4. \bbuy (now|today|here|the dip|on dips|at cmp|at this level)\b
    for tail in ["now", "today", "here", "the dip", "on dips",
                 "at cmp", "at this level"]:
        probes.append(f"buy {tail}")

    # 5. \bsell (now|today|here|on rallies|at cmp|at this level)\b
    for tail in ["now", "today", "here", "on rallies",
                 "at cmp", "at this level"]:
        probes.append(f"sell {tail}")

    # 6. \b(enter|exit|book profits?|book losses?)\s+(now|today|here|
    #         on dips|on rallies|at cmp|at this level)\b
    for verb, tail in product(
        ["enter", "exit", "book profit", "book profits",
         "book loss", "book losses"],
        ["now", "today", "here", "on dips", "on rallies",
         "at cmp", "at this level"],
    ):
        probes.append(f"{verb} {tail}")

    # 7. \b(must|should)\s+(accumulate|hold|exit|trim|book)\b
    for adv, verb in product(
        ["must", "should"],
        ["accumulate", "hold", "exit", "trim", "book"],
    ):
        probes.append(f"{adv} {verb}")

    # 8. \b(go|going)\s+(long|short)\b
    for verb, side in product(["go", "going"], ["long", "short"]):
        probes.append(f"{verb} {side}")

    # 9. \b(guaranteed|assured|risk[-\s]?free)\s+(profit|return|gain|win)s?\b
    for adj, noun in product(
        ["guaranteed", "assured", "risk-free", "risk free", "riskfree"],
        ["profit", "return", "gain", "win"],
    ):
        probes.append(f"{adj} {noun}")
        probes.append(f"{adj} {noun}s")

    # 10. \b(can[''']?t lose|sure[-\s]?shot|sureshot|no[-\s]?brainer)\b
    for token in ["cant lose", "can't lose", "can\u2019t lose",
                  "sure-shot", "sure shot", "sureshot",
                  "no-brainer", "no brainer", "nobrainer"]:
        probes.append(token)

    # 11. \bmultibagger\b
    probes.append("multibagger")

    # 12. \b(target price is|price target of)\b
    probes.append("target price is")
    probes.append("price target of")

    return probes


_PROHIBITED_PROBES = _build_probes()


def test_probe_table_covers_every_pattern_in_advice_replacements():
    """Guard rail: if a new regex is added to `_ADVICE_REPLACEMENTS` without
    a matching block of probes here, this test fails so future maintainers
    are forced to extend the test coverage. Conservative lower bound: at
    least one probe per current pattern."""
    assert len(ai._ADVICE_REPLACEMENTS) == 12, (
        "The number of SEBI scrub patterns changed. Update _build_probes() "
        "in this file to enumerate every alternative of the new/removed "
        "pattern, then update this assertion."
    )
    # Every probe must actually be matched by at least one pattern —
    # otherwise the probe is dead weight that won't catch regressions.
    import re
    for probe in _PROHIBITED_PROBES:
        sentence = f"In context, {probe}, end."
        assert any(pat.search(sentence) for pat, _ in ai._ADVICE_REPLACEMENTS), (
            f"Probe {probe!r} is not matched by any pattern in "
            f"_ADVICE_REPLACEMENTS — the probe is stale."
        )


def _make_report_containing(phrase: str) -> dict:
    """Synthetic report that smuggles `phrase` into every user-visible field."""
    sentence = f"This research note states that {phrase} per the desk."
    return {
        "ticker":      "TEST",
        "verdict":     "HOLD",
        "confidence":  "MEDIUM",
        "headline":    sentence,
        "priceTarget": sentence,
        "horizon":     sentence,
        "keyRisks":    [sentence, f"Even though {phrase}, watch macro."],
        "analysts": {
            "fundamentals": sentence,
            "news":         sentence,
            "technicals":   sentence,
            "macro":        sentence,
        },
        "debate": {
            "bull": sentence,
            "bear": sentence,
        },
    }


def _all_strings(report: dict):
    yield report["headline"]
    yield report["priceTarget"]
    yield report["horizon"]
    yield from report["keyRisks"]
    yield from report["analysts"].values()
    yield from report["debate"].values()


@pytest.mark.parametrize("phrase", _PROHIBITED_PROBES)
def test_scrub_report_removes_every_prohibited_phrase(phrase: str):
    scrubbed = ai._scrub_report(_make_report_containing(phrase))
    for s in _all_strings(scrubbed):
        assert phrase.lower() not in s.lower(), (
            f"_scrub_report left prohibited phrase {phrase!r} in: {s!r}"
        )


def test_scrub_report_preserves_innocuous_text():
    """Sanity: scrubbing a clean report doesn't mangle benign content."""
    benign = "The bull case sees support near ₹1,200 with rising volumes."
    rpt = _make_report_containing("")  # phrase is empty, so plain template
    rpt["headline"] = benign
    rpt["analysts"]["technicals"] = benign
    out = ai._scrub_report(rpt)
    assert out["headline"] == benign
    assert out["analysts"]["technicals"] == benign


# ── 2. Atomic quota reservation under concurrency ────────────────────────────


def test_try_reserve_quota_is_atomic_under_concurrency(isolated_db):
    """N threads racing to reserve a slot for the same user with limit=3
    should yield exactly 3 successes — never 4, never 2."""
    user = f"{isolated_db}-race-user"
    n_workers = 20
    limit = 3

    barrier = threading.Barrier(n_workers)

    def attempt() -> bool:
        # All threads line up so they hammer the DB at the same moment.
        barrier.wait(timeout=5)
        return ai._try_reserve_quota(user, limit=limit)

    with ThreadPoolExecutor(max_workers=n_workers) as ex:
        results = [f.result() for f in as_completed(
            [ex.submit(attempt) for _ in range(n_workers)]
        )]

    successes = sum(1 for r in results if r)
    assert successes == limit, (
        f"Expected exactly {limit} successful reservations under "
        f"concurrent load, got {successes}. Results: {results}"
    )

    # And the persisted counter agrees.
    quota = ai.get_quota(user)
    assert quota["used"] == limit
    assert quota["remaining"] == 0

    # Any further attempt is rejected.
    assert ai._try_reserve_quota(user, limit=limit) is False


# ── 3. Per-user cache isolation ──────────────────────────────────────────────


def test_get_cached_report_is_per_user(isolated_db):
    """A report saved for user A must not be served to user B."""
    ticker = "RELIANCE"
    user_a = f"{isolated_db}-userA"
    user_b = f"{isolated_db}-userB"
    report_a = {
        "ticker": ticker, "verdict": "BUY", "headline": "User A's report",
    }
    ai._save_report(
        ticker=ticker, user_id=user_a, report=report_a,
        models=["m"], sources=["s"], wall_clock_ms=100,
    )

    # User A sees their saved report.
    got_a = ai.get_cached_report(ticker, user_a)
    assert got_a is not None
    assert got_a["headline"] == "User A's report"
    assert got_a["cached"] is True

    # User B sees nothing for the same ticker.
    got_b = ai.get_cached_report(ticker, user_b)
    assert got_b is None

    # User B saving their own report does not overwrite user A's row.
    report_b = {
        "ticker": ticker, "verdict": "SELL", "headline": "User B's report",
    }
    ai._save_report(
        ticker=ticker, user_id=user_b, report=report_b,
        models=["m"], sources=["s"], wall_clock_ms=100,
    )
    again_a = ai.get_cached_report(ticker, user_a)
    again_b = ai.get_cached_report(ticker, user_b)
    assert again_a is not None and again_a["headline"] == "User A's report"
    assert again_b is not None and again_b["headline"] == "User B's report"
