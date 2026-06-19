"""Guard test: no SQLite database may live under the market_cache/ SMB mount.

In production market_cache/ is an Azure Files (SMB) network share. SQLite (and
especially WAL mode) cannot run there — connections fail with
``sqlite3.OperationalError: database is locked``. SQLite DBs must live on local
disk via ``app.lib.db_paths.local_db_path`` (which roots them under
sqlite_cache/). This regression took the backend down once; this test makes it
fail the build instead of production.

The static scan keys on the *code* signature of the mistake: a ``"market_cache"``
string literal joined to a ``"*.db"`` / ``"*.sqlite"`` string literal on the same
line, e.g. ``Path(...) / "market_cache" / "foo.db"``. Prose in docstrings/comments
that merely mentions an old path (a single string like ``"market_cache/foo.db"``)
does not match, so it won't false-positive.
"""
from __future__ import annotations

import ast
from pathlib import Path

from app.lib.db_paths import LOCAL_DB_DIR, MOUNTED_CACHE_DIR, local_db_path

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
_DB_SUFFIXES = (".db", ".sqlite")


def test_local_db_helper_is_off_the_mount():
    """The sanctioned SQLite location must not be under the SMB mount."""
    p = local_db_path("probe.db").resolve()
    assert MOUNTED_CACHE_DIR.resolve() not in p.parents, (
        f"local_db_path() resolves under the market_cache/ mount: {p}"
    )
    assert LOCAL_DB_DIR.resolve() in p.parents


def _string_literals_by_line(tree: ast.AST) -> dict[int, list[str]]:
    by_line: dict[int, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            by_line.setdefault(node.lineno, []).append(node.value)
    return by_line


def test_no_sqlite_db_constructed_under_market_cache():
    """No module joins a SQLite filename onto a literal 'market_cache' segment."""
    offenders: list[str] = []
    for py in _APP_DIR.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for lineno, literals in _string_literals_by_line(tree).items():
            has_mount = any(s == "market_cache" for s in literals)
            has_db = any(s.endswith(_DB_SUFFIXES) for s in literals)
            if has_mount and has_db:
                offenders.append(f"{py.relative_to(_APP_DIR.parent)}:{lineno}")
    assert not offenders, (
        "SQLite DB path built under the market_cache/ SMB mount — use "
        "app.lib.db_paths.local_db_path() instead. Offending lines:\n  "
        + "\n  ".join(offenders)
    )
