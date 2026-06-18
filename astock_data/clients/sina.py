"""Sina Finance HTTP clients (K-line fallback, financial reports, news).

Fetches + parses raw Sina responses (JSONP/JSON kline, JSON financial reports,
GBK news HTML) into plain dicts/lists. Clients do ONLY transport + parsing.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Optional

import requests

from ..errors import DataSourceError

__all__ = ["SinaClient"]


# report_type alias -> Sina ``source`` parameter.
_REPORT_TYPE_MAP = {
    "balance": "fzb",  # 资产负债表
    "income": "lrb",  # 利润表
    "cashflow": "llb",  # 现金流量表
}

# Regex extracting news rows from Sina's GBK stock-news HTML page.
_NEWS_ROW_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})\s*(?:&nbsp;)*(\d{2}:\d{2})\s*(?:&nbsp;)*"
    r"<a[^>]+href='([^']+)'[^>]*>([^<]+)</a>"
)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

_KLINE_SCALE = {
    "5min": "5",
    "15min": "15",
    "30min": "30",
    "60min": "60",
    "day": "240",
    "week": "1680",
    "month": "7200",
}

_INDEX_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("sh", "s_sh000001"),
    ("sz", "s_sz399001"),
    ("cyb", "s_sz399006"),
    ("kc50", "s_sh000688"),
    ("hs300", "s_sh000300"),
    ("zz500", "s_sh000905"),
)


def _shsz_prefix(code: str) -> str:
    """Map a 6-digit code to ``sh``/``sz`` for Sina endpoints."""
    if code.startswith(("6", "9")):
        return "sh"
    return "sz"


def _to_float(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


class SinaClient:
    """Thin HTTP client for Sina Finance fallback data sources.

    Parameters
    ----------
    session:
        Optional injected ``requests.Session`` for testability.
    timeout:
        Per-request timeout in seconds.
    """

    KLINE_URL = (
        "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "CN_MarketData.getKLineData"
    )
    FINANCE_URL = (
        "https://quotes.sina.cn/cn/api/openapi.php/"
        "CompanyFinanceService.getFinanceReport2022"
    )
    NEWS_URL = (
        "https://vip.stock.finance.sina.com.cn/corp/view/"
        "vCB_AllNewsStock.php"
    )
    QUOTE_URL = "https://hq.sinajs.cn/list="
    MARKET_CENTER_URL = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "Market_Center.getHQNodeData"
    )

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        timeout: float = 15.0,
    ) -> None:
        self._session = session
        self._timeout = timeout

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    # ------------------------------------------------------------------
    # K-line (daily OHLCV fallback)
    # ------------------------------------------------------------------

    def kline(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "day",
    ) -> list[dict]:
        """Fetch K-line bars from the Sina endpoint.

        Each returned row is ``{date, open, high, low, close, volume}`` in
        ascending date order.
        """
        scale = _KLINE_SCALE.get(period)
        if scale is None:
            supported = ", ".join(_KLINE_SCALE)
            raise ValueError(f"Unsupported Sina K-line period: {period!r}. Supported: {supported}")
        prefix = _shsz_prefix(code)
        params = {
            "symbol": f"{prefix}{code}",
            "scale": scale,
            "ma": "no",
            "datalen": "800",
        }
        data = self._get_json(self.KLINE_URL, params=params)

        if not isinstance(data, list):
            return []

        rows: list[dict] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            day = item.get("day", "")
            if start_date and day < start_date:
                continue
            if end_date and day > end_date:
                continue
            rows.append(
                {
                    "date": day,
                    "open": _to_float(item.get("open")),
                    "high": _to_float(item.get("high")),
                    "low": _to_float(item.get("low")),
                    "close": _to_float(item.get("close")),
                    "volume": _to_int(item.get("volume")),
                }
            )
        return rows

    # ------------------------------------------------------------------
    # Quote snapshots and market rows (market breadth fallback)
    # ------------------------------------------------------------------

    def index_snapshots(self) -> dict[str, dict]:
        """Fetch fixed index quote snapshots from Sina short quote format."""

        try:
            resp = self.session.get(
                self.QUOTE_URL + ",".join(symbol for _, symbol in _INDEX_SYMBOLS),
                headers={"User-Agent": _USER_AGENT, "Referer": "https://finance.sina.com.cn/"},
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise DataSourceError(f"Sina index quote request failed: {exc}") from exc

        try:
            text = resp.content.decode("gbk")
        except (UnicodeDecodeError, LookupError) as exc:
            raise DataSourceError(f"Sina index quote GBK decode failed: {exc}") from exc

        parsed = self._parse_short_quotes(text)
        result: dict[str, dict] = {}
        for key, symbol in _INDEX_SYMBOLS:
            row = parsed.get(symbol)
            if row:
                result[key] = row
        if not result:
            raise DataSourceError("Sina index quote returned no usable rows")
        return result

    def market_page(self, *, page: int = 1, page_size: int = 80) -> list[dict]:
        """Fetch one Sina A-share market page normalized for limit statistics."""

        params = {
            "page": str(page),
            "num": str(page_size),
            "sort": "symbol",
            "asc": "1",
            "node": "hs_a",
            "symbol": "",
            "_s_r_a": "page",
        }
        data = self._get_json(self.MARKET_CENTER_URL, params=params)
        if not isinstance(data, list):
            return []
        return self.normalize_market_rows(item for item in data if isinstance(item, Mapping))

    def market_all(self, *, page_size: int = 80, max_pages: int = 80) -> list[dict]:
        """Fetch Sina A-share market rows with a conservative page cap."""

        rows: list[dict] = []
        for page in range(1, max_pages + 1):
            page_rows = self.market_page(page=page, page_size=page_size)
            if not page_rows:
                break
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
        return rows

    @staticmethod
    def _parse_short_quotes(raw: str) -> dict[str, dict]:
        rows: dict[str, dict] = {}
        for line in raw.strip().split(";"):
            if "=" not in line or '"' not in line:
                continue
            symbol = line.split("=", 1)[0].split("hq_str_", 1)[-1].strip()
            payload = line.split('"', 2)[1]
            values = payload.split(",")
            if len(values) < 4 or not values[0]:
                continue
            rows[symbol] = {
                "name": values[0],
                "price": _to_float(values[1]),
                "change": _to_float(values[2]),
                "change_pct": _to_float(values[3]),
            }
        return rows

    @staticmethod
    def normalize_market_rows(rows: object) -> list[dict]:
        """Normalize Sina market-center rows into quote-row shape."""

        normalized: list[dict] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            code = str(row.get("code") or row.get("symbol") or "").strip()
            if code.startswith(("sh", "sz", "bj")):
                code = code[2:]
            if not code:
                continue
            normalized.append(
                {
                    "code": code,
                    "name": str(row.get("name") or "").strip(),
                    "close": _to_float(row.get("trade") or row.get("price")),
                    "change_pct": _to_float(row.get("changepercent") or row.get("change_pct")),
                }
            )
        return normalized

    # ------------------------------------------------------------------
    # Financial reports (balance / income / cashflow)
    # ------------------------------------------------------------------

    def financial_report(
        self,
        code: str,
        report_type: str,
        freq: str = "quarterly",
    ) -> list[dict]:
        """Fetch a Sina financial report table.

        ``report_type`` accepts ``balance`` (fzb), ``income`` (lrb) or
        ``cashflow`` (llb). Each returned row carries ``report_date`` plus the
        raw Chinese-field dict straight from Sina (field names are unstable, so
        the raw dict is preserved verbatim).
        """
        source_type = _REPORT_TYPE_MAP.get(report_type)
        if source_type is None:
            raise DataSourceError(
                f"Unknown Sina report_type '{report_type}'; "
                "expected one of: balance, income, cashflow"
            )

        prefix = _shsz_prefix(code)
        params = {
            "paperCode": f"{prefix}{code}",
            "source": source_type,
            "type": "0",
            "page": "1",
            "num": "20",
        }
        d = self._get_json(self.FINANCE_URL, params=params)
        if not isinstance(d, dict):
            return []

        items = d.get("result", {}).get("data", {}).get(source_type, [])
        if not isinstance(items, list) or not items:
            return []

        rows: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            # Sina uses the Chinese column header ``报告日`` for report date.
            report_date = item.get("报告日", "")
            rows.append({"report_date": report_date, "fields": dict(item)})
        return rows

    # ------------------------------------------------------------------
    # News (GBK HTML fallback)
    # ------------------------------------------------------------------

    def news(self, code: str, page_size: int = 20) -> list[dict]:
        """Fetch stock-specific news from the Sina GBK HTML fallback page.

        Each item is ``{title, content="", time, source="新浪财经", url}``.
        """
        prefix = _shsz_prefix(code)
        url = self.NEWS_URL
        params = {"symbol": f"{prefix}{code}", "Page": "1"}

        try:
            resp = self.session.get(
                url,
                params=params,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Referer": "https://finance.sina.com.cn/",
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise DataSourceError(f"Sina news request failed: {exc}") from exc

        # Sina news page is GB2312-encoded.
        try:
            html = resp.content.decode("gb2312", errors="replace")
        except LookupError:
            html = resp.text

        articles: list[dict] = []
        for date_str, time_str, link, title in _NEWS_ROW_RE.findall(html)[
            :page_size
        ]:
            articles.append(
                {
                    "title": title.strip(),
                    "content": "",
                    "time": f"{date_str} {time_str}",
                    "source": "新浪财经",
                    "url": link,
                }
            )
        return articles

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _get_json(self, url: str, params: dict) -> object:
        """GET ``url`` with ``params`` and return parsed JSON.

        Sina JSONP/JSON endpoints return a JSON document that ``requests``
        cannot always auto-detect, so we parse ``resp.text`` explicitly.
        Raises :class:`DataSourceError` on HTTP or JSON failures.
        """
        try:
            resp = self.session.get(
                url,
                params=params,
                headers={"User-Agent": _USER_AGENT},
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise DataSourceError(
                f"Sina request failed for {url}: {exc}"
            ) from exc

        text = resp.text.strip()
        if not text:
            raise DataSourceError(f"Sina returned empty body for {url}")

        try:
            return json.loads(text)
        except (ValueError, json.JSONDecodeError) as exc:
            raise DataSourceError(
                f"Sina JSON parse failed for {url}: {exc}"
            ) from exc
