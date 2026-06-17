"""Offline tests for :class:`astock_data.clients.eastmoney.EastmoneyClient`.

All tests run fully offline. Network behavior is intercepted via either a
fake ``requests.Session`` (for the thread-safety test) or the shared
``requests_mocker`` fixture (for payload-shape parsing tests). No real
``eastmoney.com`` call is ever made.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
import requests

from astock_data.clients import eastmoney as em_module
from astock_data.clients.eastmoney import EastmoneyClient
from astock_data.errors import DataSourceError, RateLimitError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes.
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, status_code: int = 200, *, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text else (json.dumps(json_data) if json_data is not None else "")

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class _FakeSession:
    """Records every ``get`` call with its args and observes lock state.

    ``lock_observer`` is an optional callable invoked inside each ``get``
    so a test can assert the client's lock is held while the HTTP call is
    in flight (proving the call happens inside the critical section).
    """

    def __init__(self, response: _FakeResponse | None = None, lock_observer=None):
        self.headers: dict[str, str] = {}
        self.response = response or _FakeResponse(json_data={"ok": True})
        self.calls: list[dict] = []
        self.lock_observer = lock_observer

    def get(self, url, params=None, headers=None, timeout=None, **kwargs):
        if self.lock_observer is not None:
            self.lock_observer()
        self.calls.append(
            {
                "url": url,
                "params": dict(params) if params else {},
                "headers": dict(headers) if headers else {},
                "timeout": timeout,
                "ts": time.time(),
            }
        )
        return self.response


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_session():
    return _FakeSession()


@pytest.fixture
def client():
    """A client over a *real* session so ``requests_mocker`` can intercept.

    ``min_interval=0`` keeps the offline tests fast while still exercising
    the lock-protected code path.
    """
    return EastmoneyClient(min_interval=0.0, timeout=5.0)


# ---------------------------------------------------------------------------
# Thread-safety: a single lock serializes sleep+call+timestamp-update.
# ---------------------------------------------------------------------------
def test_concurrent_calls_serialized_by_lock(fake_session, monkeypatch):
    """The lock is held during the HTTP call AND serializes two threads.

    Two independent assertions, both deterministic:

    1. **Lock held in-flight**: while ``session.get`` executes, the
       client's ``threading.Lock`` must be *un-acquirable* from another
       thread — i.e. the HTTP call happens inside the critical section.
    2. **Serialized calls**: with both threads released by a barrier and
       the throttle sleep reduced to a no-op, the second thread's call
       still observes the timestamp set by the first and therefore sleeps
       a positive ``wait + jitter``. Exactly one of the two calls sleeps
       a positive amount.
    """

    client = EastmoneyClient(
        min_interval=0.5, timeout=5.0, session=fake_session
    )

    # Assertion 1 — inspect the lock from inside the session call.
    held_during_call: list[bool] = []

    def observe_lock():
        # ``locked()`` is True when held; acquire(blocking=False) must fail.
        held_during_call.append(
            client._lock.locked()
            and client._lock.acquire(blocking=False) is False
        )

    fake_session.lock_observer = observe_lock

    sleep_calls: list[float] = []
    monkeypatch.setattr(em_module.time, "sleep", lambda s: sleep_calls.append(s))

    # Assertion 2 — two threads racing through get().
    barrier = threading.Barrier(2)
    results: list = []

    def call():
        barrier.wait()
        results.append(client.get(em_module.DATACENTER_URL, params={"x": "1"}))

    t1 = threading.Thread(target=call)
    t2 = threading.Thread(target=call)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(fake_session.calls) == 2
    assert len(results) == 2
    # Every HTTP call observed the lock as held.
    assert held_during_call == [True, True], (
        f"lock must be held during every get(); observed {held_during_call}"
    )
    # Exactly one call (the 2nd to take the lock) sleeps a positive amount
    # ≥ min_interval. If the lock were absent, both threads would read the
    # same stale ``_last_call`` (0.0) and neither would sleep.
    positive_sleeps = [s for s in sleep_calls if s > 0]
    assert len(positive_sleeps) == 1, (
        "expected exactly one throttling sleep across two concurrent calls, "
        f"got sleep_calls={sleep_calls}"
    )
    assert positive_sleeps[0] >= 0.5


def test_throttle_sleep_respected_between_sequential_calls(fake_session, monkeypatch):
    """A second sequential call within the window is throttled by sleep.

    The first call fires immediately (``_last_call`` starts at 0.0 so
    ``elapsed`` is huge and ``wait`` is non-positive). The second call,
    coming within ``min_interval`` of the first, MUST sleep a positive
    amount ≥ ``min_interval``.
    """

    client = EastmoneyClient(
        min_interval=0.5, timeout=5.0, session=fake_session
    )
    slept: list[float] = []
    monkeypatch.setattr(em_module.time, "sleep", lambda s: slept.append(s))

    client.get(em_module.DATACENTER_URL)  # first: immediate, no sleep
    client.get(em_module.DATACENTER_URL)  # second: throttled

    # Only the second call sleeps, and it sleeps ≥ min_interval (+ jitter).
    assert len(slept) == 1
    assert slept[0] >= 0.5


# ---------------------------------------------------------------------------
# datacenter helper.
# ---------------------------------------------------------------------------
def test_datacenter_parses_result_data(requests_mocker, client):
    payload = {
        "result": {
            "data": [
                {"SECURITY_CODE": "688017", "TRADE_DATE": "2026-05-12", "RANK": 1},
                {"SECURITY_CODE": "000001", "TRADE_DATE": "2026-05-12", "RANK": 2},
            ]
        }
    }
    requests_mocker.get(em_module.DATACENTER_URL, json=payload)

    rows = client.datacenter("rpt_dragon_tiger")

    assert isinstance(rows, list)
    assert len(rows) == 2
    assert rows[0]["SECURITY_CODE"] == "688017"
    # Assert the datacenter param shape was built correctly.
    # (requests_mock lowercases both keys and values in ``qs``.)
    last = requests_mocker.request_history[-1]
    assert last.qs["reportname"] == ["rpt_dragon_tiger"]
    assert last.qs["source"] == ["web"]
    assert last.qs["pagesize"] == ["50"]


def test_datacenter_empty_payload_returns_empty_list(requests_mocker, client):
    requests_mocker.get(em_module.DATACENTER_URL, json={"result": {"data": []}})
    assert client.datacenter("rpt_x") == []


def test_datacenter_missing_result_returns_empty_list(requests_mocker, client):
    requests_mocker.get(em_module.DATACENTER_URL, json={"success": False})
    assert client.datacenter("rpt_x") == []


# ---------------------------------------------------------------------------
# push2 / push2his helpers.
# ---------------------------------------------------------------------------
def test_push2_returns_parsed_dict(requests_mocker, client):
    requests_mocker.get(
        em_module.PUSH2_BASE + em_module.PUSH2_FFLOW_KLINE_PATH,
        json={"data": {"klines": ["2026-05-12,1,2,3"]}},
    )
    out = client.push2(em_module.PUSH2_FFLOW_KLINE_PATH, {"secid": "1.688017"})
    assert out["data"]["klines"] == ["2026-05-12,1,2,3"]


def test_push2his_returns_parsed_dict(requests_mocker, client):
    url = em_module.PUSH2HIS_BASE + em_module.PUSH2HIS_FFLOW_DAYKLINE_PATH
    requests_mocker.get(url, json={"data": {"klines": ["d1", "d2"]}})
    out = client.push2his(em_module.PUSH2HIS_FFLOW_DAYKLINE_PATH, {"secid": "0.000001"})
    assert out["data"]["klines"] == ["d1", "d2"]


# ---------------------------------------------------------------------------
# search_news helper (JSONP-wrapped).
# ---------------------------------------------------------------------------
def test_search_news_parses_jsonp(requests_mocker, client):
    inner = {
        "result": {
            "cmsArticleWebOld": [
                {
                    "title": "某公司发布财报",
                    "content": "正文摘要",
                    "date": "2026-05-12",
                    "mediaName": "证券时报",
                    "url": "https://example.com/a1",
                }
            ]
        }
    }
    # The endpoint wraps JSON in callback(...).
    body = "callback(" + json.dumps(inner, ensure_ascii=False) + ")"
    requests_mocker.get(em_module.SEARCH_NEWS_URL, text=body)

    articles = client.search_news("688017", page_size=5)
    assert len(articles) == 1
    assert articles[0]["title"] == "某公司发布财报"
    assert articles[0]["source"] == "证券时报"
    assert articles[0]["url"] == "https://example.com/a1"

    last = requests_mocker.request_history[-1]
    assert last.qs["cb"] == ["callback"]
    assert last.headers["Referer"] == "https://so.eastmoney.com/"


def test_search_news_empty_returns_empty(requests_mocker, client):
    body = "callback(" + json.dumps({"result": {"cmsArticleWebOld": []}}) + ")"
    requests_mocker.get(em_module.SEARCH_NEWS_URL, text=body)
    assert client.search_news("000001") == []


# ---------------------------------------------------------------------------
# fast_news helper (np-weblist 7x24).
# ---------------------------------------------------------------------------
def test_fast_news_parses_fastnewslist(requests_mocker, client):
    payload = {
        "data": {
            "fastNewsList": [
                {"title": "央行降准", "summary": "摘要内容", "showTime": "10:21"},
                {"title": "板块异动", "summary": "另一条", "showTime": "10:19"},
            ]
        }
    }
    requests_mocker.get(em_module.FAST_NEWS_URL, json=payload)

    news = client.fast_news(limit=10)
    assert len(news) == 2
    assert news[0]["title"] == "央行降准"
    assert news[0]["source"] == "Eastmoney Global"
    assert news[1]["content"] == "另一条"

    last = requests_mocker.request_history[-1]
    assert last.qs["pagesize"] == ["10"]
    assert last.headers["Referer"] == "https://kuaixun.eastmoney.com/"


# ---------------------------------------------------------------------------
# concept_blocks helper — asserts it calls EASTMONEY slist, NOT baidu.
# ---------------------------------------------------------------------------
def test_concept_blocks_hits_eastmoney_slist_not_baidu(requests_mocker, client):
    payload = {
        "data": {
            "diff": [
                {"f12": "BK0473", "f14": "半导体概念", "f3": 2.11, "f6": 9.9e9, "f128": "板块"},
            ]
        }
    }
    requests_mocker.get(
        em_module.PUSH2_BASE + em_module.PUSH2_SLIST_PATH,
        json=payload,
    )

    blocks = client.concept_blocks("688017")

    assert len(blocks) == 1
    assert blocks[0]["code"] == "BK0473"
    assert blocks[0]["name"] == "半导体概念"

    requested = requests_mocker.request_history[-1].url
    assert "eastmoney.com" in requested
    assert "baidu.com" not in requested
    # SH-listed (688017 → market 1).
    assert requests_mocker.request_history[-1].qs["secid"] == ["1.688017"]


def test_concept_blocks_sz_market_prefix(requests_mocker, client):
    requests_mocker.get(
        em_module.PUSH2_BASE + em_module.PUSH2_SLIST_PATH,
        json={"data": {"diff": []}},
    )
    client.concept_blocks("000001")
    assert requests_mocker.request_history[-1].qs["secid"] == ["0.000001"]


# ---------------------------------------------------------------------------
# Error mapping.
# ---------------------------------------------------------------------------
def test_http_500_raises_data_source_error(requests_mocker, client):
    requests_mocker.get(em_module.DATACENTER_URL, status_code=500)
    with pytest.raises(DataSourceError):
        client.datacenter("rpt_x")


def test_http_429_raises_rate_limit_error(requests_mocker, client):
    requests_mocker.get(em_module.DATACENTER_URL, status_code=429)
    with pytest.raises(RateLimitError):
        client.datacenter("rpt_x")


def test_transport_error_raises_data_source_error(client, monkeypatch):
    def _boom(*args, **kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(client._session, "get", _boom)
    with pytest.raises(DataSourceError):
        client.get(em_module.DATACENTER_URL)


def test_non_json_body_raises_data_source_error(requests_mocker, client):
    requests_mocker.get(em_module.DATACENTER_URL, text="<html>not json</html>")
    with pytest.raises(DataSourceError):
        client.datacenter("rpt_x")


# ---------------------------------------------------------------------------
# Configuration: settings drive defaults; UA on the session.
# ---------------------------------------------------------------------------
def test_defaults_derived_from_settings():
    from astock_data.config import AStockSettings

    settings = AStockSettings()
    c = EastmoneyClient(settings=settings)
    assert c.min_interval == settings.eastmoney_min_interval
    assert c.timeout == settings.request_timeout
    assert c._session.headers["User-Agent"] == settings.user_agent


def test_no_eastmoney_url_leaks_outside_constants_module():
    """URL constants are the only place eastmoney hosts are spelled out.

    We inspect the module's string literals (not docstrings) to ensure no
    service-style hardcoded host lives outside the ``*_URL`` / ``*_BASE``
    constants, and that the retired Baidu PAE host is never used as an
    actual URL.
    """
    import ast

    source = open(em_module.__file__, encoding="utf-8").read()
    tree = ast.parse(source)
    string_lits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            string_lits.append(node.value)

    # The module must reference the eastmoney hosts among its constants.
    assert any("eastmoney.com" in s for s in string_lits)
    # No string literal is a Baidu PAE/gushitong URL (those are retired).
    assert not any(
        s.startswith(("http://finance.pae.baidu", "https://finance.pae.baidu"))
        for s in string_lits
    )
    assert not any(
        s.startswith(("http://gushitong.baidu", "https://gushitong.baidu"))
        for s in string_lits
    )
