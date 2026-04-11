#!/usr/bin/env python3.11
"""
bug_fixer.py — Autonomous bug-fixing agent for the Indian Stock Market Analyzer.

Workflow for each open bug:
  1. Read bug details from DB
  2. Find relevant source files based on component + keywords
  3. Ask AI to analyse and generate a JSON fix plan
  4. Apply edits (old_code → new_code patches)
  5. Run the test suite
  6. If tests pass → push to GitHub, mark bug as "fixed"
  7. If tests fail or AI can't fix → mark note + leave as "open"
  8. Log everything to the structured log buffer

Usage:
    PYTHONPATH=. python3.11 scripts/bug_fixer.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
BACKEND_DIR  = Path(__file__).parent.parent.resolve()
WORKSPACE    = BACKEND_DIR.parent.parent      # /home/runner/workspace
SCRIPTS_DIR  = WORKSPACE / "scripts"

sys.path.insert(0, str(BACKEND_DIR))

from app.lib.secrets_store import get_secret

log = logging.getLogger("bug_fixer")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

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
        "artifacts/python-backend/app/services",
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

def _get_db() -> sqlite3.Connection:
    db_path = BACKEND_DIR / "users.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _list_open_bugs() -> list[dict]:
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM bug_reports WHERE status = 'open' ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _update_bug(bug_id: str, **fields: str | int) -> None:
    fields["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [bug_id]
    conn = _get_db()
    conn.execute(f"UPDATE bug_reports SET {set_clause} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def _create_fix_log_bug(summary: str) -> None:
    """Create a bug entry that records the fixer's activity."""
    conn = _get_db()
    conn.execute("""
        INSERT OR IGNORE INTO bug_reports
            (id, title, description, severity, status, component, reported_by, created_at, updated_at)
        VALUES ('fixer-log','Bug Fixer Run Log','','low','closed','API','bug_fixer',?,?)
    """, (int(time.time()), int(time.time())))
    conn.execute(
        "UPDATE bug_reports SET description = ?, updated_at = ? WHERE id = 'fixer-log'",
        (summary, int(time.time()))
    )
    conn.commit()
    conn.close()


# ── Code context builder ───────────────────────────────────────────────────────

def _read_file_snippet(path: Path, max_lines: int = 200) -> str:
    try:
        text = path.read_text(errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... [{len(lines)-max_lines} more lines]"
        return text
    except Exception as exc:
        return f"[could not read: {exc}]"


def _build_code_context(bug: dict) -> str:
    component = bug.get("component", "")
    title     = bug.get("title", "")
    desc      = bug.get("description", "")

    paths = COMPONENT_PATHS.get(component, [])
    if not paths:
        # Keyword-based fallback
        keywords = re.findall(r'\b\w{4,}\b', f"{title} {desc}")[:6]
        for kw in keywords:
            result = subprocess.run(
                ["grep", "-rl", kw, str(WORKSPACE / "artifacts/python-backend/app"),
                 str(WORKSPACE / "artifacts/stock-market-app/src")],
                capture_output=True, text=True
            )
            for line in result.stdout.strip().splitlines()[:3]:
                if line not in paths:
                    paths.append(line)

    context_parts = []
    for p in paths[:5]:
        full = WORKSPACE / p if not os.path.isabs(p) else Path(p)
        if full.is_file():
            context_parts.append(f"\n### {p}\n```\n{_read_file_snippet(full)}\n```")
        elif full.is_dir():
            for f in sorted(full.iterdir())[:3]:
                if f.suffix in (".py", ".ts", ".tsx"):
                    rel = str(f.relative_to(WORKSPACE))
                    context_parts.append(f"\n### {rel}\n```\n{_read_file_snippet(f)}\n```")

    return "\n".join(context_parts) if context_parts else "[no code context found]"


# ── AI fix generation ──────────────────────────────────────────────────────────

_FIX_SCHEMA = """\
Return ONLY valid JSON with this exact schema (no markdown, no explanation):
{
  "can_fix": true,
  "analysis": "root cause explanation",
  "confidence": "high|medium|low",
  "fixes": [
    {
      "file": "relative/path/from/workspace/root",
      "description": "what this change does",
      "old_code": "exact string to find and replace (must exist verbatim in the file)",
      "new_code": "replacement string"
    }
  ],
  "test_command": "command to validate the fix, e.g. python3.11 -m pytest tests/ -q"
}

If you cannot determine a safe fix, return:
{"can_fix": false, "analysis": "reason", "confidence": "low", "fixes": [], "test_command": ""}
"""


async def _ask_for_fix(bug: dict, code_context: str) -> dict:
    from app.services.ai_client import ask  # noqa: PLC0415

    prompt = f"""\
Bug Report:
- ID: {bug['id']}
- Title: {bug['title']}
- Description: {bug.get('description', '(none)')}
- Component: {bug.get('component', 'unknown')}
- Severity: {bug.get('severity', 'medium')}

Relevant source code:
{code_context}

{_FIX_SCHEMA}"""

    system = (
        "You are a senior engineer fixing bugs in an Indian stock market analysis app "
        "(Python/FastAPI backend + React/TypeScript frontend). "
        "Analyse the bug carefully and produce a precise, minimal code patch. "
        "Only suggest changes you are confident about. "
        "The 'old_code' field MUST be an exact verbatim substring of the file."
    )

    raw = await ask(prompt, system=system, max_tokens=2048, temperature=0.1)

    # Strip markdown fences if AI wrapped the JSON
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("AI returned non-JSON: %s", raw[:200])
        return {"can_fix": False, "analysis": f"AI returned unparseable response: {raw[:200]}", "fixes": []}


# ── Patch application ──────────────────────────────────────────────────────────

def _apply_fix(fix: dict) -> tuple[bool, str]:
    rel_path = fix.get("file", "")
    old_code = fix.get("old_code", "")
    new_code = fix.get("new_code", "")

    if not rel_path or not old_code:
        return False, "Missing file or old_code in fix spec"

    full = WORKSPACE / rel_path
    if not full.exists():
        return False, f"File not found: {rel_path}"

    text = full.read_text(errors="replace")
    if old_code not in text:
        return False, f"old_code not found verbatim in {rel_path}"

    new_text = text.replace(old_code, new_code, 1)
    full.write_text(new_text)
    return True, f"Patched {rel_path}"


# ── Test runner ────────────────────────────────────────────────────────────────

def _run_tests(test_cmd: str) -> tuple[bool, str]:
    if not test_cmd:
        test_cmd = "python3.11 -m pytest artifacts/python-backend/tests/ -q --tb=short"

    result = subprocess.run(
        test_cmd,
        shell=True,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = (result.stdout + result.stderr)[-3000:]
    passed = result.returncode == 0
    return passed, output


# ── GitHub push ────────────────────────────────────────────────────────────────

def _git_push() -> tuple[bool, str]:
    result = subprocess.run(
        "pnpm --filter @workspace/scripts run push-github",
        shell=True,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = (result.stdout + result.stderr)[-1000:]
    return result.returncode == 0, output


# ── Main loop ──────────────────────────────────────────────────────────────────

async def fix_one_bug(bug: dict, dry_run: bool = False) -> str:
    bug_id = bug["id"]
    title  = bug["title"]
    log.info("→ Analysing bug #%s: %s", bug_id, title)

    # Mark in-progress
    if not dry_run:
        _update_bug(bug_id, status="in-progress")

    code_context = _build_code_context(bug)
    plan = await _ask_for_fix(bug, code_context)

    if not plan.get("can_fix"):
        reason = plan.get("analysis", "AI could not determine a fix")
        log.warning("  ✗ Cannot auto-fix #%s: %s", bug_id, reason[:120])
        if not dry_run:
            _update_bug(bug_id, status="open",
                        description=f"{bug.get('description','')}\n\n[Fixer note] AI analysis: {reason}")
        return f"SKIP #{bug_id}: {reason[:80]}"

    confidence = plan.get("confidence", "low")
    analysis   = plan.get("analysis", "")
    fixes      = plan.get("fixes", [])
    test_cmd   = plan.get("test_command", "")

    log.info("  AI plan: confidence=%s, %d fix(es)", confidence, len(fixes))
    log.info("  Analysis: %s", analysis[:120])

    if dry_run:
        return f"DRY-RUN #{bug_id}: would apply {len(fixes)} fix(es) ({confidence} confidence)"

    # Apply patches
    applied = []
    failed  = []
    for fix in fixes:
        ok, msg = _apply_fix(fix)
        if ok:
            applied.append(msg)
            log.info("  ✓ %s", msg)
        else:
            failed.append(msg)
            log.warning("  ✗ Patch failed: %s", msg)

    if failed and not applied:
        reason = "; ".join(failed)
        _update_bug(bug_id, status="open",
                    description=f"{bug.get('description','')}\n\n[Fixer note] Patch failed: {reason}")
        return f"PATCH_FAIL #{bug_id}: {reason[:80]}"

    # Run tests
    log.info("  Running tests…")
    tests_passed, test_output = _run_tests(test_cmd)

    if not tests_passed:
        log.warning("  ✗ Tests failed after patch — reverting would need manual work")
        _update_bug(bug_id, status="open",
                    description=(
                        f"{bug.get('description','')}\n\n"
                        f"[Fixer note] Patch applied but tests failed:\n{test_output[-500:]}"
                    ))
        return f"TEST_FAIL #{bug_id}: tests did not pass after fix"

    log.info("  ✓ Tests passed")

    # Push to GitHub
    log.info("  Pushing to GitHub…")
    pushed, push_out = _git_push()
    if pushed:
        log.info("  ✓ Pushed to GitHub")
    else:
        log.warning("  ✗ GitHub push failed: %s", push_out[:200])

    # Mark fixed
    fix_note = f"Auto-fixed by bug_fixer.py. {analysis[:200]}"
    _update_bug(bug_id, status="fixed", description=f"{bug.get('description','')}\n\n[Fixer] {fix_note}")

    return f"FIXED #{bug_id}: {title[:60]}"


async def run_all(dry_run: bool = False) -> list[str]:
    bugs = _list_open_bugs()
    log.info("Bug fixer: %d open bug(s) to process", len(bugs))
    if not bugs:
        return ["No open bugs found."]

    results = []
    for bug in bugs:
        try:
            result = await fix_one_bug(bug, dry_run=dry_run)
            results.append(result)
        except Exception as exc:
            log.error("Error processing bug #%s: %s", bug["id"], exc)
            results.append(f"ERROR #{bug['id']}: {exc}")

    summary = "\n".join(results)
    log.info("Bug fixer complete:\n%s", summary)
    _create_fix_log_bug(summary)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous bug fixer")
    parser.add_argument("--dry-run", action="store_true", help="Analyse only, don't apply fixes")
    args = parser.parse_args()
    asyncio.run(run_all(dry_run=args.dry_run))
