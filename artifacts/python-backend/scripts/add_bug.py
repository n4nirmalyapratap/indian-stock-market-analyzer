#!/usr/bin/env python3.11
"""
add_bug.py — CLI helper to add a bug to the tracker.

Usage (from workspace root):
    PYTHONPATH=artifacts/python-backend python3.11 artifacts/python-backend/scripts/add_bug.py \
        --title "Short bug description" \
        --description "Steps to reproduce / root cause" \
        --severity medium \
        --component "Options Strategy Tester" \
        --reported_by "agent"

Severity choices: critical high medium low
Component choices: Options Strategy Tester | Stock Analysis | Charts | Chatbot |
                   Backtest | Admin Dashboard | API | Authentication | Other
"""

from __future__ import annotations

import argparse
import sqlite3
import time
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent.resolve()
DB_PATH     = BACKEND_DIR / "users.db"

COMPONENTS = [
    "Options Strategy Tester", "Stock Analysis", "Charts", "Chatbot",
    "Backtest", "Admin Dashboard", "API", "Authentication", "Other",
]
SEVERITIES = ["critical", "high", "medium", "low"]


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bug_reports (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            description TEXT DEFAULT '',
            severity    TEXT DEFAULT 'medium',
            status      TEXT DEFAULT 'open',
            component   TEXT DEFAULT '',
            reported_by TEXT DEFAULT '',
            created_at  INTEGER NOT NULL,
            updated_at  INTEGER NOT NULL
        )
    """)
    conn.commit()


def add_bug(
    title: str,
    description: str = "",
    severity: str = "medium",
    component: str = "Other",
    reported_by: str = "agent",
) -> str:
    """Insert a new bug and return its ID."""
    bug_id = str(uuid.uuid4())[:8]
    now    = int(time.time())
    conn   = sqlite3.connect(str(DB_PATH))
    _ensure_table(conn)
    conn.execute(
        """INSERT INTO bug_reports
           (id, title, description, severity, status, component, reported_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)""",
        (bug_id, title, description, severity, component, reported_by, now, now),
    )
    conn.commit()
    conn.close()
    return bug_id


def update_bug_status(bug_id: str, status: str, note: str = "") -> None:
    """Update a bug's status (open → in-progress → fixed / closed)."""
    now  = int(time.time())
    conn = sqlite3.connect(str(DB_PATH))
    if note:
        conn.execute(
            "UPDATE bug_reports SET status=?, updated_at=?, description=description||? WHERE id=?",
            (status, now, f"\n\n[{status}] {note}", bug_id),
        )
    else:
        conn.execute(
            "UPDATE bug_reports SET status=?, updated_at=? WHERE id=?",
            (status, now, bug_id),
        )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add a bug report to the tracker")
    parser.add_argument("--title",       required=True,       help="Short bug title")
    parser.add_argument("--description", default="",          help="Detailed description")
    parser.add_argument("--severity",    default="medium",    choices=SEVERITIES)
    parser.add_argument("--component",   default="Other",
                        help=f"One of: {', '.join(COMPONENTS)}")
    parser.add_argument("--reported_by", default="agent",     help="Who found this bug")
    args = parser.parse_args()

    bug_id = add_bug(
        title=args.title,
        description=args.description,
        severity=args.severity,
        component=args.component,
        reported_by=args.reported_by,
    )
    print(f"Bug added: #{bug_id}  [{args.severity}]  {args.title}")
    print(f"  → Status: open")
    print(f"  → Stored in: {DB_PATH}")
