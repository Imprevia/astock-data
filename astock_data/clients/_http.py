"""Shared anti-crawler HTTP helpers for vendor clients."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Mapping
from typing import Final

import requests

from astock_data.config import AStockSettings, get_settings
from astock_data.errors import DataSourceError, RateLimitError

_DESKTOP_UA_POOL: Final[tuple[str, ...]] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
    "Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) "
    "Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/55.0.2883.75 Safari/537.36",
    "Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/28.0.1500.95 Safari/537.36",
)
_RETRY_DELAYS: Final[tuple[float, ...]] = (1.0, 2.0)
_RATE_LIMIT_DELAYS: Final[tuple[float, ...]] = (2.0, 4.0)
_DEFAULT_REFERERS: Final[dict[str, str]] = {
    "sina": "https://finance.sina.com.cn/",
    "tencent": "https://gu.qq.com/",
    "push2": "https://quote.eastmoney.com/",
    "push2his": "https://quote.eastmoney.com/",
}

_VENDOR_LOCKS: dict[str, threading.Lock] = {}
_VENDOR_LAST_CALL: dict[str, float] = {}
_registry_lock = threading.Lock()


def pick_user_agent(settings: AStockSettings | None = None) -> str:
    """Choose one configured or built-in desktop user agent."""

    cfg = settings if settings is not None else get_settings()
    pool = cfg.user_agent_pool if cfg.user_agent_pool else _DESKTOP_UA_POOL
    return random.choice(pool)


def _get_vendor_lock(vendor: str) -> threading.Lock:
    with _registry_lock:
        return _VENDOR_LOCKS.setdefault(vendor, threading.Lock())


def _is_retryable_transport_error(exc: requests.RequestException) -> bool:
    if isinstance(
        exc,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ),
    ):
        return True
    if isinstance(exc, requests.exceptions.SSLError):
        return "unexpected eof" in str(exc).lower()
    return False


def _retry_after_seconds(response: requests.Response, attempt: int) -> float:
    value = response.headers.get("Retry-After")
    try:
        return max(0.0, float(int(value))) if value is not None else _RATE_LIMIT_DELAYS[attempt]
    except ValueError:
        return _RATE_LIMIT_DELAYS[attempt]


def throttled_get(
    vendor: str,
    session: requests.Session,
    url: str,
    *,
    min_interval: float,
    timeout: float,
    params: Mapping[str, str | int | float] | None = None,
    headers: Mapping[str, str] | None = None,
    max_retries: int = 2,
) -> requests.Response:
    """Issue one vendor-throttled GET with bounded transport/rate retries."""

    with _get_vendor_lock(vendor):
        retry_delay: float | None = None
        for attempt in range(1 + max_retries):
            if attempt == 0:
                wait = min_interval - (time.time() - _VENDOR_LAST_CALL.get(vendor, 0.0))
                if wait > 0:
                    time.sleep(wait + random.uniform(0.1, 0.5))
            elif retry_delay is not None:
                time.sleep(retry_delay)

            try:
                try:
                    response = session.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=timeout,
                    )
                finally:
                    _VENDOR_LAST_CALL[vendor] = time.time()
            except requests.RequestException as exc:
                if _is_retryable_transport_error(exc) and attempt < max_retries:
                    retry_delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                    continue
                attempts = attempt + 1
                raise DataSourceError(
                    f"{vendor} request failed after {attempts} attempts: {url!r}: {exc}"
                ) from exc

            status = response.status_code
            if status in (429, 503):
                if attempt < max_retries:
                    retry_delay = _retry_after_seconds(
                        response,
                        min(attempt, len(_RATE_LIMIT_DELAYS) - 1),
                    )
                    continue
                raise RateLimitError(
                    f"{vendor} rate-limited ({status}) at {url!r}"
                )
            if status >= 400:
                raise DataSourceError(
                    f"{vendor} returned HTTP {status} at {url!r}"
                )
            return response

    raise DataSourceError(f"{vendor} request failed at {url!r}")


def build_headers(
    vendor: str,
    referer: str | None = None,
    user_agent: str | None = None,
) -> dict[str, str]:
    """Build browser-like headers for one explicitly supported vendor."""

    if vendor not in _DEFAULT_REFERERS:
        raise ValueError(f"Unknown vendor: {vendor!r}")
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "User-Agent": user_agent or pick_user_agent(),
        "Referer": referer or _DEFAULT_REFERERS[vendor],
    }


def apply_proxy(
    session: requests.Session,
    settings: AStockSettings | None = None,
) -> None:
    """Apply the configured HTTP proxy to both HTTP and HTTPS requests."""

    cfg = settings if settings is not None else get_settings()
    if cfg.http_proxy is not None:
        session.proxies = {"http": cfg.http_proxy, "https": cfg.http_proxy}


__all__ = [
    "_DESKTOP_UA_POOL",
    "apply_proxy",
    "build_headers",
    "pick_user_agent",
    "throttled_get",
]
