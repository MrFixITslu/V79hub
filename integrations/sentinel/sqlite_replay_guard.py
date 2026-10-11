"""Isolated, single-host SQLite replay defense for the G2 read prototype.

Not mounted in a real NOC. A trusted operator must provision an already
existing private directory and an explicit, fixed database path. No network,
customer device access, credential data, or HTTP listener in this module.

This proves process/restart persistence on one host. It is NOT a multi-host
distributed replay solution; never claim otherwise.
"""
from __future__ import annotations

import os
import re
from contextlib import closing
import sqlite3
import stat
from pathlib import Path

_NONCE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_MAX_USED = 128
_WINDOW_MS = 90_000


class ReplayStoreUnavailable(RuntimeError):
    """No authorization may proceed without an available replay ledger."""


class SqliteNonceReplayGuard:
    """Crash-persistent, atomic one-use claim for a *single trusted host*.

    The caller must finish HMAC auth/tenant and request freshness checks
    BEFORE using this store. Never derive the database path from requests.
    """

    def __init__(self, database_path: str | Path):
        path = Path(database_path)
        if path.name in ("", ".", "..") or not path.is_absolute():
            raise ReplayStoreUnavailable("A fixed absolute replay path is required")
        self._path = path
        try:
            parent = path.parent
            parent_info = parent.stat()
            if not stat.S_ISDIR(parent_info.st_mode) or stat.S_IMODE(parent_info.st_mode) & 0o077:
                raise ReplayStoreUnavailable("Replay directory must be private")
            # Never follow a pre-existing malicious link. Explicitly creating
            # the file with 0600 also prevents accidental world-readable state.
            if path.is_symlink():
                raise ReplayStoreUnavailable("Replay database symlink forbidden")
            if not path.exists():
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
                flags |= getattr(os, "O_NOFOLLOW", 0)
                try:
                    fd = os.open(path, flags, 0o600)
                except FileExistsError:
                    pass  # another trusted worker won the creation race
                else:
                    os.close(fd)
            entry = path.stat()
            if not stat.S_ISREG(entry.st_mode) or stat.S_IMODE(entry.st_mode) & 0o077:
                raise ReplayStoreUnavailable("Replay database must be a private file")
            with closing(self._connect()) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS used_requests (
                        request_id TEXT PRIMARY KEY,
                        expires_at_ms INTEGER NOT NULL
                    )
                """)
        except (OSError, sqlite3.Error) as exc:
            raise ReplayStoreUnavailable("Replay store unavailable") from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._path), timeout=2.0, isolation_level=None)
        try:
            connection.execute("PRAGMA busy_timeout=2000")
            connection.execute("PRAGMA synchronous=FULL")
        except (sqlite3.Error, OSError):
            connection.close()
            raise
        return connection

    def claim(self, request_id: str, now_ms: int) -> bool:
        """Persist a fresh request exactly once, across processes and restarts.

        Returns False for duplicate or saturated stores. Unavailable stores
        raise ReplayStoreUnavailable so the caller can fail with generic 503.
        """
        if (not isinstance(request_id, str) or not _NONCE.fullmatch(request_id)
            or type(now_ms) is not int or not 0 <= now_ms <= 8_640_000_000_000_000):
            return False

        try:
            with closing(self._connect()) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM used_requests WHERE expires_at_ms <= ?", (now_ms,))
                existing = db.execute(
                    "SELECT 1 FROM used_requests WHERE request_id=?", (request_id,)
                ).fetchone()
                if existing:
                    db.execute("COMMIT")
                    return False
                size = db.execute("SELECT COUNT(*) FROM used_requests").fetchone()[0]
                if size >= _MAX_USED:
                    db.execute("COMMIT")
                    return False
                db.execute(
                    "INSERT INTO used_requests(request_id, expires_at_ms) VALUES (?, ?)",
                    (request_id, now_ms + _WINDOW_MS),
                )
                db.execute("COMMIT")
                return True
        except (OSError, sqlite3.Error) as exc:
            raise ReplayStoreUnavailable("Replay store unavailable") from exc
