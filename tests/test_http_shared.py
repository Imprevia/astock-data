import json
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

from astock_data.clients import _http
from astock_data.config import AStockSettings, get_settings
from astock_data.errors import DataSourceError, RateLimitError


pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        *,
        headers: dict[str, str] | None = None,
        json_data=None,
        text: str = "",
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_data
        self.text = text if text else (
            json.dumps(json_data) if json_data is not None else ""
        )

    def json(self):
        if self._json is None:
            raise json.JSONDecodeError("no json", "", 0)
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class _FakeSession:
    """Record requests while returning or raising configured outcomes."""

    def __init__(self, *outcomes):
        self.calls: list[dict] = []
        self._outcomes = deque(outcomes or (_FakeResponse(),))
        self._last_outcome = self._outcomes[-1]

    def get(self, url, params=None, headers=None, timeout=None, **kwargs):
        self.calls.append(
            {
                "url": url,
                "params": dict(params) if params else {},
                "headers": dict(headers) if headers else {},
                "timeout": timeout,
                "ts": time.time(),
            }
        )
        outcome = (
            self._outcomes.popleft()
            if len(self._outcomes) > 1
            else self._last_outcome
        )
        if isinstance(outcome, requests.RequestException):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def _reset_vendor_throttle():
    _http._VENDOR_LAST_CALL.clear()
    yield
    _http._VENDOR_LAST_CALL.clear()


def _get(session: _FakeSession, vendor: str = "test"):
    return _http.throttled_get(
        vendor,
        session,
        "https://example.test/data",
        min_interval=0.0,
        timeout=3.0,
    )


def test_pick_user_agent_uses_multiple_built_in_desktop_values():
    selected = {_http.pick_user_agent(AStockSettings()) for _ in range(50)}

    assert selected <= set(_http._DESKTOP_UA_POOL)
    assert len(selected) > 1


def test_pick_user_agent_honors_configured_environment_pool(monkeypatch):
    monkeypatch.setenv("ASTOCK_USER_AGENT_POOL", '["UA-X"]')
    get_settings.cache_clear()

    settings = get_settings()
    assert _http.pick_user_agent(settings) == "UA-X"

    get_settings.cache_clear()


def test_throttled_get_retries_429_then_returns_success(monkeypatch):
    monkeypatch.setattr(_http.time, "sleep", lambda _seconds: None)
    success = _FakeResponse(200)
    session = _FakeSession(_FakeResponse(429), success)

    response = _get(session, "rate-once")

    assert len(session.calls) == 2
    assert response is success
    assert response.status_code == 200


def test_throttled_get_raises_rate_limit_after_three_429s(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(_http.time, "sleep", sleeps.append)
    session = _FakeSession(_FakeResponse(429))

    with pytest.raises(RateLimitError):
        _get(session, "rate-always")

    assert len(session.calls) == 3
    assert sleeps
    assert sleeps == sorted(sleeps)


def test_throttled_get_respects_retry_after_header(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(_http.time, "sleep", sleeps.append)
    session = _FakeSession(_FakeResponse(429, headers={"Retry-After": "5"}))

    with pytest.raises(RateLimitError):
        _get(session, "retry-after")

    assert 5.0 in sleeps


def test_throttled_get_treats_503_as_rate_limit(monkeypatch):
    monkeypatch.setattr(_http.time, "sleep", lambda _seconds: None)
    session = _FakeSession(_FakeResponse(503))

    with pytest.raises(RateLimitError):
        _get(session, "unavailable")

    assert len(session.calls) == 3


def test_throttled_get_returns_200_without_retry():
    expected = _FakeResponse(200)
    session = _FakeSession(expected)

    response = _get(session, "success")

    assert len(session.calls) == 1
    assert response is expected


@pytest.mark.parametrize("status_code", [404, 500])
def test_throttled_get_does_not_retry_other_http_errors(status_code):
    session = _FakeSession(_FakeResponse(status_code))

    with pytest.raises(DataSourceError) as exc_info:
        _get(session, f"http-{status_code}")

    assert len(session.calls) == 1
    assert not isinstance(exc_info.value, RateLimitError)


def test_throttled_get_retries_connection_errors_then_succeeds(monkeypatch):
    monkeypatch.setattr(_http.time, "sleep", lambda _seconds: None)
    session = _FakeSession(
        requests.ConnectionError("first"),
        requests.ConnectionError("second"),
        _FakeResponse(200),
    )

    response = _get(session, "connection-recovers")

    assert len(session.calls) == 3
    assert response.status_code == 200


def test_throttled_get_wraps_exhausted_connection_errors(monkeypatch):
    monkeypatch.setattr(_http.time, "sleep", lambda _seconds: None)
    session = _FakeSession(requests.ConnectionError("offline"))

    with pytest.raises(DataSourceError) as exc_info:
        _get(session, "connection-fails")

    assert len(session.calls) == 3
    assert not isinstance(exc_info.value, RateLimitError)


def test_throttled_get_serializes_concurrent_calls_by_vendor(monkeypatch):
    min_interval = 0.05
    monkeypatch.setattr(_http.random, "uniform", lambda _start, _end: 0.0)
    session = _FakeSession(_FakeResponse(200))

    def request_twice() -> None:
        for _ in range(2):
            _http.throttled_get(
                "sina-concurrent",
                session,
                "https://example.test/data",
                min_interval=min_interval,
                timeout=3.0,
            )

    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(lambda _index: request_twice(), range(5)))

    timestamps = [call["ts"] for call in session.calls]
    intervals = [later - earlier for earlier, later in zip(timestamps, timestamps[1:])]
    assert len(session.calls) == 10
    assert all(interval >= min_interval - 0.05 for interval in intervals)


def test_apply_proxy_sets_both_schemes_and_preserves_default_when_absent():
    proxy = "http://127.0.0.1:8080"
    with requests.Session() as configured, requests.Session() as default:
        default_proxies = dict(default.proxies)

        _http.apply_proxy(configured, AStockSettings(http_proxy=proxy))
        _http.apply_proxy(default, AStockSettings(http_proxy=None))

        assert configured.proxies == {"http": proxy, "https": proxy}
        assert default.proxies == default_proxies
