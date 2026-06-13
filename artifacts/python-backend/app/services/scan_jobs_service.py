"""Background scan job tracking — in-memory.

Why this exists
---------------
The synchronous /scanners/{id}/run endpoint blocks the HTTP request for
the full scan duration. With Hidden Gems scanners (which trigger a
~15-90s Yahoo fundamentals prefetch on cold-cache), the UI is just a
"Running…" spinner with no feedback, and if the user navigates away
the scan result is lost.

This service decouples the two concerns:
  * /scanners/{id}/run-job  → creates a job, kicks off the scan as a
                              background asyncio task, returns {jobId}
                              IMMEDIATELY. Client doesn't have to wait.
  * /scanners/jobs/{jobId}  → returns current job state — progress
                              counters during running, final result
                              once done. Polled by the frontend.

The background task runs to completion regardless of whether the client
is still polling, so a user can start a long scan, navigate away, and
come back to see results.

Persistence note
----------------
Jobs are stored in a module-level dict. They survive across HTTP
requests (same Python process) but are lost on backend restart. That's
acceptable for v1 — scans are <2 min in practice, so the worst case is
"restart kills an in-flight job, user re-runs". A PG-backed job table
would be a separate hardening pass.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Optional

logger = logging.getLogger("scan_jobs")

# 1-hour retention — long enough that a user who started a scan, went
# to lunch, and came back can still see results. Old entries are
# evicted lazily during create_job() to avoid runaway memory.
_TTL_SEC = 3600

# job_id (str) → job dict (see _new_job_record below for shape)
_JOBS: dict[str, dict] = {}
_LOCK = asyncio.Lock()


def _now() -> float:
    return time.time()


def _new_job_record(scanner_id: str, scanner_name: str, universe_size: int) -> dict:
    return {
        "jobId":        "",   # filled by create_job
        "scannerId":    scanner_id,
        "scannerName":  scanner_name,
        "status":       "queued",   # queued → running → completed | failed | cancelled
        "startedAt":    _now(),
        "completedAt":  None,
        "progress": {
            "total":     universe_size,  # how many symbols in the universe
            "scanned":   0,               # how many have finished evaluation
            "matched":   0,               # of those, how many passed the conditions
            "failed":    0,               # of those, how many didn't pass
            "errors":    0,               # count of evaluation errors
            "stage":     "queued",        # human-readable phase indicator
        },
        # Live match stream — appended as the scan loop finds matches.
        # Frontend renders these in the results panel while status is
        # "running"; replaced by the final sorted result.results once
        # status flips to "completed". Capped at 500 to bound memory for
        # pathological universes; if a real scanner matches more, the
        # final `result` still ships everything.
        "partialMatches": [],
        "result":       None,   # ScanResult dict when status == completed
        "error":        None,   # error string when status == failed
    }


_MAX_PARTIAL_MATCHES = 500


def push_match(job_id: str, row: dict) -> None:
    """Append a single match to the live stream. Called from the scan
    loop's progress callback immediately after a symbol passes all
    conditions. Order = arrival order (NOT sorted by score) — the
    frontend sees a live "matches as they come" feed; the final sorted
    list arrives separately via `result.results` once status flips
    to completed.

    Bounded at `_MAX_PARTIAL_MATCHES` to keep memory predictable; the
    `result.results` payload from the completed scan still ships ALL
    matches regardless of this cap."""
    job = _JOBS.get(job_id)
    if not job:
        return
    arr = job.get("partialMatches")
    if arr is None:
        arr = []
        job["partialMatches"] = arr
    if len(arr) < _MAX_PARTIAL_MATCHES:
        arr.append(row)


async def create_job(
    scanner_id: str,
    scanner_name: str,
    universe_size: int,
) -> str:
    """Allocate a fresh job and return its id. Caller is responsible
    for spawning the actual scan task; this function only sets up the
    tracking record."""
    job_id = uuid.uuid4().hex
    async with _LOCK:
        _evict_expired_unlocked()
        rec = _new_job_record(scanner_id, scanner_name, universe_size)
        rec["jobId"] = job_id
        _JOBS[job_id] = rec
    logger.info("scan_jobs: created job %s for scanner %s (universe=%d)",
                job_id[:8], scanner_id, universe_size)
    return job_id


def _evict_expired_unlocked() -> None:
    """Drop completed jobs older than TTL. Called inside create_job
    while the lock is held."""
    cutoff = _now() - _TTL_SEC
    expired = [
        jid for jid, j in _JOBS.items()
        if j.get("completedAt") is not None and j["completedAt"] < cutoff
    ]
    for jid in expired:
        del _JOBS[jid]
    if expired:
        logger.debug("scan_jobs: evicted %d expired jobs", len(expired))


def update_progress(job_id: str, **updates: Any) -> None:
    """Merge `updates` into the job's progress dict. Safe to call from
    a background task — no lock needed because we're single-threaded
    inside the event loop, and `dict.update` is atomic per-key.

    Caller passes ONLY the fields that changed (e.g. `scanned=42,
    matched=7`). `stage` accepts any short human-readable string —
    "prefetch_fundamentals" / "scanning" / "done" are conventional."""
    job = _JOBS.get(job_id)
    if not job:
        return
    job["progress"].update(updates)


def mark_running(job_id: str, stage: str = "scanning") -> None:
    job = _JOBS.get(job_id)
    if not job:
        return
    job["status"] = "running"
    job["progress"]["stage"] = stage


def mark_completed(job_id: str, result: dict) -> None:
    job = _JOBS.get(job_id)
    if not job:
        return
    job["status"] = "completed"
    job["completedAt"] = _now()
    job["result"] = result
    job["progress"]["stage"] = "done"


def mark_failed(job_id: str, error: str) -> None:
    job = _JOBS.get(job_id)
    if not job:
        return
    job["status"] = "failed"
    job["completedAt"] = _now()
    job["error"] = str(error)[:500]
    job["progress"]["stage"] = "failed"


def get(job_id: str) -> Optional[dict]:
    """Read-only fetch. Returns the live record — caller should treat
    it as immutable (don't mutate fields)."""
    return _JOBS.get(job_id)


def list_active() -> list[dict]:
    """Snapshot of all currently-running jobs. Useful for an admin
    debug endpoint; not used by the standard flow."""
    return [j for j in _JOBS.values() if j["status"] in ("queued", "running")]
