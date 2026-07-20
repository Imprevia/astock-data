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


_TRAVERSAL_RE = re.compile(r"[\x00/\\]|\.\.")


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

    # ------------------------------------------------------------------
    # General-key API (for non-A-share sub-keys: sector codes BK0447, ETF
    # codes 512480, intraday hour buckets, etc.). Reuses the same table;
    # the ``ticker`` column stores the free-form ``sub_key`` verbatim.
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_sub_key(sub_key: str) -> str:
        """Validate a general-purpose cache sub-key.

        Unlike :func:`_validate_ticker`, accepts any non-empty string that is
        not a path-traversal / control-char vector (so sector codes like
        ``BK0447``, ETF codes like ``512480`` and hour buckets like
        ``2026-07-20-15`` are all admissible).
        """
        if not isinstance(sub_key, str) or not sub_key.strip():
            raise InvalidTickerError(
                f"Invalid general cache sub_key: {sub_key!r}"
            )
        if _TRAVERSAL_RE.search(sub_key):
            raise InvalidTickerError(
                f"Unsafe general cache sub_key: {sub_key!r}"
            )
        return sub_key

    def write_general(
        self,
        kind: str,
        sub_key: str,
        trade_date: str,
        payload: dict[str, Any],
        *,
        created_at: dt.datetime | None = None,
    ) -> None:
        """Write a payload under a free-form ``sub_key`` (sector/ETF/hour bucket).

        Mirrors :meth:`write` but skips the A-share ticker regex, so callers
        dealing with non-ticker entities (industry sectors ``BK0447``, ETF
        codes ``512480``, intraday snapshot buckets ``2026-07-20-15``) can
        share the same SQLite store without a schema migration.
        """
        safe_sub = self._validate_sub_key(sub_key)
        safe_trade_date = _validate_trade_date(trade_date)

        born_at = created_at if created_at is not None else dt.datetime.now(tz=dt.UTC)
        expires_at = born_at + self._ttl

        key = f"{kind}:{safe_sub}:{safe_trade_date}"
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
                        safe_sub,
                        safe_trade_date,
                        born_at.isoformat(),
                        expires_at.isoformat(),
                        payload_json,
                    ),
                )

    def read_general(
        self,
        kind: str,
        sub_key: str,
        trade_date: str,
        *,
        now: dt.datetime | None = None,
    ) -> dict[str, Any] | None:
        """Read a payload written via :meth:`write_general`."""
        safe_sub = self._validate_sub_key(sub_key)
        safe_trade_date = _validate_trade_date(trade_date)

        key = f"{kind}:{safe_sub}:{safe_trade_date}"
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

    def read_latest(
        self,
        kind: str,
        sub_key: str,
        target_date: str,
        max_fallback_days: int = 3,
        *,
        now: dt.datetime | None = None,
    ) -> tuple[dict[str, Any], str] | None:
        """Return the freshest non-expired payload for ``sub_key``.

        Searches the most recent ``max_fallback_days + 1`` trade dates
        (target_date first, then earlier days). Within each date the lookup is
        a *prefix match*: if ``sub_key`` is an hour bucket like
        ``2026-07-20-15`` the trailing hour segment is dropped and any snapshot
        from any hour of that day matches (the newest ``created_at`` wins), so
        an intraday snapshot taken at 11:00 is still served when the caller
        asks at 15:00 and the live push2 endpoint is blocked. Mirrors the
        ``clist_cache.load_latest`` fallback semantics of the daily-review
        step-2 workflow before this data source was migrated into the data
        layer.

        :returns: ``(payload, actual_trade_date)`` or ``None`` when no fresh
            snapshot exists within the fallback window.
        """
        safe_sub = self._validate_sub_key(sub_key)
        current = now if now is not None else dt.datetime.now(tz=dt.UTC)
        try:
            target = dt.date.fromisoformat(_validate_trade_date(target_date))
        except InvalidTickerError:
            return None

        # Drop a trailing "-HH" hour segment so intraday snapshots collapse to
        # one daily prefix; bare sub_keys (sector/ETF codes) are unaffected.
        prefix = safe_sub.rsplit("-", 1)[0] if safe_sub.rsplit("-", 1)[-1].isdigit() else safe_sub
        like_pattern = f"{prefix}%"

        for fallback in range(max_fallback_days + 1):
            actual_date = (target - dt.timedelta(days=fallback)).isoformat()
            cursor = self._conn.execute(
                "SELECT payload_json, expires_at FROM structured_cache "
                "WHERE kind = ? AND trade_date = ? AND ticker LIKE ? "
                "ORDER BY created_at DESC LIMIT 1",
                (kind, actual_date, like_pattern),
            )
            row = cursor.fetchone()
            if row is None:
                continue
            payload_json, expires_at_raw = row
            expires_at = dt.datetime.fromisoformat(expires_at_raw)
            if expires_at <= current:
                continue
            return json.loads(payload_json), actual_date
        return None
