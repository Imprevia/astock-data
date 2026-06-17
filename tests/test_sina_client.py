"""Offline unit tests for SinaClient (K-line, financials, news).

All HTTP is intercepted; no live network. Marked ``unit``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from astock_data.clients.sina import SinaClient
from astock_data.errors import DataSourceError

FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.unit


def _kline_payload() -> str:
    return (FIXTURES / "sina_kline.json").read_text(encoding="utf-8")


def _financial_payload(report_type: str) -> str:
    name = {
        "balance": "sina_financial_balance.json",
        "income": "sina_financial_income.json",
        "cashflow": "sina_financial_cashflow.json",
    }[report_type]
    return (FIXTURES / name).read_text(encoding="utf-8")


def _news_bytes() -> bytes:
    return (FIXTURES / "sina_news.html").read_bytes()


# ---------------------------------------------------------------------------
# kline
# ---------------------------------------------------------------------------


def test_kline_parses_ordered_ohlcv(requests_mocker) -> None:
    requests_mocker.get(SinaClient.KLINE_URL, text=_kline_payload())

    client = SinaClient()
    rows = client.kline("688017")

    assert len(rows) == 3
    # Ascending date order preserved.
    assert [r["date"] for r in rows] == [
        "2026-06-15", "2026-06-16", "2026-06-17",
    ]
    first = rows[0]
    assert set(first.keys()) == {"date", "open", "high", "low", "close", "volume"}
    assert first["open"] == pytest.approx(10.00)
    assert first["high"] == pytest.approx(10.10)
    assert first["low"] == pytest.approx(9.90)
    assert first["close"] == pytest.approx(10.05)
    assert first["volume"] == 1000


def test_kline_date_filter(requests_mocker) -> None:
    requests_mocker.get(SinaClient.KLINE_URL, text=_kline_payload())

    client = SinaClient()
    rows = client.kline("688017", start_date="2026-06-16", end_date="2026-06-16")
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-06-16"


@pytest.mark.parametrize(
    "period,scale",
    [
        ("5min", "5"),
        ("15min", "15"),
        ("30min", "30"),
        ("60min", "60"),
        ("day", "240"),
        ("week", "1680"),
        ("month", "7200"),
    ],
)
def test_kline_period_maps_to_scale(requests_mocker, period, scale) -> None:
    captured = {}

    def _matcher(request, context):
        captured["qs"] = request.qs
        return _kline_payload()

    requests_mocker.get(SinaClient.KLINE_URL, json=_matcher)
    SinaClient().kline("688017", period=period)

    assert captured["qs"]["scale"] == [scale]


def test_kline_invalid_period_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unsupported Sina K-line period"):
        SinaClient().kline("688017", period="1min")


def test_kline_http_error_raises(requests_mocker) -> None:
    requests_mocker.get(
        SinaClient.KLINE_URL, exc=requests.ConnectionError("boom")
    )
    with pytest.raises(DataSourceError):
        SinaClient().kline("688017")


def test_kline_json_error_raises(requests_mocker) -> None:
    requests_mocker.get(SinaClient.KLINE_URL, text="not json")
    with pytest.raises(DataSourceError):
        SinaClient().kline("688017")


# ---------------------------------------------------------------------------
# financial_report
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("report_type,source", [
    ("balance", "fzb"),
    ("income", "lrb"),
    ("cashflow", "llb"),
])
def test_financial_report_parses_rows(requests_mocker, report_type, source) -> None:
    requests_mocker.get(
        SinaClient.FINANCE_URL, text=_financial_payload(report_type)
    )

    client = SinaClient()
    rows = client.financial_report("688017", report_type)

    assert len(rows) == 2
    # Each row has report_date + raw Chinese fields dict.
    assert "report_date" in rows[0]
    assert "fields" in rows[0]
    assert rows[0]["report_date"] == "2025-12-31"
    assert isinstance(rows[0]["fields"], dict)
    # Raw Chinese field names preserved verbatim.
    assert "报告日" in rows[0]["fields"]


def test_financial_report_unknown_type_raises(requests_mocker) -> None:
    with pytest.raises(DataSourceError):
        SinaClient().financial_report("688017", "bogus")


def test_financial_report_http_error_raises(requests_mocker) -> None:
    requests_mocker.get(
        SinaClient.FINANCE_URL, exc=requests.ConnectionError("boom")
    )
    with pytest.raises(DataSourceError):
        SinaClient().financial_report("688017", "balance")


def test_financial_report_url_params(requests_mocker) -> None:
    captured = {}

    def _matcher(request, context):
        captured["qs"] = request.qs
        return _financial_payload("income")

    requests_mocker.get(SinaClient.FINANCE_URL, json=_matcher)
    SinaClient().financial_report("688017", "income")
    # paperCode must carry the sh prefix for a 6-leading code.
    assert captured["qs"]["papercode"] == ["sh688017"]
    assert captured["qs"]["source"] == ["lrb"]


# ---------------------------------------------------------------------------
# news
# ---------------------------------------------------------------------------


def test_news_parses_items(requests_mocker) -> None:
    requests_mocker.get(SinaClient.NEWS_URL, content=_news_bytes())

    client = SinaClient()
    items = client.news("688017")

    assert len(items) == 2
    item = items[0]
    assert set(item.keys()) == {"title", "content", "time", "source", "url"}
    assert item["source"] == "新浪财经"
    assert item["content"] == ""
    assert item["url"].startswith("https://finance.sina.com.cn/")
    assert item["time"] == "2026-06-17 10:30"
    # Title is GBK-decoded Chinese (non-empty).
    assert item["title"]


def test_news_page_size_limit(requests_mocker) -> None:
    requests_mocker.get(SinaClient.NEWS_URL, content=_news_bytes())
    items = SinaClient().news("688017", page_size=1)
    assert len(items) == 1


def test_news_http_error_raises(requests_mocker) -> None:
    requests_mocker.get(
        SinaClient.NEWS_URL, exc=requests.ConnectionError("boom")
    )
    with pytest.raises(DataSourceError):
        SinaClient().news("688017")


def test_injected_session_is_used(requests_mocker) -> None:
    session = requests.Session()
    requests_mocker.get(SinaClient.KLINE_URL, text=_kline_payload())
    client = SinaClient(session=session)
    assert client.session is session
    assert client.kline("688017")
