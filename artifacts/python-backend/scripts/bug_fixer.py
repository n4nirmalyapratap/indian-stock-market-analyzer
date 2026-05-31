#!/usr/bin/env python3.11
"""
bug_analyser.py — AI-powered bug analysis job for the Indian Stock Market Analyzer.

What it does (analysis only — no code changes, no git push):
  1. Reads open bugs from the DB that don't already have an AI analysis
  2. Finds relevant source code based on the component tag + title keywords
  3. Asks AI to diagnose the root cause and suggest precise fix steps
  4. Stores the analysis in the bug's description field
  5. Logs everything to the admin log ring-buffer

What it does NOT do:
  - Apply any code changes
  - Run tests
  - Push to GitHub
  - Change bug status (that's the human's job)

Usage:
    PYTHONPATH=. python3.11 scripts/bug_fixer.py [--bug-id <id>]

    --bug-id   Analyse a specific bug only (by ID). Omit to analyse all open bugs.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent.resolve()
WORKSPACE   = BACKEND_DIR.parent.parent      # /home/runner/workspace

sys.path.insert(0, str(BACKEND_DIR))

log = logging.getLogger("bug_analyser")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

ANALYSIS_TAG = "[AI Analysis]"

# ── Component → likely source dirs ─────────────────────────────────────────────
COMPONENT_PATHS: dict[str, list[str]] = {
    "Options Strategy Tester": [
        "artifacts/python-backend/app/services/options_backtest_service.py",
        "artifacts/python-backend/app/services/options_service.py",
        "artifacts/python-backend/app/routes/options.py",
        "artifacts/stock-market-app/src/pages/OptionsStrategyTester.tsx",
        "artifacts/stock-market-app/src/lib/options-utils.ts",
    ],
    "Stock Analysis": [
        "artifacts/python-backend/app/routes/stocks.py",
        "artifacts/python-backend/app/routes/sectors.py",
    ],
    "Charts": [
        "artifacts/stock-market-app/src/pages",
    ],
    "Chatbot": [
        "artifacts/python-backend/app/services/options_chatbot.py",
        "artifacts/python-backend/app/routes/options.py",
        "artifacts/python-backend/app/services/ai_client.py",
    ],
    "Backtest": [
        "artifacts/python-backend/app/services/options_backtest_service.py",
        "artifacts/python-backend/app/routes/options.py",
    ],
    "Admin Dashboard": [
        "artifacts/admin-dashboard/src/pages",
        "artifacts/python-backend/app/routes/admin.py",
    ],
    "API": [
        "artifacts/python-backend/app/routes",
        "artifacts/python-backend/main.py",
    ],
    "Authentication": [
        "artifacts/python-backend/app/routes/auth.py",
        "artifacts/python-backend/app/middleware/clerk_auth.py",
    ],
}


# ── DB helpers ─────────────────────────────────────────────────────────────────
#
# bug_reports lives in PostgreSQL (managed by admin.py:_init_bugs_db /
# /admin/bugs CRUD). The pre-PG version of this script opened a SQLite
# `users.db` that no longer exists — every 10-min tick logged
# "no such table: bug_reports". We now use the same PG connection the
# rest of the app uses.
#
# `created_at` / `updated_at` are stored as BIGINT epoch-ms in the
# bug_reports schema (see admin.py), so the seconds-based 24h freshness
# check below converts on read.


def _ensure_bug_reports_table() -> None:
    """Create the bug_reports PG table if it doesn't exist.

    `admin.py:_init_bugs_db` creates the same table lazily when an admin
    opens /admin/bugs. The scheduler can run before any admin has, so we
    bootstrap here too to make the script self-sufficient. Identical
    schema — keep it in sync with admin.py manually if either changes.
    """
    from app.lib.auth_store import get_conn  # noqa: PLC0415
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bug_reports (
                    id          TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    severity    TEXT NOT NULL DEFAULT 'medium',
                    status      TEXT NOT NULL DEFAULT 'open',
                    component   TEXT NOT NULL DEFAULT '',
                    reported_by TEXT NOT NULL DEFAULT '',
                    created_at  BIGINT NOT NULL,
                    updated_at  BIGINT NOT NULL
                )
            """)


def _list_open_bugs(bug_id: str | None = None) -> list[dict]:
    from app.lib.auth_store import get_conn  # noqa: PLC0415
    _ensure_bug_reports_table()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if bug_id:
                cur.execute(
                    "SELECT * FROM bug_reports WHERE id = %s",
                    (bug_id,),
                )
            else:
                cur.execute(
                    "SELECT * FROM bug_reports "
                    " WHERE status IN ('open','in-progress') "
                    " ORDER BY created_at ASC"
                )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def _already_analysed(bug: dict) -> bool:
    """Return True if this bug already has a recent AI analysis (< 24h old).

    `updated_at` is epoch-MS in PG (BIGINT). Convert to seconds before
    comparing with `time.time()`.
    """
    desc = bug.get("description", "") or ""
    if ANALYSIS_TAG not in desc:
        return False
    updated_ms = int(bug.get("updated_at") or 0)
    if updated_ms == 0:
        return False
    age_sec = time.time() - (updated_ms / 1000.0)
    return age_sec < 86400


def _save_analysis(bug_id: str, analysis: str) -> None:
    from app.lib.auth_store import get_conn  # noqa: PLC0415
    now_ms = int(time.time() * 1000)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT description FROM bug_reports WHERE id = %s",
                (bug_id,),
            )
            row = cur.fetchone()
            if row:
                current = row["description"] or ""
                # Strip any prior analysis so we don't concatenate
                # successive AI passes into the description forever.
                if ANALYSIS_TAG in current:
                    current = current[:current.index(ANALYSIS_TAG)].rstrip()
                new_desc = f"{current}\n\n{ANALYSIS_TAG}\n{analysis}".strip()
            else:
                new_desc = f"{ANALYSIS_TAG}\n{analysis}"
            cur.execute(
                "UPDATE bug_reports SET description = %s, updated_at = %s "
                " WHERE id = %s",
                (new_desc, now_ms, bug_id),
            )


# ── Code context builder ───────────────────────────────────────────────────────

def _read_file_snippet(path: Path, max_lines: int = 150) -> str:
    try:
        text  = path.read_text(errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... [{len(lines)-max_lines} more lines, file truncated]"
        return text
    except Exception as exc:
        return f"[could not read: {exc}]"


def _build_code_context(bug: dict) -> str:
    component = bug.get("component", "")
    title     = bug.get("title", "")
    desc      = bug.get("description", "") or ""

    paths = list(COMPONENT_PATHS.get(component, []))

    # Keyword grep fallback if component not mapped
    if not paths:
        keywords = re.findall(r'\b[a-zA-Z_]\w{3,}\b', f"{title} {desc}")[:5]
        for kw in keywords:
            result = subprocess.run(
                ["grep", "-rl", "--include=*.py", "--include=*.ts", "--include=*.tsx",
                 kw,
                 str(WORKSPACE / "artifacts/python-backend/app"),
                 str(WORKSPACE / "artifacts/stock-market-app/src")],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().splitlines()[:3]:
                if line and line not in paths:
                    paths.append(line)

    context_parts: list[str] = []
    seen: set[str] = set()
    for p in paths[:5]:
        full = WORKSPACE / p if not os.path.isabs(p) else Path(p)
        if full.is_file() and str(full) not in seen:
            seen.add(str(full))
            rel = str(full.relative_to(WORKSPACE)) if full.is_relative_to(WORKSPACE) else p
            context_parts.append(f"\n### {rel}\n```\n{_read_file_snippet(full)}\n```")
        elif full.is_dir():
            for f in sorted(full.iterdir())[:3]:
                if f.suffix in (".py", ".ts", ".tsx") and str(f) not in seen:
                    seen.add(str(f))
                    rel = str(f.relative_to(WORKSPACE))
                    context_parts.append(f"\n### {rel}\n```\n{_read_file_snippet(f)}\n```")

    return "\n".join(context_parts) if context_parts else "[no relevant source files found]"


# ── AI analysis ────────────────────────────────────────────────────────────────

_ANALYSIS_PROMPT = """\
You are a senior engineer reviewing a bug in the Indian Stock Market Analyzer (Python/FastAPI backend + React/TypeScript frontend).

Bug Report:
- ID: {id}
- Title: {title}
- Description: {description}
- Component: {component}
- Severity: {severity}

Relevant source code:
{code_context}

Your task: Diagnose this bug and explain how to fix it. Write a clear, actionable analysis that another developer can follow to fix the bug. Do NOT write actual code patches — instead explain:
1. **Root Cause** — What is causing this bug (be specific: file name, function name, line behaviour)
2. **Impact** — What breaks / how users are affected
3. **Fix Steps** — Numbered list of exact steps to fix it (file to edit, what to change, why)
4. **Test** — How to verify the fix is working

Be concise but precise. Use markdown. If you cannot determine the root cause from the information given, say so clearly and list what additional information would help.
"""


async def _analyse_bug(bug: dict, code_context: str) -> str:
    from app.services.ai_client import ask  # noqa: PLC0415

    prompt = _ANALYSIS_PROMPT.format(
        id=bug["id"],
        title=bug["title"],
        description=bug.get("description", "(none)"),
        component=bug.get("component", "unknown"),
        severity=bug.get("severity", "medium"),
        code_context=code_context,
    )
    system = (
        "You are a senior engineer diagnosing bugs in a Python/TypeScript stock market analysis app. "
        "Your analysis will be read by a developer or AI agent who will implement the fix. "
        "Be specific, direct, and actionable."
    )

    try:
        analysis = await ask(prompt, system=system, max_tokens=1500, temperature=0.2)
        return analysis.strip()
    except Exception as exc:
        return f"AI analysis failed: {exc}"


# ── Main loop ──────────────────────────────────────────────────────────────────

async def analyse_one_bug(bug: dict) -> str:
    bug_id = bug["id"]
    title  = bug["title"]

    if _already_analysed(bug):
        log.info("  Skipping #%s — already analysed recently", bug_id)
        return f"SKIP #{bug_id}: already has a fresh analysis"

    log.info("→ Analysing bug #%s: %s", bug_id, title)
    code_context = _build_code_context(bug)
    analysis     = await _analyse_bug(bug, code_context)

    _save_analysis(bug_id, analysis)
    log.info("  ✓ Analysis saved for #%s", bug_id)
    return f"ANALYSED #{bug_id}: {title[:60]}"


async def run_all(bug_id: str | None = None) -> list[str]:
    bugs = _list_open_bugs(bug_id=bug_id)
    if not bugs:
        msg = f"Bug #{bug_id} not found" if bug_id else "No open bugs to analyse"
        log.info("Bug analyser: %s", msg)
        return [msg]

    log.info("Bug analyser: %d bug(s) to process", len(bugs))
    results: list[str] = []
    for bug in bugs:
        try:
            result = await analyse_one_bug(bug)
            results.append(result)
        except Exception as exc:
            log.error("Error analysing bug #%s: %s", bug["id"], exc)
            results.append(f"ERROR #{bug['id']}: {exc}")

    log.info("Bug analyser complete: %s", results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI bug analyser")
    parser.add_argument("--bug-id", help="Analyse a specific bug ID only")
    args = parser.parse_args()
    asyncio.run(run_all(bug_id=args.bug_id))
