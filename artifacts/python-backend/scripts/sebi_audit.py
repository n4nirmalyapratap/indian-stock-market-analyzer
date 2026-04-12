#!/usr/bin/env python3.11
"""
SEBI Compliance Audit Job
=========================
Runs weekly (or on demand) to:
  1. Scrape SEBI.gov.in for the latest circulars (past 30 days by default)
  2. Download and extract the text of each circular
  3. Scan the app codebase for all SEBI-related logic
  4. Use DeepSeek (via OpenRouter) to compare circulars against code
  5. Write a structured audit report to reports/sebi_audit_YYYY-MM-DD.md

The output report is designed to be fed directly to an AI agent for fixing.

Usage:
    # Run from the python-backend directory
    python3.11 scripts/sebi_audit.py

    # Check only the last N days
    python3.11 scripts/sebi_audit.py --days 7

    # Save to a specific file
    python3.11 scripts/sebi_audit.py --output reports/audit.md
"""

import os
import sys
import re
import json
import asyncio
import argparse
import logging
import textwrap
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ── Path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent          # …/python-backend
APP_ROOT = ROOT.parent.parent                          # workspace root
sys.path.insert(0, str(ROOT))

from app.services.ai_client import ask, is_available, AI_MODEL  # noqa: E402
from scripts.sebi_circulars_db import get_all_circulars as _get_historical_circulars  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("sebi_audit")

# ── SEBI scraping ──────────────────────────────────────────────────────────────

SEBI_RSS_URL   = "https://www.sebi.gov.in/sebirss.xml"           # combined RSS feed
SEBI_BASE      = "https://www.sebi.gov.in"
SEBI_CIRC_PAGE = (                                               # HTML circular listing
    "https://www.sebi.gov.in/sebiweb/home/HomeAction.do"
    "?doListing=yes&sid=1&ssid=7&smid=0"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

def fetch_sebi_circulars(days: int = 30) -> list[dict]:
    """
    Fetch SEBI circulars from the RSS feed published in the last `days` days.
    Returns list of {title, url, date, text} dicts.
    """
    cutoff = date.today() - timedelta(days=days)
    circulars: list[dict] = []

    try:
        log.info("Fetching SEBI RSS feed …")
        resp = requests.get(SEBI_RSS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "xml")
        items = soup.find_all("item")
        log.info("Found %d items in RSS feed", len(items))
    except Exception as exc:
        log.error("RSS fetch failed: %s — using fallback scraper", exc)
        return _scrape_circulars_page(cutoff)

    for item in items:
        try:
            pub_str = (item.find("pubDate") or item.find("dc:date") or item.find("date") or
                       None)
            pub_date: Optional[date] = None
            if pub_str and pub_str.text.strip():
                for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%d %b %Y"):
                    try:
                        pub_date = datetime.strptime(pub_str.text.strip()[:30], fmt).date()
                        break
                    except ValueError:
                        pass

            if pub_date and pub_date < cutoff:
                continue   # too old

            title = item.find("title")
            link  = item.find("link") or item.find("guid")
            if not title or not link:
                continue

            title_text = title.text.strip()
            url = link.text.strip() if link.text else ""
            if not url.startswith("http"):
                url = SEBI_BASE + url

            text = _fetch_circular_text(url)
            circulars.append({
                "title": title_text,
                "url":   url,
                "date":  pub_date.isoformat() if pub_date else "unknown",
                "text":  text,
            })
            log.info("  ✓ %s (%s)", title_text[:80], pub_date or "date unknown")
        except Exception as exc:
            log.warning("  ✗ Could not process item: %s", exc)

    return circulars


def _scrape_circulars_page(cutoff: date) -> list[dict]:
    """
    Fallback: scrape the SEBI circulars listing page directly.
    """
    url = SEBI_CIRC_PAGE
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        log.error("Fallback scrape also failed: %s", exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    rows = soup.select("table.table tr")[1:]   # skip header
    circulars = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        date_text  = cells[0].get_text(strip=True)
        title_cell = cells[1]
        link_tag   = title_cell.find("a")
        if not link_tag:
            continue
        title = link_tag.get_text(strip=True)
        href  = link_tag.get("href", "")
        if not href.startswith("http"):
            href = SEBI_BASE + href
        try:
            pub_date = datetime.strptime(date_text, "%b %d, %Y").date()
        except ValueError:
            pub_date = None
        if pub_date and pub_date < cutoff:
            continue
        text = _fetch_circular_text(href)
        circulars.append({
            "title": title, "url": href,
            "date": pub_date.isoformat() if pub_date else "unknown",
            "text": text,
        })
    return circulars


def _fetch_circular_text(url: str) -> str:
    """
    Fetch the text content of a SEBI circular URL.
    Handles HTML pages; returns cleaned plain text (max 8000 chars).
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")
        # Remove nav/header/footer noise
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:8000]
    except Exception as exc:
        log.warning("    Could not fetch circular text from %s: %s", url, exc)
        return "(text unavailable)"


# ── Codebase scanner ───────────────────────────────────────────────────────────

# Files and directories in the app that contain regulatory / SEBI logic
AUDIT_FILES = [
    # ── Frontend ──────────────────────────────────────────────────────────────
    "artifacts/stock-market-app/src/pages/OptionsStrategyTester.tsx",
    "artifacts/stock-market-app/src/lib/options-utils.ts",
    # ── Backend options layer ──────────────────────────────────────────────────
    "artifacts/python-backend/app/services/options_service.py",
    "artifacts/python-backend/app/services/options_backtest_service.py",
    "artifacts/python-backend/app/services/options_chatbot.py",
    "artifacts/python-backend/app/services/strategy_builder_service.py",
    "artifacts/python-backend/app/routes/options.py",
    # ── Market data & sentiment ────────────────────────────────────────────────
    "artifacts/python-backend/app/services/market_sentiment_engine.py",
    "artifacts/python-backend/app/services/nse_service.py",
    "artifacts/python-backend/app/services/yahoo_service.py",
]

# Keywords that flag SEBI-related lines in the code
SEBI_KEYWORDS = [
    "expir", "weekly", "monthly", "SEBI", "sebi", "circular", "lot_size",
    "lot size", "circuit", "margin", "position limit", "pcr", "open interest",
    "STT", "transaction tax", "CTT", "stamp duty", "FINNIFTY", "BANKNIFTY",
    "MIDCPNIFTY", "SENSEX", "BANKEX", "NIFTY", "NSE", "BSE", "f&o",
    "futures", "options", "derivative", "settlement", "expiry_dow",
    "EXPIRY_DOW", "WEEKLY_SYMBOLS", "_last_weekday", "_expiry_dates",
]


def scan_codebase() -> dict[str, str]:
    """
    Return {filename: relevant_snippet} for each audit file.
    Extracts lines within ±15 lines of SEBI-related keywords to keep context tight.
    """
    snippets: dict[str, str] = {}
    for rel_path in AUDIT_FILES:
        abs_path = APP_ROOT / rel_path
        if not abs_path.exists():
            log.warning("Audit file not found: %s", rel_path)
            continue
        try:
            lines = abs_path.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            log.warning("Could not read %s: %s", rel_path, exc)
            continue

        # Find line indices that contain SEBI keywords
        flagged: set[int] = set()
        for i, line in enumerate(lines):
            for kw in SEBI_KEYWORDS:
                if kw in line:
                    # Include ±10 lines for context
                    flagged.update(range(max(0, i - 10), min(len(lines), i + 11)))
                    break

        if not flagged:
            continue

        extracted: list[str] = []
        prev = -2
        for i in sorted(flagged):
            if i > prev + 1:
                extracted.append(f"\n… (line {i+1}) …\n")
            extracted.append(f"{i+1:4d} | {lines[i]}")
            prev = i

        snippets[rel_path] = "\n".join(extracted)

    return snippets


# ── AI analysis ────────────────────────────────────────────────────────────────

ANALYSIS_SYSTEM = textwrap.dedent("""
You are a senior compliance engineer reviewing an Indian stock market application
for SEBI (Securities and Exchange Board of India) regulatory compliance.

Your job is to compare SEBI circulars with the application code and produce a
STRUCTURED AUDIT REPORT that a developer (or AI agent) can act on immediately.

Rules:
- Be specific: cite exact file paths, line numbers, and SEBI circular references
- Use the exact format specified — the output will be fed to an AI agent as a task list
- Only flag genuine discrepancies; do not invent issues
- If a circular is about something unrelated to this app (portfolio disclosures, broker registration, etc.), note it as "NOT APPLICABLE" and skip
- If the code already correctly implements the circular's requirement, note it as "ALREADY COMPLIANT"
""").strip()


async def analyse_with_ai(
    circulars: list[dict],
    code_snippets: dict[str, str],
) -> str:
    """
    Analyse SEBI circulars against the codebase using free AI models.

    Strategy (keeps well within free-model token limits):
    - Compress circulars to title + date + 250-char summary per circular
    - Compress code snippets to 500 chars each (key declarations only)
    - Split into batches of 10 circulars if needed, aggregate findings
    - Each call stays under ~4,000 tokens — safe for all free models

    Returns the full compliance audit as Markdown.
    """
    if not is_available():
        return (
            "**AI analysis skipped** — OpenRouter integration not connected.\n\n"
            "Go to Admin → Integrations → enable OpenRouter to use free Gemma 4 / Qwen / Llama models.\n\n"
            f"Circulars reviewed (no AI): {len(circulars)}"
        )

    today_str = date.today().isoformat()

    # ── Compress code snippets (500 chars each, first declarations only) ─────────
    compressed_code = ""
    for path, snippet in code_snippets.items():
        compressed_code += f"\n`{path}`:\n{snippet[:500]}\n"

    # ── Batch circulars into groups of 10 ────────────────────────────────────────
    # Each circular: title + date + 250-char summary → ~80 tokens each
    # 10 circulars × 80 = 800 tokens + 500 chars code × 10 files = ~2,500 tokens total
    BATCH_SIZE = 10
    batches = [circulars[i:i+BATCH_SIZE] for i in range(0, len(circulars), BATCH_SIZE)]
    all_issues: list[str] = []
    all_compliant: list[str] = []
    all_na: list[str] = []

    for batch_idx, batch in enumerate(batches, 1):
        circ_block = ""
        for c in batch:
            summary = (c.get("text") or "")[:250].replace("\n", " ").strip()
            circ_block += f"- [{c['date']}] **{c['title']}** — {summary}\n"

        prompt = textwrap.dedent(f"""
        You are auditing an Indian Stock Market web app (F&O options trading) for SEBI compliance.

        ## SEBI Circulars (batch {batch_idx}/{len(batches)})
        {circ_block}

        ## Key App Code (compressed)
        {compressed_code}

        ## Task
        List ONLY issues where the app code does NOT comply with a circular above.
        For each issue use this format:
        ### ISSUE: [short title]
        - Severity: Critical/High/Medium/Low
        - Circular: [title and date]
        - Rule: [exact rule]
        - File: [filename:line]
        - Fix: [precise code change needed]

        Then list already-compliant rules (one line each, prefix "COMPLIANT: ").
        Then list not-applicable circulars (one line each, prefix "NA: ").
        If nothing applies, write "COMPLIANT: All circulars in this batch are already implemented or not applicable."
        Be concise. Do not repeat the app description.
        """).strip()

        log.info("AI batch %d/%d — %d circulars …", batch_idx, len(batches), len(batch))
        try:
            result = await ask(prompt, system=ANALYSIS_SYSTEM, max_tokens=1500, temperature=0.1)
        except Exception as exc:
            log.warning("AI batch %d failed: %s — skipping", batch_idx, str(exc)[:100])
            result = f"(batch {batch_idx} skipped due to rate limit)"

        # Parse sections from result
        for line in result.split("\n"):
            stripped = line.strip()
            if stripped.startswith("### ISSUE"):
                all_issues.append(stripped[4:])  # remove "### "
            elif stripped.startswith("COMPLIANT:"):
                all_compliant.append(stripped)
            elif stripped.startswith("NA:"):
                all_na.append(stripped)
            else:
                # Keep full ISSUE blocks (multi-line)
                if all_issues and not stripped.startswith("COMPLIANT") and not stripped.startswith("NA:"):
                    all_issues[-1] = all_issues[-1] + "\n" + line

        # Brief pause between batches to avoid rate limits (1.5 s)
        if batch_idx < len(batches):
            await asyncio.sleep(1.5)

    # ── Build final report ────────────────────────────────────────────────────────
    n_issues = len([x for x in all_issues if x.strip()])
    issue_section = ""
    for idx, issue in enumerate(all_issues, 1):
        # Re-number issues sequentially
        first_line = issue.split("\n")[0]
        rest = "\n".join(issue.split("\n")[1:])
        issue_section += f"\n### ISSUE-{idx:03d}: {first_line.lstrip('ISSUE:').strip()}\n{rest}\n"

    compliant_section = "\n".join(all_compliant) or "None detected."
    na_section        = "\n".join(all_na)         or "None detected."

    risk = "Low" if n_issues == 0 else ("Medium" if n_issues <= 2 else "High")

    report = textwrap.dedent(f"""
    # SEBI Compliance Audit — {today_str}

    ## Executive Summary
    Reviewed **{len(circulars)} SEBI circulars** (20 from 5-year historical database + live RSS).
    Found **{n_issues} compliance issue(s)**. Overall risk level: **{risk}**.
    Analysis powered by {AI_MODEL} (free, open-source via OpenRouter).

    ## Issues Found
    {issue_section if issue_section.strip() else "_No issues found — codebase appears compliant._"}

    ## Already Compliant
    {compliant_section}

    ## Not Applicable
    {na_section}
    """).strip()

    log.info("AI analysis complete — %d issues across %d batches", n_issues, len(batches))
    return report


# ── Report writer ──────────────────────────────────────────────────────────────

def write_report(analysis: str, circulars: list[dict], output_path: Path) -> None:
    today = date.today().isoformat()
    header = textwrap.dedent(f"""
    ---
    generated: {today}
    model: {AI_MODEL}
    circulars_reviewed: {len(circulars)}
    tool: sebi_audit.py
    ---

    > **How to use this report:**
    > 1. Read the Issues Found section.
    > 2. Copy each "Agent Prompt" directly into your AI coding agent.
    > 3. The agent will make the code changes and run tests.
    > 4. Re-run this script after fixes to confirm compliance.

    ---

    """).lstrip()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(header + analysis, encoding="utf-8")
    log.info("Report written to %s", output_path)


# ── CLI entry point ────────────────────────────────────────────────────────────

def _merge_circulars(historical: list[dict], live: list[dict]) -> list[dict]:
    """
    Merge historical database with live-scraped circulars.
    Deduplicates by URL; live data takes precedence (may have fuller text).
    Returns sorted by date descending.
    """
    seen_urls: set[str] = set()
    merged: list[dict] = []
    # Live first (newer, more complete text)
    for c in live:
        url = c.get("url", "")
        if url not in seen_urls:
            seen_urls.add(url)
            merged.append(c)
    # Historical baseline
    for c in historical:
        url = c.get("url", "")
        if url not in seen_urls:
            seen_urls.add(url)
            merged.append(c)
    # Sort by date descending
    merged.sort(key=lambda c: c.get("date", ""), reverse=True)
    return merged


async def main() -> None:
    parser = argparse.ArgumentParser(description="SEBI Compliance Audit Job")
    parser.add_argument("--days",   type=int,  default=90,
                        help="How many days back to scrape live SEBI RSS (default 90). "
                             "Historical 5-year database is ALWAYS included regardless.")
    parser.add_argument("--output", type=str,  default="",
                        help="Output file path (default: reports/sebi_audit_YYYY-MM-DD.md)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch circulars and scan code but skip AI call; print raw data")
    args = parser.parse_args()

    today_str   = date.today().isoformat()
    output_path = Path(args.output) if args.output else (
        ROOT / "reports" / f"sebi_audit_{today_str}.md"
    )

    print(f"\n{'='*60}")
    print(f"  SEBI Compliance Audit — {today_str}")
    print(f"  Historical DB (2019–present) + live RSS ({args.days} days) | Model: {AI_MODEL}")
    print(f"{'='*60}\n")

    # 1a. Load 5-year historical database (always)
    historical = _get_historical_circulars()
    print(f"✓ Loaded {len(historical)} circulars from 5-year historical database\n")

    # 1b. Try live RSS for recent additions
    live = fetch_sebi_circulars(days=args.days)
    if not live:
        log.warning("Live RSS fetch returned nothing — using historical database only")
        live = []

    # 1c. Merge and deduplicate
    circulars = _merge_circulars(historical, live)
    print(f"✓ Total circulars for audit: {len(circulars)} "
          f"({len(historical)} historical + {len(live)} live, deduplicated)\n")

    # 2. Scan codebase
    code_snippets = scan_codebase()
    print(f"✓ Scanned {len(code_snippets)} files with SEBI-related logic\n")

    if args.dry_run:
        print("=== DRY RUN — Circular titles ===")
        for c in circulars:
            print(f"  [{c['date']}] {c['title']}")
        print("\n=== Files scanned ===")
        for f in code_snippets:
            print(f"  {f}")
        return

    # 3. AI analysis
    analysis = await analyse_with_ai(circulars, code_snippets)
    print("✓ AI analysis complete\n")

    # 4. Write report
    write_report(analysis, circulars, output_path)
    print(f"\n✓ Report saved to: {output_path}")
    print(f"\nFeed this file to your AI coding agent to fix all issues at once.\n")


async def run_audit_async(days: int = 90) -> dict:
    """
    Run the full SEBI compliance audit in-process (no subprocess).
    Returns {status, report_path, n_issues, log}.

    Call this from FastAPI routes and background jobs instead of
    launching this file as a subprocess.
    """
    today_str   = date.today().isoformat()
    output_path = ROOT / "reports" / f"sebi_audit_{today_str}.md"

    buf: list[str] = []
    def _log(msg: str) -> None:
        log.info(msg)
        buf.append(msg)

    _log(f"SEBI Compliance Audit — {today_str}")
    _log(f"Historical DB (2019–present) + live RSS ({days} days) | Model: {AI_MODEL}")

    # 1. Load & merge circulars
    historical = _get_historical_circulars()
    _log(f"Loaded {len(historical)} circulars from 5-year historical database")

    try:
        live = fetch_sebi_circulars(days=days)
    except Exception as exc:
        _log(f"Live RSS fetch error ({str(exc)[:120]}) — using historical database only")
        live = []
    if not live:
        _log("Live RSS returned nothing — using historical database only")
        live = []

    circulars = _merge_circulars(historical, live)
    _log(f"Total circulars: {len(circulars)} ({len(historical)} historical + {len(live)} live)")

    # 2. Scan codebase
    code_snippets = scan_codebase()
    _log(f"Scanned {len(code_snippets)} files with SEBI-related logic")

    # 3. AI analysis
    analysis = await analyse_with_ai(circulars, code_snippets)
    _log("AI analysis complete")

    # 4. Write report
    write_report(analysis, circulars, output_path)
    n_issues = analysis.count("### ISSUE-")
    _log(f"Report saved: {output_path.name} | {n_issues} issue(s) found")

    return {
        "status":      "ok",
        "report_path": str(output_path),
        "n_issues":    n_issues,
        "log":         "\n".join(buf),
    }


def _mock_known_rules() -> list[dict]:
    """Deprecated — use _get_historical_circulars() from sebi_circulars_db instead."""
    return _get_historical_circulars()


if __name__ == "__main__":
    asyncio.run(main())
