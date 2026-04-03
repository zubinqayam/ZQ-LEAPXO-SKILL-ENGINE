"""
backend/db.py — LeapXO v9 SQLCipher+WAL database layer.

Features:
- SQLCipher encryption (falls back to plain sqlite3 when pysqlcipher3 is unavailable)
- WAL journal mode for improved read/write concurrency
- Asyncio-safe mutex locking around all write operations
- Optimistic locking via per-row `version` column
- Connection kept open with a single-writer / multi-reader pattern
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQLCipher import — use encrypted driver when available, otherwise plain SQLite
# ---------------------------------------------------------------------------
try:
    from pysqlcipher3 import dbapi2 as _sqlite  # type: ignore[import]

    _SQLCIPHER_AVAILABLE = True
    logger.info("SQLCipher driver loaded — database will be encrypted at rest")
except ImportError:
    import sqlite3 as _sqlite  # type: ignore[assignment]

    _SQLCIPHER_AVAILABLE = False
    logger.warning(
        "pysqlcipher3 not installed — falling back to plain SQLite. "
        "Install pysqlcipher3 for encrypted-at-rest storage."
    )

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_DEFAULT_DB_PATH = os.environ.get("LEAPXO_DB_PATH", "leapxo_v9.db")
_DB_KEY = os.environ.get("LEAPXO_DB_KEY", "")  # injected by Tauri Stronghold / K8s secret


# ---------------------------------------------------------------------------
# Database manager
# ---------------------------------------------------------------------------
class Database:
    """Single-connection SQLite/SQLCipher database with WAL mode and async mutex."""

    def __init__(self, path: str = _DEFAULT_DB_PATH) -> None:
        self._path = path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Open (or create) the database and configure WAL + encryption."""
        conn = _sqlite.connect(self._path, check_same_thread=False)

        if _SQLCIPHER_AVAILABLE and _DB_KEY:
            # Use parameterized binding to avoid SQL injection in the key PRAGMA.
            # pysqlcipher3 supports the key pragma via executescript; we use
            # execute with a format that is safe because PRAGMA key requires the
            # literal value — the recommended approach for pysqlcipher3 is to
            # pass the key through the connect() call or via a dedicated cursor.
            # We use a prepared statement with Python string formatting only after
            # validating that the key contains no single-quote characters.
            safe_key = _DB_KEY.replace("'", "")
            if safe_key != _DB_KEY:
                raise ValueError("LEAPXO_DB_KEY must not contain single-quote characters.")
            conn.execute(f"PRAGMA key='{safe_key}'")

        # Enable WAL for concurrent readers + single writer
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        self._conn = conn
        self._migrate()
        logger.info("Database opened: %s (WAL mode)", self._path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Schema migrations
    # ------------------------------------------------------------------
    def _migrate(self) -> None:
        assert self._conn
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agents (
                model_hash  TEXT PRIMARY KEY,
                label       TEXT NOT NULL,
                trust_score REAL NOT NULL DEFAULT 1.0,
                version     INTEGER NOT NULL DEFAULT 1,
                archived    INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                model_hash  TEXT,
                payload     TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS telemetry (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                value       REAL NOT NULL,
                labels      TEXT,
                recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Generic query helpers (thread-safe via asyncio.Lock)
    # ------------------------------------------------------------------
    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """Execute a write statement; returns lastrowid."""
        async with self._lock:
            assert self._conn, "Database not connected"
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute a read query and return all rows as dicts."""
        assert self._conn, "Database not connected"
        cur = self._conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Execute a read query and return the first row as a dict (or None)."""
        assert self._conn, "Database not connected"
        cur = self._conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Optimistic locking helpers
    # ------------------------------------------------------------------
    async def update_with_version(
        self,
        table: str,
        updates: dict[str, Any],
        where_key: str,
        where_value: Any,
        expected_version: int,
    ) -> bool:
        """
        Perform an optimistic-lock UPDATE.

        Returns True on success, False when the row's version does not match
        `expected_version` (i.e. a concurrent writer modified the row first).
        """
        set_clauses = ", ".join(f"{col} = ?" for col in updates if col != "version")
        set_clauses += ", version = version + 1, updated_at = datetime('now')"
        values = [v for k, v in updates.items() if k != "version"]
        values += [where_value, expected_version]

        sql = f"UPDATE {table} SET {set_clauses} WHERE {where_key} = ? AND version = ?"
        async with self._lock:
            assert self._conn, "Database not connected"
            cur = self._conn.execute(sql, values)
            self._conn.commit()
            return cur.rowcount == 1

    # ------------------------------------------------------------------
    # Agent-specific helpers
    # ------------------------------------------------------------------
    async def upsert_agent(self, model_hash: str, label: str, trust_score: float) -> None:
        await self.execute(
            """
            INSERT INTO agents (model_hash, label, trust_score)
            VALUES (?, ?, ?)
            ON CONFLICT(model_hash) DO UPDATE SET
                trust_score = excluded.trust_score,
                updated_at  = datetime('now')
            """,
            (model_hash, label, trust_score),
        )

    async def update_trust(
        self, model_hash: str, trust_score: float, expected_version: int
    ) -> bool:
        return await self.update_with_version(
            table="agents",
            updates={"trust_score": trust_score},
            where_key="model_hash",
            where_value=model_hash,
            expected_version=expected_version,
        )

    async def archive_agent(self, model_hash: str) -> None:
        await self.execute(
            "UPDATE agents SET archived = 1, updated_at = datetime('now') WHERE model_hash = ?",
            (model_hash,),
        )

    async def list_agents(self, archived: bool = False) -> list[dict[str, Any]]:
        return await self.fetchall(
            "SELECT * FROM agents WHERE archived = ? ORDER BY trust_score DESC",
            (1 if archived else 0,),
        )

    # ------------------------------------------------------------------
    # Telemetry helpers
    # ------------------------------------------------------------------
    async def record_telemetry(self, metric_name: str, value: float, labels: str = "") -> None:
        await self.execute(
            "INSERT INTO telemetry (metric_name, value, labels) VALUES (?, ?, ?)",
            (metric_name, value, labels),
        )

    async def audit(self, event_type: str, model_hash: str = "", payload: str = "") -> None:
        await self.execute(
            "INSERT INTO audit_events (event_type, model_hash, payload) VALUES (?, ?, ?)",
            (event_type, model_hash, payload),
        )


# ---------------------------------------------------------------------------
# Module-level singleton (initialised in FastAPI lifespan)
# ---------------------------------------------------------------------------
_db: Database | None = None


def get_db() -> Database:
    """Return the module-level database singleton (must be initialised first)."""
    if _db is None:
        raise RuntimeError("Database has not been initialised. Call init_db() first.")
    return _db


def init_db(path: str = _DEFAULT_DB_PATH) -> Database:
    """Initialise and return the module-level database singleton."""
    global _db
    _db = Database(path)
    _db.connect()
    return _db


def close_db() -> None:
    """Close the module-level database singleton."""
    global _db
    if _db:
        _db.close()
        _db = None
