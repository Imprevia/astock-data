"""Tencent Finance HTTP client (qt.gtimg.cn).

Fetches + parses raw GBK Tencent real-time quote responses into plain dicts.
Clients do ONLY transport + parsing; no business validation lives here.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Optional

import requests

from ..config import AStockSettings, get_settings
from ..errors import DataSourceError, RateLimitError
from ._http import apply_proxy, build_headers, pick_user_agent, throttled_get

__all__ = ["TencentClient"]


_INDEX_CODES: tuple[tuple[str, str], ...] = (
    ("sh", "sh000001"),
    ("sz", "sz399001"),
    ("cyb", "sz399006"),
    ("kc50", "sh000688"),
    ("hs300", "sh000300"),
    ("zz500", "sh000905"),
)


def _market_prefix(code: str) -> str:
    """Map a 6-digit A-share code to its Tencent market prefix.

    Rules: ``920``/``43``/``8`` -> ``bj`` (Beijing Exchange), other leading
    ``5``/``6``/``9`` -> ``sh`` (Shanghai), everything else -> ``sz`` (Shenzhen).
    """
    if not code:
        return "sz"
    if code.startswith(("920", "43", "8")):
        return "bj"
    if code.startswith(("5", "6", "9")):
        return "sh"
    return "sz"


def _to_float(value: str) -> float:
    """Parse a Tencent field into float; empty/garbage -> 0.0."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Indices into the ``~``-delimited Tencent quote payload. These mirror the
# upstream field layout (tradingagents/dataflows/a_stock.py:_tencent_quote).
_FIELD_INDEXES = {
    "name": 1,
    "price": 3,
    "last_close": 4,
    "open": 5,
    "vendor_timestamp": 30,
    "change_pct": 32,
    "high": 33,
    "low": 34,
    "volume": 36,
    "amount_wan": 37,
    "turnover_pct": 38,
    "pe_ttm": 39,
    "mcap_yi": 44,
    "float_mcap_yi": 45,
    "pb": 46,
    "limit_up": 47,
    "limit_down": 48,
    "pe_static": 52,
}
_NUMERIC_FIELDS = {
    "price",
    "last_close",
    "open",
    "change_pct",
    "high",
    "low",
    "volume",
    "amount_wan",
    "turnover_pct",
    "pe_ttm",
    "mcap_yi",
    "float_mcap_yi",
    "pb",
    "limit_up",
    "limit_down",
    "pe_static",
}


class TencentClient:
    """Thin HTTP client for Tencent Finance batch real-time quotes.

    Parameters
    ----------
    session:
        Optional injected ``requests.Session`` for testability (Keep-Alive,
        mocking). When ``None`` a fresh session is created on demand.
    timeout:
        Per-request timeout in seconds.
    settings:
        Optional runtime settings for timeout, user-agent pool, and proxy.
    """

    QUOTE_URL = "https://qt.gtimg.cn/q="
    USER_AGENT = None

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: float | None = None,
        settings: AStockSettings | None = None,
    ) -> None:
        self._settings = settings if settings is not None else get_settings()
        self._session = session
        self._ua = pick_user_agent(self._settings)
        self._timeout = (
            timeout if timeout is not None else self._settings.request_timeout
        )
        if self._session is not None:
            apply_proxy(self._session, self._settings)

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            apply_proxy(self._session, self._settings)
        return self._session

    def quote(self, codes: list[str]) -> dict[str, dict]:
        """Fetch and parse batch real-time quotes for ``codes``.

        Returns a mapping ``{code: {name, price, last_close, open,
        vendor_timestamp, change_pct, high, low, volume, amount_wan,
        turnover_pct, pe_ttm, mcap_yi, float_mcap_yi, pb, limit_up,
        limit_down, pe_static}}``. ``volume`` is measured in lots and
        ``amount_wan`` in ten-thousand yuan.
        """
        if not codes:
            return {}

        prefixed = [f"{_market_prefix(c)}{c}" for c in codes]
        return self._quote_prefixed(prefixed)

    def order_book(self, code: str) -> dict:
        """Fetch one Tencent five-level order-book snapshot.

        Bid/ask volumes are returned in the vendor's native ``volume_lots``
        unit, where one lot represents 100 shares. The vendor timestamp is
        preserved as ``YYYYMMDDHHMMSS`` local exchange time.
        """

        prefixed = f"{_market_prefix(code)}{code}"
        raw = self._fetch_raw([prefixed])
        return self._parse_order_books(raw).get(code, {})

    def index_snapshots(self) -> dict[str, dict]:
        """Fetch fixed market index snapshots from Tencent batch quotes."""

        rows = self._quote_prefixed(
            [code for _, code in _INDEX_CODES], keep_prefix=True
        )
        result: dict[str, dict] = {}
        for key, prefixed_code in _INDEX_CODES:
            row = rows.get(prefixed_code)
            if not row:
                continue
            price = _to_optional_float(row.get("price"))
            last_close = _to_optional_float(row.get("last_close"))
            change = None
            if price is not None and last_close is not None:
                change = price - last_close
            result[key] = {
                "name": row.get("name", ""),
                "price": price,
                "change": change,
                "change_pct": _to_optional_float(row.get("change_pct")),
            }
        if not result:
            raise DataSourceError("Tencent index quote returned no usable rows")
        return result

    def _quote_prefixed(
        self, prefixed: list[str], *, keep_prefix: bool = False
    ) -> dict[str, dict]:
        if not prefixed:
            return {}

        raw = self._fetch_raw(prefixed)
        try:
            return self._parse(raw, keep_prefix=keep_prefix)
        except DataSourceError:
            raise
        except Exception as exc:  # malformed payload
            raise DataSourceError(
                f"Tencent quote parse failed: {exc}"
            ) from exc

    def _fetch_raw(self, prefixed: list[str]) -> str:
        """Fetch and decode a Tencent batch quote payload."""

        url = self.QUOTE_URL + ",".join(prefixed)

        try:
            resp = throttled_get(
                vendor="tencent",
                session=self.session,
                url=url,
                min_interval=0.5,
                timeout=self._timeout,
                headers=build_headers("tencent", user_agent=self._ua),
            )
        except RateLimitError:
            raise
        except DataSourceError as exc:
            raise DataSourceError(
                f"Tencent quote request failed: {exc}"
            ) from exc

        try:
            raw = resp.content.decode("gbk")
        except (UnicodeDecodeError, LookupError) as exc:
            raise DataSourceError(
                f"Tencent quote GBK decode failed: {exc}"
            ) from exc
        return raw

    @staticmethod
    def _parse(raw: str, *, keep_prefix: bool = False) -> dict[str, dict]:
        """Parse the raw GBK Tencent payload into a per-code dict."""
        result: dict[str, dict] = {}
        for line in raw.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line or '"' not in line:
                continue
            # key like ``v_sh688017`` -> market-prefixed code ``sh688017``
            head = line.split("=", 1)[0]
            prefixed_key = head.split("_")[-1].strip()
            payload = line.split('"', 2)[1]
            vals = payload.split("~")
            if len(vals) < 53:
                # Skip lines that don't carry full quote fields.
                continue
            code = (
                prefixed_key
                if keep_prefix
                else prefixed_key[2:] if len(prefixed_key) > 2 else prefixed_key
            )

            entry: dict = {}
            for field, idx in _FIELD_INDEXES.items():
                if field in _NUMERIC_FIELDS:
                    entry[field] = _to_float(vals[idx])
                else:
                    entry[field] = vals[idx]
            result[code] = entry
        return result

    @staticmethod
    def _parse_order_books(raw: str) -> dict[str, dict]:
        """Parse five bid and five ask levels from Tencent quote rows."""

        result: dict[str, dict] = {}
        for line in raw.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line or '"' not in line:
                continue
            head = line.split("=", 1)[0]
            prefixed_key = head.split("_")[-1].strip()
            code = prefixed_key[2:] if len(prefixed_key) > 2 else prefixed_key
            vals = line.split('"', 2)[1].split("~")
            if len(vals) < 53:
                continue

            vendor_timestamp = vals[30].strip()
            try:
                datetime.strptime(vendor_timestamp, "%Y%m%d%H%M%S")
            except ValueError:
                continue

            bids = TencentClient._parse_depth_levels(vals, start_index=9)
            asks = TencentClient._parse_depth_levels(vals, start_index=19)
            bid_depth_lots = sum(level["volume_lots"] for level in bids)
            ask_depth_lots = sum(level["volume_lots"] for level in asks)
            total_depth = bid_depth_lots + ask_depth_lots
            spread = asks[0]["price"] - bids[0]["price"] if bids and asks else None
            imbalance = (
                (bid_depth_lots - ask_depth_lots) / total_depth
                if total_depth > 0
                else None
            )
            result[code] = {
                "name": vals[1].strip(),
                "vendor_timestamp": vendor_timestamp,
                "last_price": _to_optional_float(vals[3]),
                "bids": bids,
                "asks": asks,
                "bid_depth_lots": bid_depth_lots,
                "ask_depth_lots": ask_depth_lots,
                "spread": spread,
                "imbalance": imbalance,
            }
        return result

    @staticmethod
    def _parse_depth_levels(
        vals: list[str], *, start_index: int
    ) -> list[dict[str, float | int]]:
        levels: list[dict[str, float | int]] = []
        for position in range(1, 6):
            price_index = start_index + (position - 1) * 2
            volume_index = price_index + 1
            if volume_index >= len(vals):
                break
            price = _to_optional_float(vals[price_index])
            volume_lots = _to_optional_float(vals[volume_index])
            if price is None or price <= 0 or volume_lots is None or volume_lots < 0:
                continue
            levels.append(
                {
                    "position": position,
                    "price": price,
                    "volume_lots": volume_lots,
                }
            )
        return levels

    @staticmethod
    def normalize_market_board_rows(rows: list[Mapping[str, object]]) -> list[dict]:
        """Normalize Tencent market-board-like rows into quote-row shape."""

        normalized: list[dict] = []
        for row in rows:
            code = str(row.get("code") or row.get("symbol") or "").strip()
            if code.startswith(("sh", "sz", "bj")):
                code = code[2:]
            if not code:
                continue
            normalized.append(
                {
                    "code": code,
                    "name": str(row.get("name") or row.get("n") or "").strip(),
                    "close": _to_optional_float(
                        row.get("price") or row.get("p") or row.get("trade")
                    ),
                    "change_pct": _to_optional_float(
                        row.get("change_pct") or row.get("zdf") or row.get("pct")
                    ),
                }
            )
        return normalized
