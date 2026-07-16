"""Guard test: no SQLite database may live under the market_cache/ SMB mount.

In production market_cache/ is an Azure Files (SMB) network share. SQLite (and
especially WAL mode) cannot run there — connections fail with
``sqlite3.OperationalError: database is locked``. SQLite DBs must live on local
disk via ``app.lib.db_paths.local_db_path`` (which roots them under
sqlite_cache/). This regression took the backend down once; this test makes it
fail the build instead of production.

Detection is a small AST taint scan, because the naive same-line literal check
missed two real regressions:

  * ipo_store.py built the path across two lines
    (``_DB_DIR = os.path.join(..., "market_cache")`` then
    ``os.path.join(_DB_DIR, "ipo_store.db")``) — invisible to a same-line scan.
  * sector_cache.py joined the literals on ONE line and nobody noticed the
    red test for several commits.

The scan marks a variable "tainted" when its assigned value references the
mount (a literal ``market_cache`` path segment, the exported
``MOUNTED_CACHE_DIR``, or another tainted variable — followed to a fixpoint),
then flags any join/call/f-string that combines a mount reference with a
``*.db`` / ``*.sqlite`` filename literal, plus any standalone path literal like
``"market_cache/foo.db"``. Prose in docstrings/comments does not match: only
whole-string paths (no whitespace) count for the standalone rule, and comments
never reach the AST.

Legitimate references (currently only ipo_store's READ-ONLY legacy-migration
source) opt out with an explicit end-of-line marker::

    _LEGACY_DB = os.path.join(_LEGACY_DIR, "ipo_store.db")  # sqlite-on-mount-ok: <reason>

Flat files (JSON/CSV) on the mount are fine and are not flagged.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from app.lib.db_paths import LOCAL_DB_DIR, MOUNTED_CACHE_DIR, local_db_path

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
_DB_SUFFIXES = (".db", ".sqlite", ".sqlite3")
_MOUNT_SEGMENT = "market_cache"
# Names that ARE the mount, wherever they're imported from.
_MOUNT_NAMES = frozenset({"MOUNTED_CACHE_DIR"})
_ALLOW_MARKER = "sqlite-on-mount-ok"


def test_local_db_helper_is_off_the_mount():
    """The sanctioned SQLite location must not be under the SMB mount."""
    p = local_db_path("probe.db").resolve()
    assert MOUNTED_CACHE_DIR.resolve() not in p.parents, (
        f"local_db_path() resolves under the market_cache/ mount: {p}"
    )
    assert LOCAL_DB_DIR.resolve() in p.parents


# ── the scanner ─────────────────────────────────────────────────────────────

def _is_mount_path_literal(s: str) -> bool:
    """True when 'market_cache' appears as a clean path segment. Prose such
    as 'the market_cache directory' does not split into an exact segment."""
    return _MOUNT_SEGMENT in re.split(r"[\\/]+", s.strip())


def _is_db_literal(s: str) -> bool:
    return s.strip().lower().endswith(_DB_SUFFIXES)


def _str_constants(node: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _attr_names(node: ast.AST) -> set[str]:
    """Attribute accessors within `node`, e.g. `db_paths.MOUNTED_CACHE_DIR`
    contributes 'MOUNTED_CACHE_DIR' — so a module-qualified reference to the
    mount is caught, not just a bare imported name."""
    return {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def _mount_import_aliases(tree: ast.AST) -> set[str]:
    """Local names bound to a mount symbol via `from … import MOUNTED_CACHE_DIR`
    — including `... as alias`, so the aliased name is tainted too."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name in _MOUNT_NAMES:
                    aliases.add(a.asname or a.name)
    return aliases


def find_mount_db_offences(source: str) -> list[int]:
    """Line numbers where a SQLite filename is combined with the mount.

    Rules:
      1. taint — a variable assigned from anything referencing the mount
         (literal segment / a mount name / a tainted var) is itself a mount
         reference; propagated to a fixpoint so chains resolve. Mount names
         include MOUNTED_CACHE_DIR, any `import … as alias` of it, and any
         module-qualified access (`db_paths.MOUNTED_CACHE_DIR`).
      2. combination — a Call / BinOp / f-string that references the mount
         AND contains a *.db/*.sqlite literal is an offence (os.path.join,
         Path joins with '/', string concat/format alike).
      3. standalone — a whole-string path literal under market_cache ending
         in a DB suffix (e.g. sqlite3.connect("market_cache/x.db")).
      4. a line carrying the `sqlite-on-mount-ok` marker is exempt.
    """
    tree = ast.parse(source)
    src_lines = source.splitlines()

    # ── rule 1: taint propagation over simple-name assignments ─────────────
    assigns: list[tuple[set[str], ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if targets:
                assigns.append((targets, node.value))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            if isinstance(node.target, ast.Name) and node.value is not None:
                assigns.append(({node.target.id}, node.value))

    # Seed taint with the base mount name, its import aliases, and treat any
    # `*.MOUNTED_CACHE_DIR` attribute access as a mount reference.
    tainted: set[str] = set(_MOUNT_NAMES) | _mount_import_aliases(tree)

    def refs_mount(node: ast.AST) -> bool:
        return (any(_is_mount_path_literal(s) for s in _str_constants(node))
                or bool(_names(node) & tainted)
                or bool(_attr_names(node) & _MOUNT_NAMES))

    changed = True
    while changed:
        changed = False
        for targets, value in assigns:
            if not targets <= tainted and refs_mount(value):
                tainted |= targets
                changed = True

    # ── rules 2 + 3: collect offences ───────────────────────────────────────
    offence_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Call, ast.BinOp, ast.JoinedStr)):
            if refs_mount(node) and any(_is_db_literal(s) for s in _str_constants(node)):
                offence_lines.add(node.lineno)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value.strip()
            # whole-string path only — prose containing whitespace is skipped
            if s and not re.search(r"\s", s) and _is_mount_path_literal(s) and _is_db_literal(s):
                offence_lines.add(node.lineno)

    # ── rule 4: explicit opt-out marker on the offending line ──────────────
    out = []
    for lineno in sorted(offence_lines):
        line = src_lines[lineno - 1] if 0 < lineno <= len(src_lines) else ""
        if _ALLOW_MARKER not in line:
            out.append(lineno)
    return out


def test_no_sqlite_db_constructed_under_market_cache():
    """No module builds a SQLite path under market_cache/ — even across
    multiple lines / variables (the evasion that let ipo_store.py regress)."""
    offenders: list[str] = []
    for py in _APP_DIR.rglob("*.py"):
        for lineno in find_mount_db_offences(py.read_text(encoding="utf-8")):
            offenders.append(f"{py.relative_to(_APP_DIR.parent)}:{lineno}")
    assert not offenders, (
        "SQLite DB path built under the market_cache/ SMB mount — use "
        "app.lib.db_paths.local_db_path() instead (or, for a read-only "
        f"legacy reference, add a '# {_ALLOW_MARKER}: <reason>' marker). "
        "Offending lines:\n  " + "\n  ".join(offenders)
    )


# ── scanner self-tests: pin the exact patterns that previously escaped ─────

class TestScannerCatchesEvasions:
    def test_same_line_join_is_caught(self):
        # The sector_cache.py regression (one-line Path join).
        src = 'from pathlib import Path\n_DB = Path(__file__).parent / "market_cache" / "sector_cache.db"\n'
        assert find_mount_db_offences(src) == [2]

    def test_two_line_variable_join_is_caught(self):
        # The ipo_store.py regression the old same-line scan missed.
        src = (
            "import os\n"
            '_DB_DIR  = os.path.join(os.path.dirname(__file__), "..", "..", "market_cache")\n'
            '_DB_PATH = os.path.join(_DB_DIR, "ipo_store.db")\n'
        )
        assert find_mount_db_offences(src) == [3]

    def test_taint_chain_through_intermediate_variable(self):
        src = (
            "import os\n"
            '_BASE = os.path.join("x", "market_cache")\n'
            "_DIR = _BASE\n"
            '_DB = os.path.join(_DIR, "cache.sqlite")\n'
        )
        assert find_mount_db_offences(src) == [4]

    def test_mounted_cache_dir_name_is_caught(self):
        src = 'from app.lib.db_paths import MOUNTED_CACHE_DIR\np = MOUNTED_CACHE_DIR / "foo.db"\n'
        assert find_mount_db_offences(src) == [2]

    def test_aliased_mount_import_is_caught(self):
        # `import … as alias` must taint the alias, not just the base name.
        src = (
            "from app.lib.db_paths import MOUNTED_CACHE_DIR as cache_dir\n"
            'p = cache_dir / "foo.db"\n'
        )
        assert find_mount_db_offences(src) == [2]

    def test_module_qualified_mount_ref_is_caught(self):
        # `db_paths.MOUNTED_CACHE_DIR` (attribute access) must be caught.
        src = (
            "from app.lib import db_paths\n"
            'p = db_paths.MOUNTED_CACHE_DIR / "foo.db"\n'
        )
        assert find_mount_db_offences(src) == [2]

    def test_single_combined_literal_is_caught(self):
        src = 'import sqlite3\nconn = sqlite3.connect("market_cache/foo.db")\n'
        assert find_mount_db_offences(src) == [2]

    def test_fstring_join_is_caught(self):
        src = '_dir = "market_cache"\npath = f"{_dir}/alerts.db"\n'
        assert find_mount_db_offences(src) == [2]

    def test_flat_files_on_mount_are_fine(self):
        # JSON/CSV on the SMB mount is the sanctioned use.
        src = (
            "from pathlib import Path\nimport os\n"
            '_CACHE_DIR = Path(os.environ.get("MARKET_CACHE_DIR", "market_cache"))\n'
            '_STORE = _CACHE_DIR / "bot_alerts.json"\n'
            '_CSV = _CACHE_DIR / "dhan_scrip_master.csv"\n'
        )
        assert find_mount_db_offences(src) == []

    def test_prose_in_docstrings_does_not_match(self):
        src = (
            '"""This used to live at market_cache/ai_analyst.db; now the\n'
            'store is in Postgres. Do not recreate market_cache DBs."""\n'
            'X = "unrelated.db"\n'
        )
        assert find_mount_db_offences(src) == []

    def test_local_db_path_usage_is_fine(self):
        src = (
            "from app.lib.db_paths import local_db_path\n"
            '_DB_PATH = str(local_db_path("ipo_store.db"))\n'
        )
        assert find_mount_db_offences(src) == []

    def test_allow_marker_suppresses_a_deliberate_reference(self):
        src = (
            "import os\n"
            '_LEGACY_DIR = os.path.join("x", "market_cache")\n'
            f'_LEGACY_DB = os.path.join(_LEGACY_DIR, "ipo_store.db")  # {_ALLOW_MARKER}: read-only migration\n'
        )
        assert find_mount_db_offences(src) == []
