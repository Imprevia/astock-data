"""CSV-backed K-line (OHLCV) cache.

Stores each ticker's daily OHLCV bars as a plain UTF-8 CSV file under an
explicit ``base_dir``. Freshness is controlled by a TTL measured against the
cache file's modification time (``created_at`` may be injected for testing).
"""

from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Sequence

from astock_data.errors import InvalidTickerError

if TYPE_CHECKING:
    from astock_data.models.market import OHLCVBar

# A-share 6-digit instrument codes: Shanghai (6), Shenzhen (0/3), Beijing (8).
_TICKER_RE = re.compile(r"^[0368]\d{5}$")
_PERIOD_RE = re.compile(r"^(day|week|month|1min|5min|15min|30min|60min)$")

_HEADER = ["date", "open", "high", "low", "close", "volume"]


def _validate_ticker(code: str) -> str:
    """Return ``code`` only if it is a safe, normalized A-share ticker.

    Rejects anything that is not exactly a 6-digit A-share code, which also
    defends against path-traversal payloads such as ``../evil``.
    """

    if not isinstance(code, str) or not _TICKER_RE.match(code):
        raise InvalidTickerError(f"Invalid A-share ticker for cache key: {code!r}")
    return code


def _validate_period(period: str) -> str:
    if not isinstance(period, str) or not _PERIOD_RE.match(period):
        raise InvalidTickerError(f"Invalid K-line period for cache key: {period!r}")
    return period


class CsvKlineCache:
    """Append-friendly CSV cache of daily OHLCV bars keyed by ticker code."""

    def __init__(
        self,
        base_dir: Path,
        ttl: dt.timedelta = dt.timedelta(hours=12),
    ) -> None:
        self._base_dir = Path(base_dir)
        self._ttl = ttl

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _path_for(self, code: str, *, period: str = "day") -> Path:
        safe_code = _validate_ticker(code)
        safe_period = _validate_period(period)
        # ``safe_code`` is validated to be 6 ASCII digits, so it can never
        # escape ``base_dir`` via path separators or ``..``.
        suffix = "" if safe_period == "day" else f"-{safe_period}"
        return self._base_dir / f"{safe_code}{suffix}.csv"

    def _is_fresh(self, path: Path, now: dt.datetime) -> bool:
        mtime_ts = path.stat().st_mtime
        mtime = dt.datetime.fromtimestamp(mtime_ts, tz=dt.UTC)
        return (now - mtime) < self._ttl

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def write(
        self,
        code: str,
        rows: Sequence[OHLCVBar],
        *,
        period: str = "day",
        created_at: dt.datetime | None = None,
    ) -> Path:
        """Write ``rows`` to ``<base_dir>/<code>.csv`` as UTF-8 CSV.

        When ``created_at`` is supplied (used by tests to simulate aging),
        the file's modification time is pinned to that moment so the TTL
        comparison behaves deterministically.
        """

        # Import locally to keep the cache layer free of model import-time
        # side effects and avoid hard coupling at module load.
        from astock_data.models.market import OHLCVBar  # noqa: F401  (type hint sanity)

        path = self._path_for(code, period=period)
        self._base_dir.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(_HEADER)
            for bar in rows:
                writer.writerow(
                    [
                        str(bar.date),
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume,
                    ]
                )

        if created_at is not None:
            ts = created_at.timestamp()
            # mtime + atime so the file looks "born" at created_at.
            import os

            os.utime(path, (ts, ts))

        return path

    def read(
        self,
        code: str,
        *,
        period: str = "day",
        now: dt.datetime | None = None,
    ) -> list[OHLCVBar] | None:
        """Return cached bars for ``code`` if present and fresh, else ``None``."""

        from astock_data.models.market import OHLCVBar

        path = self._path_for(code, period=period)
        if not path.exists():
            return None

        current = now if now is not None else dt.datetime.now(tz=dt.UTC)
        if not self._is_fresh(path, current):
            return None

        bars: list[OHLCVBar] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header is None:
                return bars
            for raw in reader:
                if not raw:
                    continue
                bars.append(
                    OHLCVBar(
                        date=raw[0],
                        open=float(raw[1]),
                        high=float(raw[2]),
                        low=float(raw[3]),
                        close=float(raw[4]),
                        volume=float(raw[5]),
                    )
                )
        return bars
