"""Thread-safe Eastmoney HTTP client.

All ``eastmoney.com`` requests in this package MUST go through
:class:`EastmoneyClient`. It guarantees:

* a single shared :class:`requests.Session` (Keep-Alive, default UA);
* a module-wide minimum interval between calls (anti-ban throttle);
* ``0.1``–``0.5`` second random jitter on top of the throttle;
* a :class:`threading.Lock` guarding the *entire* ``sleep → call →
  timestamp-update`` sequence so concurrent callers are strictly
  serialized (the source project's ``_em_get`` had no lock and raced on
  the shared timestamp under multi-agent batch loads).

Helper methods return model-agnostic ``dict`` / ``list[dict]`` payloads;
service layers map them onto public Pydantic models later.
"""

from __future__ import annotations

import json
import random
import threading
import time
from collections.abc import Mapping
from typing import Any

import requests

from astock_data.config import AStockSettings, get_settings
from astock_data.errors import DataSourceError, RateLimitError

# ---------------------------------------------------------------------------
# Eastmoney URL constants (the ONLY place these hosts are hard-coded).
# ---------------------------------------------------------------------------
# Rationale: eastmoney operates 5 distinct hosts with distinct param shapes.
# Centralizing them means later services never hardcode URLs.

DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
PUSH2_BASE = "https://push2.eastmoney.com"
PUSH2HIS_BASE = "https://push2his.eastmoney.com"
SEARCH_NEWS_URL = "https://search-api-web.eastmoney.com/search/jsonp"
FAST_NEWS_URL = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"

# Endpoint paths under the push2 / push2his hosts.
PUSH2_FFLOW_KLINE_PATH = "/api/qt/stock/fflow/kline/get"
PUSH2_STOCK_GET_PATH = "/api/qt/stock/get"
PUSH2_CLIST_PATH = "/api/qt/clist/get"
PUSH2_SLIST_PATH = "/api/qt/slist/get"
PUSH2HIS_FFLOW_DAYKLINE_PATH = "/api/qt/stock/fflow/daykline/get"

# Endpoints that originate from search / news surfaces keep their own Referer.
_SEARCH_NEWS_REFERER = "https://so.eastmoney.com/"
_FAST_NEWS_REFERER = "https://kuaixun.eastmoney.com/"


class EastmoneyClient:
    """Rate-limited, thread-safe HTTP client for eastmoney.com endpoints."""

    def __init__(
        self,
        settings: AStockSettings | None = None,
        *,
        min_interval: float | None = None,
        timeout: float | None = None,
        session: requests.Session | None = None,
    ) -> None:
        cfg = settings if settings is not None else get_settings()
        # Explicit constructor args override settings to ease testing.
        self.min_interval: float = (
            min_interval if min_interval is not None else cfg.eastmoney_min_interval
        )
        self.timeout: float = timeout if timeout is not None else cfg.request_timeout
        self.default_headers: dict[str, str] = {"User-Agent": cfg.user_agent}
        self._session: requests.Session = session or requests.Session()
        # Ensure session always carries the default UA even when injected.
        self._session.headers.update(self.default_headers)
        # Single lock serializes sleep+call+timestamp-update across threads.
        self._lock = threading.Lock()
        self._last_call: float = 0.0

    # ------------------------------------------------------------------
    # Core throttled GET — every eastmoney request funnels through here.
    # ------------------------------------------------------------------
    def get(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Perform a throttled, thread-safe ``session.get``.

        Acquires the lock, sleeps ``min_interval - elapsed`` (plus
        ``0.1``–``0.5``s jitter) when the elapsed time since the last call
        is below ``min_interval``, then issues the request and updates the
        shared timestamp in a ``finally`` block so the throttle window is
        always respected even on failure.
        """

        # The whole throttle window MUST be inside the lock, otherwise two
        # threads could both read the same stale ``_last_call`` and fire
        # back-to-back requests before either updates the timestamp — that
        # race is exactly the flaw being fixed from the source ``_em_get``.
        with self._lock:
            wait = self.min_interval - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait + random.uniform(0.1, 0.5))
            try:
                response = self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                    **kwargs,
                )
            except requests.RequestException as exc:
                # Transport-level failure (DNS, connection, timeout).
                raise DataSourceError(
                    f"Eastmoney request failed: {url!r}: {exc}"
                ) from exc
            finally:
                self._last_call = time.time()

        self._raise_for_status(response, url)
        return response

    @staticmethod
    def _raise_for_status(response: requests.Response, url: str) -> None:
        """Map non-2xx responses onto the typed error taxonomy."""

        status = response.status_code
        if status < 400:
            return
        if status in (429, 503):
            raise RateLimitError(
                f"Eastmoney rate-limited ({status}) at {url!r}"
            )
        raise DataSourceError(
            f"Eastmoney returned HTTP {status} at {url!r}"
        )

    # ------------------------------------------------------------------
    # Internal JSON helper.
    # ------------------------------------------------------------------
    def _get_json(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        response = self.get(url, params=params, headers=headers, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise DataSourceError(
                f"Eastmoney returned non-JSON body at {url!r}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Helper: datacenter (龙虎榜 / 解禁 / etc.)
    # ------------------------------------------------------------------
    def datacenter(
        self,
        report_name: str,
        columns: str = "ALL",
        filter_str: str = "",
        page_size: int = 50,
        sort_columns: str = "",
        sort_types: str = "-1",
    ) -> list[dict]:
        """Query the Eastmoney datacenter ``reportName`` endpoint.

        Returns the rows under ``result.data`` (an empty list when the
        upstream payload is empty/missing).
        """

        params = {
            "reportName": report_name,
            "columns": columns,
            "filter": filter_str,
            "pageNumber": "1",
            "pageSize": str(page_size),
            "sortColumns": sort_columns,
            "sortTypes": sort_types,
            "source": "WEB",
            "client": "WEB",
        }
        payload = self._get_json(DATACENTER_URL, params=params)
        result = payload.get("result") if isinstance(payload, Mapping) else None
        if not isinstance(result, Mapping):
            return []
        data = result.get("data")
        if not isinstance(data, list):
            return []
        return [row for row in data if isinstance(row, dict)]

    # ------------------------------------------------------------------
    # Helpers: push2 realtime (quote / fflow kline)
    # ------------------------------------------------------------------
    def push2(self, path: str, params: Mapping[str, Any]) -> dict:
        """Call a ``push2.eastmoney.com`` path and return its parsed JSON."""

        url = f"{PUSH2_BASE}{path}"
        payload = self._get_json(url, params=params)
        if not isinstance(payload, Mapping):
            raise DataSourceError(
                f"push2 endpoint returned non-object JSON at {url!r}"
            )
        return dict(payload)

    def push2his(self, path: str, params: Mapping[str, Any]) -> dict:
        """Call a ``push2his.eastmoney.com`` path and return parsed JSON."""

        url = f"{PUSH2HIS_BASE}{path}"
        payload = self._get_json(url, params=params)
        if not isinstance(payload, Mapping):
            raise DataSourceError(
                f"push2his endpoint returned non-object JSON at {url!r}"
            )
        return dict(payload)

    # ------------------------------------------------------------------
    # Helper: per-stock news search (search-api)
    # ------------------------------------------------------------------
    def search_news(self, code: str, page_size: int = 20) -> list[dict]:
        """Search individual-stock news via the Eastmoney search API.

        The endpoint is JSONP-wrapped; this method strips the ``cb(...)``
        wrapper and returns normalized article dicts.
        """

        inner_param = {
            "uid": "",
            "keyword": code,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": page_size,
                    "preTag": "",
                    "postTag": "",
                }
            },
        }
        params = {
            "cb": "callback",
            "param": json.dumps(inner_param, ensure_ascii=False),
            "_": "1",
        }
        headers = {"Referer": _SEARCH_NEWS_REFERER}

        response = self.get(SEARCH_NEWS_URL, params=params, headers=headers)
        text = response.text
        try:
            inner = text[text.index("(") + 1 : text.rindex(")")]
            data = json.loads(inner)
        except (ValueError, json.JSONDecodeError) as exc:
            raise DataSourceError(
                f"Eastmoney search-news returned malformed JSONP: {exc}"
            ) from exc

        result = data.get("result") if isinstance(data, Mapping) else None
        items = (
            result.get("cmsArticleWebOld", [])
            if isinstance(result, Mapping)
            else []
        )
        articles: list[dict] = []
        if not isinstance(items, list):
            return articles
        for item in items:
            if not isinstance(item, dict):
                continue
            articles.append(
                {
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "time": item.get("date", ""),
                    "source": item.get("mediaName", "东方财富"),
                    "url": item.get("url", ""),
                }
            )
        return articles

    # ------------------------------------------------------------------
    # Helper: 7x24 global fast news (np-weblist)
    # ------------------------------------------------------------------
    def fast_news(self, limit: int = 20) -> list[dict]:
        """Fetch the Eastmoney 7x24 fast-news feed (np-weblist)."""

        params = {
            "client": "web",
            "biz": "web_724",
            "fastColumn": "102",
            "sortEnd": "",
            "pageSize": str(limit),
            "req_trace": str(time.time_ns()),
        }
        headers = {"Referer": _FAST_NEWS_REFERER}
        payload = self._get_json(FAST_NEWS_URL, params=params, headers=headers)
        container = payload.get("data") if isinstance(payload, Mapping) else None
        items = (
            container.get("fastNewsList", [])
            if isinstance(container, Mapping)
            else []
        )
        news: list[dict] = []
        if not isinstance(items, list):
            return news
        for item in items:
            if not isinstance(item, dict):
                continue
            summary = item.get("summary", "") or ""
            news.append(
                {
                    "title": item.get("title", ""),
                    "content": summary[:200],
                    "time": item.get("showTime", ""),
                    "source": "Eastmoney Global",
                }
            )
        return news

    # ------------------------------------------------------------------
    # Helper: concept/sector blocks for a stock (slist, migrated from Baidu PAE)
    # ------------------------------------------------------------------
    def concept_blocks(self, code: str) -> list[dict]:
        """Return the concept/sector blocks a stock belongs to.

        Migrated from the now-offline Baidu concept endpoint to the
        Eastmoney ``push2`` ``slist`` endpoint. The caller
        (``code``) is the bare 6-digit ticker; the market prefix is
        derived per A-share conventions.
        """

        market = "1" if str(code).startswith("6") else "0"
        secid = f"{market}.{code}"
        params = {
            "spt": 3,
            "fltt": 2,
            "invt": 2,
            "secid": secid,
            "fields": "f12,f14,f3,f6,f128",
            # slist returns the block membership list for the given secid.
        }
        url = f"{PUSH2_BASE}{PUSH2_SLIST_PATH}"
        payload = self._get_json(url, params=params)
        data = payload.get("data") if isinstance(payload, Mapping) else None
        diff = data.get("diff") if isinstance(data, Mapping) else None
        if not isinstance(diff, list):
            return []
        blocks: list[dict] = []
        for item in diff:
            if not isinstance(item, dict):
                continue
            blocks.append(
                {
                    "code": item.get("f12", ""),
                    "name": item.get("f14", ""),
                    "change_pct": item.get("f3"),
                    "amount": item.get("f6"),
                    "direction": item.get("f128", ""),
                }
            )
        return blocks


__all__ = [
    "DATACENTER_URL",
    "FAST_NEWS_URL",
    "PUSH2HIS_FFLOW_DAYKLINE_PATH",
    "PUSH2_CLIST_PATH",
    "PUSH2_FFLOW_KLINE_PATH",
    "PUSH2_SLIST_PATH",
    "PUSH2_STOCK_GET_PATH",
    "SEARCH_NEWS_URL",
    "EastmoneyClient",
]
