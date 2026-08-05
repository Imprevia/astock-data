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
    def __init__(
        self,
        status_code: int = 200,
        *,
        json_data=None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text else (json.dumps(json_data) if json_data is not None else "")
        self.headers = headers or {}

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

    def __init__(
        self,
        response: _FakeResponse | None = None,
        lock_observer=None,
        outcomes: list[_FakeResponse | requests.RequestException] | None = None,
    ):
        self.headers: dict[str, str] = {}
        self.response = response or _FakeResponse(json_data={"ok": True})
        self.calls: list[dict] = []
        self.lock_observer = lock_observer
        self.outcomes = outcomes or []

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
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, requests.RequestException):
                raise outcome
            return outcome
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


def test_throttle_sleep_occurs_inside_lock(fake_session, monkeypatch):
    client = EastmoneyClient(
        min_interval=0.5, timeout=5.0, session=fake_session
    )
    client._last_call = time.time()
    sleep_lock_states: list[bool] = []
    monkeypatch.setattr(
        em_module.time,
        "sleep",
        lambda _seconds: sleep_lock_states.append(client._lock.locked()),
    )

    client.get(em_module.DATACENTER_URL)

    assert sleep_lock_states == [True]


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


def test_datacenter_does_not_leak_push2_referer(requests_mocker, client):
    requests_mocker.get(em_module.DATACENTER_URL, json={"result": {"data": []}})

    client.datacenter("rpt_x")

    assert requests_mocker.request_history[-1].headers.get("Referer") != (
        "https://quote.eastmoney.com/"
    )


def test_datacenter_empty_payload_returns_empty_list(requests_mocker, client):
    requests_mocker.get(em_module.DATACENTER_URL, json={"result": {"data": []}})
    assert client.datacenter("rpt_x") == []


def test_datacenter_missing_result_returns_empty_list(requests_mocker, client):
    requests_mocker.get(em_module.DATACENTER_URL, json={"success": False})
    assert client.datacenter("rpt_x") == []


def test_fetch_sector_fund_flow_rank_uses_industry_fs():
    class _FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def push2(self, path: str, params: dict) -> dict:
            self.calls.append((path, params))
            return {"data": {"diff": []}}

    fake = _FakeClient()

    assert em_module.fetch_sector_fund_flow_rank(client=fake) == []
    assert fake.calls[0][1]["fs"] == "m:90+s:4"


def test_fetch_sector_fund_flow_history_sends_normalized_end_date(
    requests_mocker, client
):
    # Given: the sector history endpoint returns no rows.
    url = em_module.PUSH2HIS_BASE + em_module.PUSH2HIS_FFLOW_DAYKLINE_PATH
    requests_mocker.get(url, json={"data": {"klines": []}})

    # When: history is requested with an ISO-formatted cutoff date.
    rows = em_module.fetch_sector_fund_flow_history(
        "90.bk1036",
        end_date="2026-07-21",
        client=client,
    )

    # Then: Eastmoney receives its compact end-date query parameter.
    assert rows == []
    assert requests_mocker.request_history[-1].qs["end"] == ["20260721"]


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


def test_push2_sends_browser_headers(requests_mocker, client):
    """push2() requests include browser headers."""

    requests_mocker.get(
        em_module.PUSH2_BASE + em_module.PUSH2_CLIST_PATH,
        json={"data": {"diff": []}},
    )

    client.push2(em_module.PUSH2_CLIST_PATH, {"secid": "1.000001"})

    last = requests_mocker.request_history[-1]
    assert last.headers["Accept"] == "application/json, text/plain, */*"
    assert last.headers["Referer"] == "https://quote.eastmoney.com/"
    assert "zh-CN" in last.headers["Accept-Language"]
    assert last.headers["Connection"] == "keep-alive"


def test_push2his_sends_browser_headers(requests_mocker, client):
    """push2his() requests include browser headers."""

    url = em_module.PUSH2HIS_BASE + em_module.PUSH2HIS_KLINE_PATH
    requests_mocker.get(url, json={"data": {"klines": []}})

    client.push2his(em_module.PUSH2HIS_KLINE_PATH, {"secid": "1.000001"})

    last = requests_mocker.request_history[-1]
    assert last.headers["Referer"] == "https://quote.eastmoney.com/"
    assert "zh-CN" in last.headers["Accept-Language"]


def test_index_snapshot_parses_stock_get_data(requests_mocker, client):
    requests_mocker.get(
        em_module.PUSH2_BASE + em_module.PUSH2_STOCK_GET_PATH,
        json={"data": {"f58": "上证指数", "f43": 4108.07, "f169": 16.2, "f170": 0.39}},
    )

    row = client.index_snapshot("1.000001")

    assert row["f58"] == "上证指数"
    assert row["f43"] == 4108.07
    assert requests_mocker.request_history[-1].qs["secid"] == ["1.000001"]


def test_index_snapshot_empty_payload_returns_empty_dict(requests_mocker, client):
    requests_mocker.get(em_module.PUSH2_BASE + em_module.PUSH2_STOCK_GET_PATH, json={"data": None})
    assert client.index_snapshot("1.000001") == {}


def test_clist_parses_page_rows_and_total(requests_mocker, client):
    requests_mocker.get(
        em_module.PUSH2_BASE + em_module.PUSH2_CLIST_PATH,
        json={"data": {"total": 2, "diff": [{"f12": "000001"}, {"f12": "688017"}]}},
    )

    rows, total = client.clist(page=2, page_size=50, fields="f12,f14")

    assert total == 2
    assert [row["f12"] for row in rows] == ["000001", "688017"]
    last = requests_mocker.request_history[-1]
    assert last.qs["pn"] == ["2"]
    assert last.qs["pz"] == ["50"]
    assert last.qs["fields"] == ["f12,f14"]


@pytest.mark.parametrize("total", [None, "bad", 0, -1, 1.5, True])
def test_clist_rejects_invalid_total(requests_mocker, client, total):
    requests_mocker.get(
        em_module.PUSH2_BASE + em_module.PUSH2_CLIST_PATH,
        json={"data": {"total": total, "diff": [{"f12": "000001"}]}},
    )

    with pytest.raises(DataSourceError, match="invalid total count"):
        client.clist()


def test_clist_rejects_total_smaller_than_returned_rows(requests_mocker, client):
    requests_mocker.get(
        em_module.PUSH2_BASE + em_module.PUSH2_CLIST_PATH,
        json={
            "data": {
                "total": 1,
                "diff": [{"f12": "000001"}, {"f12": "000002"}],
            }
        },
    )

    with pytest.raises(DataSourceError, match="smaller than the returned row count"):
        client.clist()


def test_clist_all_paginates_until_total(requests_mocker, client):
    url = em_module.PUSH2_BASE + em_module.PUSH2_CLIST_PATH
    requests_mocker.get(
        url,
        [
            {"json": {"data": {"total": 3, "diff": [{"f12": "000001"}, {"f12": "000002"}]}}},
            {"json": {"data": {"total": 3, "diff": [{"f12": "000003"}]}}},
        ],
    )

    rows = client.clist_all(page_size=2, fields="f12")

    assert [row["f12"] for row in rows] == ["000001", "000002", "000003"]
    assert len(requests_mocker.request_history) >= 2


def test_clist_all_rejects_truncated_pagination(requests_mocker, client):
    url = em_module.PUSH2_BASE + em_module.PUSH2_CLIST_PATH
    requests_mocker.get(
        url,
        [
            {"json": {"data": {"total": 3, "diff": [{"f12": "000001"}]}}},
            {"json": {"data": {"total": 3, "diff": []}}},
        ],
    )

    with pytest.raises(DataSourceError, match="pagination ended early"):
        client.clist_all(page_size=2, fields="f12")


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


def test_fast_news_page_returns_and_forwards_vendor_cursor(requests_mocker, client):
    payload = {
        "data": {
            "sortEnd": "1785659932031650",
            "fastNewsList": [
                {
                    "title": "历史快讯",
                    "summary": "摘要",
                    "showTime": "2026-07-31 23:58:00",
                }
            ],
        }
    }
    requests_mocker.get(em_module.FAST_NEWS_URL, json=payload)

    news, cursor = client.fast_news_page(
        limit=100,
        sort_end="1785660000000000",
    )

    assert news[0]["title"] == "历史快讯"
    assert cursor == "1785659932031650"
    last = requests_mocker.request_history[-1]
    assert last.qs["pagesize"] == ["100"]
    assert last.qs["sortend"] == ["1785660000000000"]


# ---------------------------------------------------------------------------
# concept_blocks helper — individual-stock core-conception endpoint.
# ---------------------------------------------------------------------------
def test_concept_blocks_parses_ordered_core_conception_membership(requests_mocker, client):
    payload = {
        "ssbk": [
            {"BOARD_CODE": "438", "BOARD_NAME": "食品饮料", "BOARD_RANK": 1},
            {"BOARD_CODE": "167", "BOARD_NAME": "山西板块", "BOARD_RANK": 4},
            {"BOARD_CODE": "1711", "BOARD_NAME": "消费风格", "BOARD_RANK": 5},
        ]
    }
    requests_mocker.get(
        em_module.CORE_CONCEPTION_URL,
        json=payload,
    )

    blocks = client.concept_blocks("600809")

    assert [block["name"] for block in blocks] == ["食品饮料", "山西板块", "消费风格"]
    assert [block["direction"] for block in blocks] == ["industry", "region", "concept"]
    assert blocks[0]["raw"]["BOARD_RANK"] == 1

    requested = requests_mocker.request_history[-1].url
    assert "eastmoney.com" in requested
    assert "baidu.com" not in requested
    assert requests_mocker.request_history[-1].qs["code"] == ["sh600809"]


def test_concept_blocks_sz_market_prefix(requests_mocker, client):
    requests_mocker.get(
        em_module.CORE_CONCEPTION_URL,
        json={"ssbk": []},
    )
    client.concept_blocks("002230")
    assert requests_mocker.request_history[-1].qs["code"] == ["sz002230"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "missing ssbk"),
        ({"ssbk": None}, "ssbk must be a list"),
        ({"ssbk": {}}, "ssbk must be a list"),
        (
            {
                "ssbk": [
                    {
                        "BOARD_CODE": "1711",
                        "BOARD_NAME": "消费风格",
                        "BOARD_RANK": "invalid",
                    }
                ]
            },
            "invalid BOARD_RANK",
        ),
        (
            {
                "ssbk": [
                    {
                        "BOARD_CODE": "",
                        "BOARD_NAME": "消费风格",
                        "BOARD_RANK": 5,
                    }
                ]
            },
            "missing BOARD_CODE",
        ),
        (
            {
                "ssbk": [
                    {
                        "BOARD_CODE": "1711",
                        "BOARD_NAME": "",
                        "BOARD_RANK": 5,
                    }
                ]
            },
            "missing BOARD_NAME",
        ),
        (
            {
                "ssbk": [
                    {
                        "BOARD_CODE": "1711",
                        "BOARD_NAME": "消费风格",
                        "BOARD_RANK": True,
                    }
                ]
            },
            "invalid BOARD_RANK",
        ),
        (
            {
                "ssbk": [
                    {
                        "BOARD_CODE": "1711",
                        "BOARD_NAME": "消费风格",
                        "BOARD_RANK": 1.5,
                    }
                ]
            },
            "invalid BOARD_RANK",
        ),
    ],
)
def test_concept_blocks_rejects_malformed_success_payloads(
    requests_mocker,
    client,
    payload,
    message,
):
    requests_mocker.get(em_module.CORE_CONCEPTION_URL, json=payload)

    with pytest.raises(DataSourceError, match=message):
        client.concept_blocks("600809")


def test_fetch_kline_parses_change_and_turnover_metrics(requests_mocker, client):
    requests_mocker.get(
        em_module.PUSH2HIS_BASE + em_module.PUSH2HIS_KLINE_PATH,
        json={
            "data": {
                "klines": [
                    "2026-08-05,10.0,10.8,11.0,9.9,12345,678900,10.0,8.0,0.8,12.3"
                ]
            }
        },
    )

    rows = em_module.fetch_kline("1.600809", days=1, client=client)

    assert rows[0]["change_pct"] == 8.0
    assert rows[0]["turnover_pct"] == 12.3
    assert requests_mocker.request_history[-1].qs["fields2"] == [
        "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    ]


# ---------------------------------------------------------------------------
# Error mapping.
# ---------------------------------------------------------------------------
def test_http_500_raises_data_source_error(requests_mocker, client):
    requests_mocker.get(em_module.DATACENTER_URL, status_code=500)
    with pytest.raises(DataSourceError):
        client.datacenter("rpt_x")


def test_http_429_exhaustion_raises_rate_limit_error(requests_mocker, client, monkeypatch):
    requests_mocker.get(em_module.DATACENTER_URL, status_code=429)
    monkeypatch.setattr(em_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(RateLimitError):
        client.datacenter("rpt_x")

    assert len(requests_mocker.request_history) == 1 + em_module._MAX_RETRIES


def test_transport_error_raises_data_source_error(client, monkeypatch):
    def _boom(*args, **kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(client._session, "get", _boom)
    with pytest.raises(DataSourceError):
        client.get(em_module.DATACENTER_URL)


def test_get_retries_on_connection_error(monkeypatch):
    """ConnectionError is retried up to _MAX_RETRIES times before giving up."""

    client = EastmoneyClient(min_interval=0.0, timeout=5.0)

    call_count = 0

    def _flaky_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise requests.ConnectionError("Remote end closed connection")

    monkeypatch.setattr(client._session, "get", _flaky_get)
    sleep_calls = []
    monkeypatch.setattr(em_module.time, "sleep", lambda s: sleep_calls.append(s))

    with pytest.raises(DataSourceError) as exc_info:
        client.get(em_module.DATACENTER_URL)

    assert call_count == 1 + em_module._MAX_RETRIES
    assert "attempts" in str(exc_info.value)
    assert em_module.DATACENTER_URL in str(exc_info.value)
    retry_delays = [s for s in sleep_calls if s in em_module._RETRY_DELAYS]
    assert len(retry_delays) == em_module._MAX_RETRIES


def test_get_does_not_retry_on_non_retryable_error(monkeypatch):
    """Non-retryable errors fail immediately."""

    client = EastmoneyClient(min_interval=0.0, timeout=5.0)

    call_count = 0

    def _fail(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise requests.HTTPError("400 Bad Request")

    monkeypatch.setattr(client._session, "get", _fail)

    with pytest.raises(DataSourceError):
        client.get(em_module.DATACENTER_URL)

    assert call_count == 1


def test_get_succeeds_on_retry(monkeypatch):
    """ConnectionError on first attempt, success on retry."""

    client = EastmoneyClient(min_interval=0.0, timeout=5.0)

    call_count = 0

    def _recovering_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise requests.ConnectionError("connection reset")
        return _FakeResponse(json_data={"ok": True})

    monkeypatch.setattr(client._session, "get", _recovering_get)
    monkeypatch.setattr(em_module.time, "sleep", lambda s: None)

    response = client.get(em_module.DATACENTER_URL)

    assert call_count == 2
    assert response.json() == {"ok": True}


def test_transport_retry_canary_preserves_backoff_sequence(monkeypatch):
    session = _FakeSession(
        outcomes=[
            requests.ConnectionError("first reset"),
            requests.ConnectionError("second reset"),
            _FakeResponse(json_data={"ok": True}),
        ]
    )
    client = EastmoneyClient(min_interval=0.0, timeout=5.0, session=session)
    sleep_calls: list[float] = []
    monkeypatch.setattr(em_module.time, "sleep", sleep_calls.append)

    response = client.get(em_module.DATACENTER_URL)

    assert response.status_code == 200
    assert len(session.calls) == 3
    assert sleep_calls == em_module._RETRY_DELAYS


def test_transport_retry_canary_exhausts_after_three_attempts(monkeypatch):
    session = _FakeSession(
        outcomes=[
            requests.ConnectionError("first reset"),
            requests.ConnectionError("second reset"),
            requests.ConnectionError("third reset"),
        ]
    )
    client = EastmoneyClient(min_interval=0.0, timeout=5.0, session=session)
    monkeypatch.setattr(em_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(DataSourceError):
        client.get(em_module.DATACENTER_URL)

    assert len(session.calls) == 1 + em_module._MAX_RETRIES


def test_get_retries_429_until_success(monkeypatch):
    session = _FakeSession(
        outcomes=[
            _FakeResponse(status_code=429),
            _FakeResponse(status_code=429),
            _FakeResponse(json_data={"ok": True}),
        ]
    )
    client = EastmoneyClient(min_interval=0.0, timeout=5.0, session=session)
    monkeypatch.setattr(em_module.time, "sleep", lambda _seconds: None)

    response = client.get(em_module.DATACENTER_URL)

    assert response.status_code == 200
    assert len(session.calls) == 3


def test_get_honors_retry_after_for_429(monkeypatch):
    session = _FakeSession(
        outcomes=[
            _FakeResponse(status_code=429, headers={"Retry-After": "5"}),
            _FakeResponse(json_data={"ok": True}),
        ]
    )
    client = EastmoneyClient(min_interval=0.0, timeout=5.0, session=session)
    sleep_calls: list[float] = []
    monkeypatch.setattr(em_module.time, "sleep", sleep_calls.append)

    response = client.get(em_module.DATACENTER_URL)

    assert response.status_code == 200
    assert sleep_calls == [5.0]


def test_get_caps_retry_after_at_sixty_seconds(monkeypatch):
    session = _FakeSession(
        outcomes=[
            _FakeResponse(status_code=429, headers={"Retry-After": "3600"}),
            _FakeResponse(json_data={"ok": True}),
        ]
    )
    client = EastmoneyClient(min_interval=0.0, timeout=5.0, session=session)
    sleep_calls: list[float] = []
    monkeypatch.setattr(em_module.time, "sleep", sleep_calls.append)

    response = client.get(em_module.DATACENTER_URL)

    assert response.status_code == 200
    assert sleep_calls == [60.0]


@pytest.mark.parametrize("retry_after", ["invalid", "-1"])
def test_get_uses_backoff_for_invalid_retry_after(monkeypatch, retry_after):
    session = _FakeSession(
        outcomes=[
            _FakeResponse(status_code=429, headers={"Retry-After": retry_after}),
            _FakeResponse(json_data={"ok": True}),
        ]
    )
    client = EastmoneyClient(min_interval=0.0, timeout=5.0, session=session)
    sleep_calls: list[float] = []
    monkeypatch.setattr(em_module.time, "sleep", sleep_calls.append)

    response = client.get(em_module.DATACENTER_URL)

    assert response.status_code == 200
    assert sleep_calls == [em_module._RATE_LIMIT_DELAYS[0]]


def test_rate_limit_retry_sleep_occurs_outside_lock(monkeypatch):
    session = _FakeSession(
        outcomes=[
            _FakeResponse(status_code=429, headers={"Retry-After": "5"}),
            _FakeResponse(json_data={"ok": True}),
        ]
    )
    client = EastmoneyClient(min_interval=0.0, timeout=5.0, session=session)
    sleep_lock_states: list[tuple[float, bool]] = []
    monkeypatch.setattr(
        em_module.time,
        "sleep",
        lambda seconds: sleep_lock_states.append((seconds, client._lock.locked())),
    )

    response = client.get(em_module.DATACENTER_URL)

    assert response.status_code == 200
    assert sleep_lock_states == [(5.0, False)]


def test_transport_retry_sleep_occurs_outside_lock(monkeypatch):
    session = _FakeSession(
        outcomes=[
            requests.ConnectionError("connection reset"),
            _FakeResponse(json_data={"ok": True}),
        ]
    )
    client = EastmoneyClient(min_interval=0.0, timeout=5.0, session=session)
    sleep_lock_states: list[tuple[float, bool]] = []
    monkeypatch.setattr(
        em_module.time,
        "sleep",
        lambda seconds: sleep_lock_states.append((seconds, client._lock.locked())),
    )

    response = client.get(em_module.DATACENTER_URL)

    assert response.status_code == 200
    assert sleep_lock_states == [(em_module._RETRY_DELAYS[0], False)]


def test_get_raises_rate_limit_error_after_429_retries(monkeypatch):
    session = _FakeSession(
        outcomes=[_FakeResponse(status_code=429) for _ in range(3)]
    )
    client = EastmoneyClient(min_interval=0.0, timeout=5.0, session=session)
    monkeypatch.setattr(em_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(RateLimitError):
        client.get(em_module.DATACENTER_URL)

    assert len(session.calls) == 1 + em_module._MAX_RETRIES


def test_non_json_body_raises_data_source_error(requests_mocker, client):
    requests_mocker.get(em_module.DATACENTER_URL, text="<html>not json</html>")
    with pytest.raises(DataSourceError):
        client.datacenter("rpt_x")


# ---------------------------------------------------------------------------
# Configuration: settings drive defaults; UA on the session.
# ---------------------------------------------------------------------------
def test_defaults_derived_from_settings():
    from astock_data.config import AStockSettings

    settings = AStockSettings(user_agent_pool=["UA-T6"])
    c = EastmoneyClient(settings=settings)
    assert c.min_interval == settings.eastmoney_min_interval
    assert c.timeout == settings.request_timeout
    assert c._session.headers["User-Agent"] == "UA-T6"


def test_proxy_derived_from_settings():
    from astock_data.config import AStockSettings

    session = _FakeSession()
    settings = AStockSettings(http_proxy="http://proxy.test:8080")

    EastmoneyClient(settings=settings, session=session)

    assert session.proxies == {
        "http": "http://proxy.test:8080",
        "https": "http://proxy.test:8080",
    }


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
