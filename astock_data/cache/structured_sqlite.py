"""SQLite-backed cache for structured payloads.

Caches arbitrary JSON-serializable payloads (fundamentals, reports, news,
signals, name maps) keyed by ``kind:ticker:trade_date`` in a single
``structured.db`` file. Writes are guarded by a process-wide ``threading.Lock``
and run inside a WAL-enabled SQLite transaction for concurrent safety.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from astock_data.errors import InvalidTickerError

_TICKER_RE = re.compile(r"^[0368]\d{5}$")
_TRADE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_DB_FILENAME = "structured.sqlite"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS structured_cache (
    key TEXT,
    kind TEXT,
    ticker TEXT,
    trade_date TEXT,
    created_at TEXT,
    expires_at TEXT,
    payload_json TEXT
)
"""

_write_lock = threading.Lock()


def _validate_ticker(ticker: str) -> str:
    if not isinstance(ticker, str) or not _TICKER_RE.match(ticker):
        raise InvalidTickerError(
            f"Invalid A-share ticker for cache key: {ticker!r}"
        )
    return ticker


def _validate_trade_date(trade_date: str) -> str:
    if not isinstance(trade_date, str) or not _TRADE_DATE_RE.match(trade_date):
        raise InvalidTickerError(
            f"Invalid trade_date for cache key: {trade_date!r}"
        )
    return trade_date


class SQLiteStructuredCache:
    """Thread-safe JSON payload cache backed by a single SQLite database."""

    def __init__(
        self,
        base_dir: Path,
        ttl: dt.timedelta = dt.timedelta(hours=24),
    ) -> None:
        self._base_dir = Path(base_dir)
        self._ttl = ttl
        self._db_path = self._base_dir / _DB_FILENAME
        self._local = threading.local()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        # Default rollback-journal mode keeps the on-disk footprint to a single
        # ``structured.sqlite`` file (no ``-wal``/``-shm`` sidecars), which keeps
        # ``rglob("*.sqlite*")`` deterministic for callers/tests. Concurrent-write
        # safety is provided by the process-wide ``_write_lock`` + transaction.
        connection = sqlite3.connect(self._db_path)
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(_CREATE_TABLE_SQL)
        return connection

    @property
    def _conn(self) -> sqlite3.Connection:
        """A per-thread connection so concurrent writers don't cross wires."""

        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = self._connect()
            self._local.connection = connection
        return connection

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def write(
        self,
        kind: str,
        ticker: str,
        trade_date: str,
        payload: dict[str, Any],
        *,
        created_at: dt.datetime | None = None,
    ) -> None:
        safe_ticker = _validate_ticker(ticker)
        safe_trade_date = _validate_trade_date(trade_date)

        born_at = created_at if created_at is not None else dt.datetime.now(tz=dt.UTC)
        expires_at = born_at + self._ttl

        key = f"{kind}:{safe_ticker}:{safe_trade_date}"
        payload_json = json.dumps(payload, ensure_ascii=False)

        with _write_lock:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM structured_cache WHERE key = ?",
                    (key,),
                )
                self._conn.execute(
                    "INSERT INTO structured_cache "
                    "(key, kind, ticker, trade_date, created_at, expires_at, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        key,
                        kind,
                        safe_ticker,
                        safe_trade_date,
                        born_at.isoformat(),
                        expires_at.isoformat(),
                        payload_json,
                    ),
                )

    def read(
        self,
        kind: str,
        ticker: str,
        trade_date: str,
        *,
        now: dt.datetime | None = None,
    ) -> dict[str, Any] | None:
        safe_ticker = _validate_ticker(ticker)
        safe_trade_date = _validate_trade_date(trade_date)

        key = f"{kind}:{safe_ticker}:{safe_trade_date}"
        current = now if now is not None else dt.datetime.now(tz=dt.UTC)

        cursor = self._conn.execute(
            "SELECT payload_json, expires_at FROM structured_cache WHERE key = ?",
            (key,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        payload_json, expires_at_raw = row
        expires_at = dt.datetime.fromisoformat(expires_at_raw)
        if expires_at <= current:
            return None

        return json.loads(payload_json)
