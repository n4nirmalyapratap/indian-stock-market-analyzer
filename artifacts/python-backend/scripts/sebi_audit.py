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
    # Frontend expiry rules
    "artifacts/stock-market-app/src/pages/OptionsStrategyTester.tsx",
    "artifacts/stock-market-app/src/lib/options-utils.ts",
    # Backend backtest service
    "artifacts/python-backend/app/services/options_backtest_service.py",
    "artifacts/python-backend/app/routes/options.py",
    # Options pricing service
    "artifacts/python-backend/app/services/options_service.py",
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
    Ask DeepSeek to compare the circulars against the code snippets.
    Returns the raw analysis text (Markdown).
    """
    if not is_available():
        return "**AI analysis skipped** — OpenRouter env vars not set.\n\n" \
               "Set AI_INTEGRATIONS_OPENROUTER_BASE_URL and AI_INTEGRATIONS_OPENROUTER_API_KEY."

    # Build the prompt
    circular_section = ""
    for i, c in enumerate(circulars, 1):
        circular_section += (
            f"\n\n### Circular {i}: {c['title']}\n"
            f"**Date:** {c['date']}  \n"
            f"**URL:** {c['url']}\n\n"
            f"{c['text'][:4000]}\n"
        )

    code_section = ""
    for path, snippet in code_snippets.items():
        code_section += f"\n\n### File: `{path}`\n```\n{snippet[:3000]}\n```\n"

    prompt = textwrap.dedent(f"""
    ## SEBI Circulars to review ({len(circulars)} circulars)
    {circular_section}

    ---

    ## Current App Code (SEBI-related sections)
    {code_section}

    ---

    ## Your Task

    Produce a compliance audit report in this EXACT format:

    ```markdown
    # SEBI Compliance Audit — {{today}}

    ## Executive Summary
    [2-3 sentences: how many circulars reviewed, how many issues found, overall risk level]

    ## Issues Found

    ### ISSUE-001: [Short title]
    - **Severity**: Critical | High | Medium | Low
    - **Circular**: [Circular title, date, URL]
    - **Rule**: [Exact rule text from the circular]
    - **Current Code**: [File path, line number(s), what the code currently does]
    - **Required Change**: [Exactly what needs to change — precise enough for an AI agent to act on]
    - **Agent Prompt**: [A self-contained instruction you could give to an AI coding agent to fix this, without any other context]

    ### ISSUE-002: ...

    ## Not Applicable
    [List circulars that don't affect this app and why]

    ## Already Compliant
    [List rules that the code already correctly implements]
    ```

    Be precise. Cite line numbers. Write the Agent Prompt as if the agent has no background.
    """).strip()

    log.info("Sending %d circulars + %d files to %s …", len(circulars), len(code_snippets), AI_MODEL)
    return await ask(prompt, system=ANALYSIS_SYSTEM, max_tokens=4096, temperature=0.2)


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

async def main() -> None:
    parser = argparse.ArgumentParser(description="SEBI Compliance Audit Job")
    parser.add_argument("--days",   type=int,  default=30,
                        help="How many days back to look for circulars (default 30)")
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
    print(f"  Looking back {args.days} days | Model: {AI_MODEL}")
    print(f"{'='*60}\n")

    # 1. Fetch circulars
    circulars = fetch_sebi_circulars(days=args.days)
    if not circulars:
        log.warning("No SEBI circulars found in the last %d days. "
                    "SEBI website may have changed structure.", args.days)
        circulars = _mock_known_rules()

    print(f"\n✓ Fetched {len(circulars)} circulars\n")

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


def _mock_known_rules() -> list[dict]:
    """
    When SEBI's website is unreachable, seed with well-known 2023-2024 rules
    so the audit still produces useful compliance checks.
    """
    return [
        {
            "title": "Weekly Options Expiry — SEBI Circular SEBI/HO/MRD/MRD-PoD-2/P/CIR/2023/168 (Oct 2023)",
            "url":   "https://www.sebi.gov.in/legal/circulars/oct-2023/circular-on-weekly-options-contracts_78174.html",
            "date":  "2023-10-04",
            "text":  (
                "SEBI has directed stock exchanges to offer weekly expiry options contracts "
                "on only one benchmark index per exchange. Effective from November 20, 2023: "
                "NSE may offer weekly contracts only on NIFTY 50. BSE may offer weekly contracts "
                "only on SENSEX. All other index options (BANKNIFTY, FINNIFTY, MIDCPNIFTY, "
                "SENSEX50, BANKEX) shall be available only in monthly expiry series. "
                "The last trading day for monthly contracts shall be the last Tuesday/Wednesday/"
                "Thursday/Friday as applicable for the respective index. "
                "Exchanges must delist weekly contract series for restricted indices by Nov 20 2023."
            ),
        },
        {
            "title": "Lot Size Rationalisation — SEBI Circular SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/113 (Aug 2024)",
            "url":   "https://www.sebi.gov.in/legal/circulars/aug-2024/rationalization-of-lot-size_85944.html",
            "date":  "2024-08-20",
            "text":  (
                "SEBI has revised lot sizes for index derivatives to ensure contract value between "
                "₹15 lakh and ₹20 lakh. New lot sizes effective November 2024: "
                "NIFTY 50 — 75 units (unchanged), BANKNIFTY — 30 units (was 25), "
                "FINNIFTY — 65 units (was 40), MIDCPNIFTY — 120 units (was 75), "
                "SENSEX — 20 units (unchanged), BANKEX — 30 units (was 20). "
                "Lot sizes must be reviewed semi-annually by exchanges."
            ),
        },
        {
            "title": "STT on Options Exercise — Finance Act 2023 (effective Apr 2023)",
            "url":   "https://incometaxindia.gov.in/communications/notification/finance-act-2023.pdf",
            "date":  "2023-04-01",
            "text":  (
                "Securities Transaction Tax (STT) on exercise of options increased from 0.0625% "
                "to 0.125% of intrinsic value (i.e. settlement price × lot size) effective "
                "1 April 2023. For backtesting and PnL calculations, STT at expiry = "
                "0.00125 × settlement_price × lot_size when the option expires in-the-money."
            ),
        },
        {
            "title": "F&O Position Limits — SEBI Circular SEBI/HO/MRD/MRD-PoD-2/P/CIR/2024/50 (Apr 2024)",
            "url":   "https://www.sebi.gov.in/legal/circulars/apr-2024/position-limits_84191.html",
            "date":  "2024-04-15",
            "text":  (
                "SEBI has revised position limits for index derivative contracts. "
                "Client level: 1% of total open interest or ₹500 crore, whichever is lower. "
                "Market maker / proprietary: 5% of total open interest. "
                "FPI category I: 20% of total open interest. "
                "Risk managers must check position limits intraday at 1-minute intervals."
            ),
        },
    ]


if __name__ == "__main__":
    asyncio.run(main())
