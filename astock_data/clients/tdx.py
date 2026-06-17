"""mootdx (通达信) wrapper client.

Primary vendor for K-line OHLCV, financial snapshot, F10 shareholder research
and the stock name-code map. This wrapper MUST NOT be bypassed: the raw
``mootdx`` client object is never exposed outside this module.

mootdx talks to the通达信 TCP quote servers (default port 7709). It is a
required dependency, but importing it is deferred to first use so that simply
constructing :class:`TdxClient` (and importing this module) never opens a TCP
connection. Live connections only happen when a method is called on a client
that was not injected.

The wrapper is testable via constructor injection: pass any mootdx-like fake
object (with ``stocks`` / ``bars`` / ``F10`` / ``finance`` methods) and no
``Quotes.factory`` call will ever be made.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from astock_data.errors import DataSourceError

__all__ = ["TdxClient"]

# 6-digit A-share ticker regex.
# Covers 0xxxxx (SZ main), 3xxxxx (SZ ChiNext/创业板), 6xxxxx (SH main/STAR),
# AND 8xxxxx / 920xxx (Beijing Exchange / 北交所).
# NOTE: the upstream source project wrongly used ``^[036]\d{5}$`` which silently
# dropped every Beijing Exchange code; this is the fix.
_CODE_RE = re.compile(r"^[0368]\d{5}$")
_PERIOD_CATEGORY = {
    "day": 4,
    "week": 5,
    "month": 6,
    "1min": 8,
    "5min": 0,
    "15min": 1,
    "30min": 2,
    "60min": 3,
}


def _import_mootdx_quotes() -> Any:
    """Import and return ``mootdx.quotes.Quotes``.

    Deferred import so module import / object construction never triggers mootdx
    loading (and therefore never probes the network). Raises
    :class:`DataSourceError` with a clear message if mootdx is unavailable.
    """
    try:
        from mootdx.quotes import Quotes
    except Exception as exc:  # pragma: no cover - exercised via monkeypatch
        raise DataSourceError(
            "mootdx is required for the TdxClient but is not available: "
            f"{exc}. Install it with `pip install mootdx`."
        ) from exc
    return Quotes


class TdxClient:
    """Wrapper around ``mootdx.quotes.Quotes`` (std market factory).

    All public methods return plain ``dict`` / ``list[dict]`` payloads (the
    service layer maps them to Pydantic models). Raw upstream payloads are kept
    accessible (``_raw`` / ``raw``) where useful.
    """

    def __init__(self, client: Any | None = None) -> None:
        """Create a new wrapper.

        :param client: optional injected mootdx-like object exposing
            ``stocks`` / ``bars`` / ``F10`` / ``finance``. When provided, no
            ``Quotes.factory`` call is ever made (use this for tests). When
            ``None`` (default), a real ``Quotes.factory(market="std")`` client
            is lazily created on first use and cached for reuse.
        """
        self._injected = client
        self._lazy_client: Any | None = None

    # ------------------------------------------------------------------
    # lazy singleton
    # ------------------------------------------------------------------
    def _get_client(self) -> Any:
        """Return the underlying mootdx client, creating it lazily on first use.

        Injected clients short-circuit and never touch ``Quotes.factory``.
        """
        if self._injected is not None:
            return self._injected
        if self._lazy_client is None:
            Quotes = _import_mootdx_quotes()
            try:
                self._lazy_client = Quotes.factory(market="std")
            except Exception as exc:
                raise DataSourceError(
                    f"Failed to initialize mootdx Quotes client: {exc}"
                ) from exc
        return self._lazy_client

    # ------------------------------------------------------------------
    # stock list / name-code map
    # ------------------------------------------------------------------
    def stocks(self) -> list[dict]:
        """Return the combined SZ (market=0) + SH (market=1) stock list.

        Each entry is ``{"code": str, "name": str}`` with whitespace stripped
        from both fields. Only codes matching ``^[0368]\\d{5}$`` are kept, which
        (importantly) includes Beijing Exchange ``8xxxxx`` codes that mootdx
        bundles into the SZ/SH stock lists.
        """
        client = self._get_client()
        out: list[dict] = []
        seen: set[str] = set()
        for market in (0, 1):  # 0=SZ, 1=SH
            try:
                df = client.stocks(market=market)
            except Exception:
                # A single market failing should not abort the whole list.
                continue
            if df is None:
                continue
            # mootdx returns a pandas DataFrame with 'code' / 'name' columns.
            rows = df.itertuples(index=False) if hasattr(df, "itertuples") else df
            for row in rows:
                code = str(getattr(row, "code", row[0] if isinstance(row, tuple) else "")).strip()
                name = str(getattr(row, "name", row[1] if isinstance(row, tuple) else "")).strip()
                if not _CODE_RE.match(code):
                    continue
                if code in seen:
                    continue
                seen.add(code)
                # Collapse all internal whitespace (incl. full-width 　 U+3000).
                clean_name = re.sub(r"[\s\u3000]+", "", name)
                out.append({"code": code, "name": clean_name})
        return out

    def build_name_map(self) -> tuple[dict[str, str], dict[str, str]]:
        """Build ``(name_to_code, code_to_name)`` dictionaries from
        :meth:`stocks`.

        Names are whitespace-collapsed (matching :meth:`stocks`). When a name
        collision occurs the first-seen mapping wins.
        """
        name_to_code: dict[str, str] = {}
        code_to_name: dict[str, str] = {}
        for entry in self.stocks():
            code = entry["code"]
            name = entry["name"]
            code_to_name.setdefault(code, name)
            name_to_code.setdefault(name, code)
        return name_to_code, code_to_name

    # ------------------------------------------------------------------
    # K-line OHLCV
    # ------------------------------------------------------------------
    def bars(self, code: str, period: str = "day", offset: int = 800) -> list[dict]:
        """Fetch OHLCV bars for ``code`` at the requested K-line period.

        Uses mootdx ``category`` mapping: day=4, week=5, month=6, 1min=8,
        5min=0, 15min=1, 30min=2, 60min=3. Returns rows normalized to keys
        ``date, open, high, low, close, volume``; ``amount`` and the redundant
        ``year/month/day/hour/minute/datetime`` columns are dropped.
        """
        category = _PERIOD_CATEGORY.get(period)
        if category is None:
            supported = ", ".join(_PERIOD_CATEGORY)
            raise ValueError(f"Unsupported K-line period: {period!r}. Supported: {supported}")
        client = self._get_client()
        df = client.bars(symbol=code, category=category, offset=offset)
        if df is None:
            return []
        rows: list[dict] = []
        # mootdx exposes both an index and a column named 'datetime' plus split
        # year/month/day/hour/minute/volume columns. Normalise defensively.
        if hasattr(df, "iterrows"):
            iterator = df.to_dict(orient="records")
        else:  # pragma: no cover - defensive for non-DataFrame payloads
            iterator = df
        for rec in iterator:
            date = rec.get("datetime", rec.get("date"))
            if date is None and all(k in rec for k in ("year", "month", "day")):
                hour = int(rec.get("hour") or 0)
                minute = int(rec.get("minute") or 0)
                date = dt.datetime(int(rec["year"]), int(rec["month"]), int(rec["day"]), hour, minute)
            if hasattr(date, "strftime"):
                date = date.strftime("%Y-%m-%d" if period in {"day", "week", "month"} else "%Y-%m-%d %H:%M")
            elif isinstance(date, str) and period in {"1min", "5min", "15min", "30min", "60min"} and len(date) >= 16:
                date = date[:16]
            elif isinstance(date, str) and period in {"day", "week", "month"} and len(date) >= 10:
                date = date[:10]
            rows.append(
                {
                    "date": str(date) if date is not None else None,
                    "open": rec.get("open"),
                    "high": rec.get("high"),
                    "low": rec.get("low"),
                    "close": rec.get("close"),
                    "volume": rec.get("volume"),
                }
            )
        return rows

    def daily_bars(self, code: str, offset: int = 800) -> list[dict]:
        """Backward-compatible alias for daily K-line bars."""
        return self.bars(code, period="day", offset=offset)

    # ------------------------------------------------------------------
    # financial snapshot
    # ------------------------------------------------------------------
    # Best-effort mapping of mootdx finance struct field names (mandarin pinyin)
    # to readable keys. Field presence depends on the underlying struct version.
    _FINANCE_FIELD_MAP: dict[str, str] = {
        "liutongguben": "float_shares",  # 流通股本
        "guben": "total_shares",  # 总股本
        "lirunzonge": "profit_amount",  # 利润总额
        "jingzichan": "net_assets",  # 净资产
        "meigujingzichan": "nav_per_share",  # 每股净资产
        "yingyeshouru": "operating_revenue",  # 营业收入
        "yingyejingchengben": "operating_cost",  # 营业成本
        "meigushouyi": "eps",  # 每股收益
        "maolilv": "gross_margin",  # 毛利率
    }

    def financial_snapshot(self, code: str) -> dict:
        """Return a best-effort normalized financial snapshot for ``code``.

        mootdx's ``finance`` call returns a single-row struct with mandarin
        pinyin keys; the readable mapped subset lives at top level and the full
        raw payload is preserved under ``_raw``.
        """
        client = self._get_client()
        df = client.finance(symbol=code)
        raw: dict[str, Any] = {}
        if df is not None:
            records = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
            if records:
                raw = dict(records[0])
        snapshot: dict[str, Any] = {"code": code}
        for src, dst in self._FINANCE_FIELD_MAP.items():
            if src in raw:
                snapshot[dst] = raw[src]
        snapshot["_raw"] = raw
        return snapshot

    # ------------------------------------------------------------------
    # F10 shareholder research
    # ------------------------------------------------------------------
    def f10_shareholders(self, code: str) -> dict:
        """Return the F10 shareholder-research text for ``code``.

        Uses ``client.F10(symbol=code, name="股东研究")``. The result is
        ``{"content": str, "sections": dict | None}`` where ``content`` is the
        raw text and ``sections`` is a best-effort parse of the ``【N.title】``
        section headers (``None`` if parsing fails or text is empty).
        """
        client = self._get_client()
        text = client.F10(symbol=code, name="股东研究")
        if text is None:
            text = ""
        text = str(text)
        return {"content": text, "sections": self._parse_f10_sections(text)}

    @staticmethod
    def _parse_f10_sections(text: str) -> dict[str, str] | None:
        """Split F10 text on ``【N. title】`` headers into ``{title: body}``.

        Returns ``None`` when the text is empty or no section headers are
        found (best-effort, never raises).
        """
        if not text.strip():
            return None
        marks = list(re.finditer(r"【\s*\d+[\.、]?\s*([^】]+)】", text))
        if not marks:
            return None
        sections: dict[str, str] = {}
        for idx, m in enumerate(marks):
            title = m.group(1).strip()
            body_start = m.end()
            body_end = marks[idx + 1].start() if idx + 1 < len(marks) else len(text)
            sections[title] = text[body_start:body_end].strip()
        return sections
