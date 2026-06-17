"""News service — stock-specific + global/China market news.

``get_news`` resolves a ticker, queries Eastmoney's per-stock search feed
first and falls back to Sina's GBK stock-news page when Eastmoney yields
nothing or errors out, then filters items to ``[start_date, end_date]``.

``get_global_news`` merges CLS (财联社) telegraph wire with Eastmoney's 7x24
fast-news feed, deduplicates by title (case-insensitive, stripped), and
returns the first ``limit`` items.

Both return structured Pydantic models from :mod:`astock_data.models.news`.
Clients are injectable so tests stay fully offline; real defaults are
constructed lazily on first use.

This module never imports langchain / openai / anthropic / streamlit /
fastapi. It uses only ``requests`` for the inline CLS fetcher.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from astock_data.clients.eastmoney import EastmoneyClient
from astock_data.clients.sina import SinaClient
from astock_data.models.news import GlobalNewsResult, NewsItem, NewsResult
from astock_data.resolver import resolve_ticker

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

    import requests

    from astock_data.cache import SQLiteStructuredCache
    from astock_data.config import AStockSettings

__all__ = ["get_global_news", "get_news"]

# CLS telegraph-wire endpoint (the only host in this service NOT covered by
# EastmoneyClient/SinaClient). Kept here so the service is self-contained.
_CLS_TELEGRAPH_URL = "https://www.cls.cn/nodeapi/telegraphList"
_CLS_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


def _parse_date(raw: str) -> dt.date | None:
    """Parse the leading ``YYYY-MM-DD`` of an item ``time`` string.

    Returns ``None`` when the value cannot be parsed (callers keep such
    items per the contract — date filter is best-effort).
    """

    if not isinstance(raw, str):
        return None
    prefix = raw[:10]
    try:
        return dt.datetime.strptime(prefix, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _to_news_item(row: Mapping[str, object]) -> NewsItem:
    """Coerce a vendor dict row onto a :class:`NewsItem`.

    Vendor ``time`` strings are best-effort parsed into a timezone-naive
    ``datetime``; unparseable values fall back to ``None``.
    """

    time_raw = row.get("time")
    parsed_dt: dt.datetime | None = None
    if isinstance(time_raw, str) and time_raw:
        # Try a few common shapes emitted by the three vendors.
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed_dt = dt.datetime.strptime(time_raw.strip(), fmt)
                break
            except ValueError:
                continue

    return NewsItem(
        title=str(row.get("title", "") or ""),
        content=(str(row.get("content", "") or "") or None),
        time=parsed_dt,
        source=(str(row.get("source", "") or "") or None),
        url=(str(row.get("url", "") or "") or None),
    )


# ---------------------------------------------------------------------------
# get_news
# ---------------------------------------------------------------------------


def get_news(
    ticker: str,
    start_date: str,
    end_date: str,
    *,
    eastmoney: EastmoneyClient | None = None,
    sina: SinaClient | None = None,
    cache: SQLiteStructuredCache | None = None,
    settings: AStockSettings | None = None,
) -> NewsResult:
    """Fetch stock-specific news within ``[start_date, end_date]``.

    Resolution goes through the unified resolver (the safety boundary).
    Eastmoney's per-stock search feed is primary; on empty result or error
    the service transparently falls back to Sina's GBK news page.

    Items whose ``time`` parses to a date outside the window are dropped;
    items with unparseable ``time`` are kept (best-effort filter).

    Parameters
    ----------
    ticker:
        Raw user/LLM input (6-digit code, prefixed/suffixed code, or
        Chinese stock name).
    start_date, end_date:
        Inclusive window bounds, ``YYYY-MM-DD``.
    eastmoney, sina:
        Optional pre-built clients (injected in tests; lazily constructed
        otherwise).
    cache:
        Optional :class:`SQLiteStructuredCache`; when supplied the raw
        vendor payload is read-through / written-through keyed by the
        resolved ticker + ``end_date``.
    settings:
        Optional settings override forwarded to lazy client construction.
    """

    resolved = resolve_ticker(ticker)
    code = resolved.code

    start_dt = dt.datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = dt.datetime.strptime(end_date, "%Y-%m-%d").date()

    cache_kind = "news"
    cache_date = end_date

    # ---- cache read-through ------------------------------------------------
    if cache is not None:
        try:
            cached = cache.read(cache_kind, code, cache_date)
        except Exception:  # noqa: BLE001 — invalid key must not break reads
            cached = None
        if cached is not None:
            rows = cached.get("items", []) if isinstance(cached, dict) else []
            source_label = cached.get("source", "eastmoney") if isinstance(
                cached, dict
            ) else "eastmoney"
            items = _filter_by_date(
                [_to_news_item(r) for r in rows if isinstance(r, dict)],
                start_dt,
                end_dt,
            )
            return NewsResult(
                ticker=code,
                items=items,
                source=source_label,
                retrieved_at=dt.datetime.now(),
            )

    # ---- primary: Eastmoney ------------------------------------------------
    rows: list[dict] = []
    source_label = "eastmoney"
    try:
        em = eastmoney if eastmoney is not None else EastmoneyClient(settings)
        rows = em.search_news(code)
    except Exception:  # noqa: BLE001 — fallback path is the whole point
        rows = []

    # ---- fallback: Sina ----------------------------------------------------
    if not rows:
        try:
            sc = sina if sina is not None else SinaClient()
            rows = sc.news(code)
            if rows:
                source_label = "sina"
        except Exception:  # noqa: BLE001 — degraded but not fatal
            rows = []

    items = _filter_by_date(
        [_to_news_item(r) for r in rows if isinstance(r, dict)], start_dt, end_dt
    )

    # ---- cache write-through ----------------------------------------------
    if cache is not None and rows:
        try:
            cache.write(
                cache_kind,
                code,
                cache_date,
                {"items": list(rows), "source": source_label},
            )
        except Exception:  # noqa: BLE001 — caching must never break reads
            pass

    return NewsResult(
        ticker=code,
        items=items,
        source=source_label,
        retrieved_at=dt.datetime.now(),
    )


def _filter_by_date(
    items: list[NewsItem],
    start_dt: dt.date,
    end_dt: dt.date,
) -> list[NewsItem]:
    """Keep items inside ``[start_dt, end_dt]``; preserve unparseable ones.

    The ``time`` field on a :class:`NewsItem` is already a parsed
    ``datetime`` (or ``None``). ``None`` items are kept because the vendor
    omitted/failed to provide a parseable date and we must not silently
    drop them.
    """

    kept: list[NewsItem] = []
    for item in items:
        if item.time is None:
            kept.append(item)
            continue
        pub = item.time.date()
        if start_dt <= pub <= end_dt:
            kept.append(item)
    return kept


# ---------------------------------------------------------------------------
# get_global_news
# ---------------------------------------------------------------------------


def _fetch_cls_telegraph(
    limit: int,
    *,
    session: requests.Session | None,
    timeout: float = 10.0,
) -> list[dict]:
    """Inline CLS telegraph-wire fetcher.

    CLS returns ``data.roll_data`` with ``title``/``brief``/``content``/
    ``ctime`` (unix seconds). Normalized to ``{title, content, time,
    source, url}``. Raises on any transport/parse failure so the caller's
    broad ``except`` degrades gracefully.
    """

    import requests  # local import keeps the module importable without it

    sess = session if session is not None else requests.Session()
    params = {"rn": str(limit), "page": "1"}
    headers = {"User-Agent": _CLS_USER_AGENT, "Referer": "https://www.cls.cn/"}
    resp = sess.get(
        _CLS_TELEGRAPH_URL, params=params, headers=headers, timeout=timeout
    )
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    roll = data.get("roll_data", []) if isinstance(data, dict) else []
    rows: list[dict] = []
    for item in roll:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "") or item.get("brief", "")
        content = item.get("content", "") or item.get("brief", "")
        ctime = item.get("ctime", "")
        pub_time = ""
        if ctime:
            try:
                pub_time = dt.datetime.fromtimestamp(int(ctime)).strftime(
                    "%Y-%m-%d %H:%M"
                )
            except (ValueError, TypeError, OSError):
                pub_time = str(ctime)
        rows.append(
            {
                "title": str(title or ""),
                "content": str(content or ""),
                "time": pub_time,
                "source": "CLS Wire",
            }
        )
    return rows


def get_global_news(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 10,
    *,
    eastmoney: EastmoneyClient | None = None,
    cls_session: requests.Session | None = None,
    cache: SQLiteStructuredCache | None = None,
    settings: AStockSettings | None = None,
) -> GlobalNewsResult:
    """Fetch China/global market news (CLS wire + Eastmoney 7x24 feed).

    The two sources are merged, deduplicated by title (case-insensitive,
    stripped), and truncated to the first ``limit`` items.

    ``curr_date`` is accepted for API parity with the source project but
    the underlying feeds are live streams, so date-range filtering is not
    applied here (matches the reference behavior).
    """

    cache_kind = "global_news"
    cache_date = curr_date
    # Note: ``SQLiteStructuredCache`` keys by ticker+trade_date and validates
    # both, so global news (no ticker) uses a placeholder date-only key. Wrap
    # every cache touch in try/except so an invalid key never breaks reads.
    _GLOBAL_TICKER = "000000"

    if cache is not None:
        try:
            cached = cache.read(cache_kind, _GLOBAL_TICKER, cache_date)
        except Exception:  # noqa: BLE001
            cached = None
        if cached is not None:
            rows = cached.get("items", []) if isinstance(cached, dict) else []
            items = _dedupe_and_limit(
                [_to_news_item(r) for r in rows if isinstance(r, dict)], limit
            )
            return GlobalNewsResult(
                items=items,
                source="cls+eastmoney",
                retrieved_at=dt.datetime.now(),
            )

    all_rows: list[dict] = []

    # CLS wire — degrades silently on failure.
    try:
        all_rows.extend(_fetch_cls_telegraph(limit, session=cls_session))
    except Exception:  # noqa: BLE001 — one source failing must not abort
        pass

    # Eastmoney 7x24 fast-news.
    try:
        em = eastmoney if eastmoney is not None else EastmoneyClient(settings)
        all_rows.extend(em.fast_news(limit))
    except Exception:  # noqa: BLE001 — degraded but not fatal
        pass

    items = _dedupe_and_limit(
        [_to_news_item(r) for r in all_rows if isinstance(r, dict)], limit
    )

    if cache is not None and all_rows:
        try:
            cache.write(
                cache_kind,
                _GLOBAL_TICKER,
                cache_date,
                {"items": list(all_rows)},
            )
        except Exception:  # noqa: BLE001 — caching must never break reads
            pass

    return GlobalNewsResult(
        items=items,
        source="cls+eastmoney",
        retrieved_at=dt.datetime.now(),
    )


def _dedupe_and_limit(items: list[NewsItem], limit: int) -> list[NewsItem]:
    """Deduplicate by stripped, case-insensitive title; take first ``limit``."""

    seen: set[str] = set()
    unique: list[NewsItem] = []
    for item in items:
        key = (item.title or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:limit]
