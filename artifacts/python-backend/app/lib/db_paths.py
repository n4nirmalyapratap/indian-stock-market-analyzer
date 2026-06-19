"""Canonical filesystem locations for the backend's SQLite databases.

Why this module exists
----------------------
In production (Azure Container Apps) the directory ``market_cache/`` is an
Azure Files (SMB) **network mount**. SQLite — especially in WAL mode, which
every cache DB here uses — cannot run on a network share: WAL needs a
shared-memory mmap segment that SMB does not provide, so connections fail at
runtime with ``sqlite3.OperationalError: database is locked``. This took down
the backend once already (a WAL cache DB was created under ``market_cache/``).

Flat-file caches (EOD JSON snapshots, logos) are fine on the SMB mount, but
SQLite databases must live on the container's **local disk**. To make that
impossible to get wrong, every SQLite path in the app is built through
:func:`local_db_path`, which always roots under a local-only directory
(``sqlite_cache/``) — never the mounted ``market_cache/``.

These DBs are per-replica, rebuildable caches, so local-disk storage (ephemeral
and not shared across replicas) is the correct design — not a limitation.

A guard test (``tests/test_sqlite_not_on_mount.py``) fails the build if any
SQLite path is ever constructed under ``market_cache/`` again.
"""
from __future__ import annotations

from pathlib import Path

# Backend root = artifacts/python-backend (this file is app/lib/db_paths.py, so
# three parents up).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

# The SMB-mounted cache dir in prod. Flat files ONLY — never SQLite. Exposed so
# the guard test can reference the canonical name instead of hard-coding it.
MOUNTED_CACHE_DIR = _BACKEND_ROOT / "market_cache"

# Local-disk home for every SQLite database. Deliberately a sibling of
# market_cache that is NOT mounted to network storage.
LOCAL_DB_DIR = _BACKEND_ROOT / "sqlite_cache"


def local_db_path(filename: str) -> Path:
    """Return the on-local-disk path for a SQLite database file.

    Use this for EVERY SQLite DB. Never join a ``.db``/``.sqlite`` path onto
    ``market_cache/`` (see module docstring for why). The parent directory is
    created on first use.
    """
    LOCAL_DB_DIR.mkdir(parents=True, exist_ok=True)
    return LOCAL_DB_DIR / filename
