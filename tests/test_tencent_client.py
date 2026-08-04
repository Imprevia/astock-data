"""Offline unit tests for TencentClient (qt.gtimg.cn).

All HTTP is intercepted; no live network. Marked ``unit``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from astock_data.clients._http import _DESKTOP_UA_POOL
from astock_data.clients.tencent import TencentClient, _market_prefix
from astock_data.config import AStockSettings
from astock_data.errors import DataSourceError, RateLimitError

FIXTURES = Path(__file__).parent / "fixtures"


def _load_tencent_fixture() -> bytes:
    """Raw Tencent payload is GBK-encoded; serve bytes like a real response."""
    return (FIXTURES / "tencent_quote.txt").read_bytes()


def _tencent_index_line(
    symbol: str,
    name: str,
    price: str,
    last_close: str,
    change_pct: str,
) -> str:
    values = [""] * 53
    values[1] = name
    values[2] = symbol[2:]
    values[3] = price
    values[4] = last_close
    values[32] = change_pct
    return 'v_' + symbol + '="' + "~".join(values) + '";'


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# market prefix mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,expected",
    [
        ("688017", "sh"),
        ("600000", "sh"),
        ("512480", "sh"),
        ("900001", "sh"),
        ("000001", "sz"),
        ("300750", "sz"),
        ("835185", "bj"),
        ("870007", "bj"),
        ("920267", "bj"),
        ("430047", "bj"),
    ],
)
def test_market_prefix_mapping(code: str, expected: str) -> None:
    assert _market_prefix(code) == expected


# ---------------------------------------------------------------------------
# quote parsing via requests_mock
# ---------------------------------------------------------------------------


def test_quote_parses_gbk_fixture(requests_mocker) -> None:
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sh688017,sz000001",
        content=_load_tencent_fixture(),
    )

    client = TencentClient()
    result = client.quote(["688017", "000001"])

    assert set(result.keys()) == {"688017", "000001"}

    tech = result["688017"]
    # Contract field keys are all present.
    assert set(tech.keys()) == {
        "name", "price", "last_close", "open", "change_pct", "high", "low",
        "volume", "amount_wan", "turnover_pct", "pe_ttm", "mcap_yi", "float_mcap_yi", "pb",
        "limit_up", "limit_down", "pe_static",
    }
    assert "bids" not in tech
    assert "asks" not in tech
    assert "vendor_timestamp" not in tech
    # Spot-check the contract values.
    assert tech["name"] == "FAKE_TECH"
    assert tech["price"] == pytest.approx(50.00)
    assert tech["last_close"] == pytest.approx(49.00)
    assert tech["open"] == pytest.approx(49.50)
    assert tech["change_pct"] == pytest.approx(1.00)
    assert tech["high"] == pytest.approx(2.04)
    assert tech["low"] == pytest.approx(48.50)
    assert tech["turnover_pct"] == pytest.approx(3.50)
    assert tech["pe_ttm"] == pytest.approx(12.50)
    assert tech["mcap_yi"] == pytest.approx(300.0)
    assert tech["float_mcap_yi"] == pytest.approx(150.0)
    assert tech["pb"] == pytest.approx(2.50)
    assert tech["limit_up"] == pytest.approx(55.00)
    assert tech["limit_down"] == pytest.approx(45.00)
    assert tech["pe_static"] == pytest.approx(12.00)

    bank = result["000001"]
    assert bank["name"] == "FAKE_BANK"
    assert bank["price"] == pytest.approx(10.00)
    assert bank["pe_ttm"] == pytest.approx(5.00)
    assert bank["pb"] == pytest.approx(0.50)
    assert bank["limit_up"] == pytest.approx(11.00)
    assert bank["limit_down"] == pytest.approx(9.00)


def test_quote_parses_volume_and_amount_in_upstream_units(requests_mocker) -> None:
    values = [""] * 53
    values[1] = "长电科技"
    values[2] = "600584"
    values[3] = "85.78"
    values[36] = "2620385"
    values[37] = "2245466"
    payload = 'v_sh600584="' + "~".join(values) + '";'
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sh600584",
        content=payload.encode("gbk"),
    )

    result = TencentClient().quote(["600584"])

    assert result["600584"]["volume"] == pytest.approx(2620385.0)
    assert result["600584"]["amount_wan"] == pytest.approx(2245466.0)


def test_order_book_parses_five_levels_timestamp_and_lot_units(
    requests_mocker,
) -> None:
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sh688017",
        content=_load_tencent_fixture(),
    )

    result = TencentClient().order_book("688017")

    assert result["name"] == "FAKE_TECH"
    assert result["vendor_timestamp"] == "20260804101530"
    assert result["last_price"] == pytest.approx(50.0)
    assert len(result["bids"]) == 5
    assert len(result["asks"]) == 5
    assert result["bids"][0] == {
        "position": 1,
        "price": 50.0,
        "volume_lots": 100.0,
    }
    assert result["asks"][0] == {
        "position": 1,
        "price": 50.01,
        "volume_lots": 600.0,
    }
    assert result["bid_depth_lots"] == pytest.approx(1500.0)
    assert result["ask_depth_lots"] == pytest.approx(1600.0)
    assert result["spread"] == pytest.approx(0.01)
    assert result["imbalance"] == pytest.approx(-100 / 3100)


def test_order_book_ignores_zero_price_and_malformed_single_levels(
    requests_mocker,
) -> None:
    values = [""] * 53
    values[1] = "FAKE_BANK"
    values[2] = "000001"
    values[3] = "10.00"
    values[9:17] = ["0", "100", "9.99", "-1", "9.98", "bad", "9.97", "40"]
    values[19:21] = ["10.01", "50"]
    values[30] = "20260804101530"
    payload = 'v_sz000001="' + "~".join(values) + '";'
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sz000001",
        content=payload.encode("gbk"),
    )

    result = TencentClient().order_book("000001")

    assert result["bids"] == [
        {"position": 4, "price": 9.97, "volume_lots": 40.0}
    ]
    assert result["asks"] == [
        {"position": 1, "price": 10.01, "volume_lots": 50.0}
    ]


def test_order_book_rejects_truncated_quote_payload(requests_mocker) -> None:
    values = [""] * 31
    values[1] = "FAKE_BANK"
    values[2] = "000001"
    values[3] = "10.00"
    values[9:11] = ["9.99", "100"]
    values[19:21] = ["10.01", "120"]
    values[30] = "20260804101530"
    payload = 'v_sz000001="' + "~".join(values) + '";'
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sz000001",
        content=payload.encode("gbk"),
    )

    assert TencentClient().order_book("000001") == {}


def test_quote_uses_browser_headers(requests_mocker) -> None:
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sh688017",
        content=_load_tencent_fixture(),
    )

    TencentClient().quote(["688017"])

    headers = requests_mocker.request_history[0].headers
    assert headers["User-Agent"] != "Mozilla/5.0"
    assert headers["User-Agent"] in _DESKTOP_UA_POOL
    assert headers["Referer"] == "https://gu.qq.com/"


def test_index_snapshots_parse_gbk_payload(requests_mocker) -> None:
    payload = (
        _tencent_index_line("sh000001", "上证指数", "3000.00", "2990.00", "0.33")
        + _tencent_index_line("sz399001", "深证成指", "10000.00", "9900.00", "1.01")
        + _tencent_index_line("sz399006", "创业板指", "2000.00", "1980.00", "1.01")
        + _tencent_index_line("sh000688", "科创50", "900.00", "910.00", "-1.10")
        + _tencent_index_line("sh000300", "沪深300", "4000.00", "3980.00", "0.50")
        + _tencent_index_line("sh000905", "中证500", "6000.00", "6010.00", "-0.17")
    )
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688,sh000300,sh000905",
        content=payload.encode("gbk"),
    )

    result = TencentClient().index_snapshots()

    assert list(result) == ["sh", "sz", "cyb", "kc50", "hs300", "zz500"]
    assert result["sh"]["name"] == "上证指数"
    assert result["sh"]["price"] == pytest.approx(3000.0)
    assert result["sh"]["change"] == pytest.approx(10.0)
    assert result["sh"]["change_pct"] == pytest.approx(0.33)


def test_quote_url_uses_correct_prefixes(requests_mocker) -> None:
    captured = {}

    def _matcher(request, context):
        captured["url"] = request.url
        return _load_tencent_fixture()

    requests_mocker.get("https://qt.gtimg.cn/q=sh688017", content=_matcher)
    # Beijing code must map to bj prefix.
    bj_captured = {}

    def _bj_matcher(request, context):
        bj_captured["url"] = request.url
        return b""

    requests_mocker.get("https://qt.gtimg.cn/q=bj835185", content=_bj_matcher)

    client = TencentClient()
    client.quote(["688017"])
    assert "q=sh688017" in captured["url"]

    client.quote(["835185"])  # bj prefix path
    assert "q=bj835185" in bj_captured["url"]


def test_quote_empty_codes_returns_empty(requests_mocker) -> None:
    client = TencentClient()
    assert client.quote([]) == {}
    # No HTTP should have been registered; requests_mock fails closed anyway.


def test_quote_http_error_raises_datasource_error(requests_mocker) -> None:
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sh688017",
        exc=requests.ConnectionError("boom"),
    )
    client = TencentClient()
    with pytest.raises(DataSourceError):
        client.quote(["688017"])


def test_quote_retries_twice_before_rate_limit_error(
    requests_mocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://qt.gtimg.cn/q=sh688017"
    requests_mocker.get(url, status_code=503)
    monkeypatch.setattr("astock_data.clients._http.time.sleep", lambda _delay: None)

    with pytest.raises(RateLimitError):
        TencentClient().quote(["688017"])

    assert requests_mocker.call_count == 3


def test_quote_unparseable_payload_yields_empty(requests_mocker) -> None:
    # Valid GBK-decodable body but no quote lines -> empty result (no data).
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sh688017",
        content="nothing useful here".encode("gbk"),
    )
    client = TencentClient()
    result = client.quote(["688017"])
    assert result == {}


def test_quote_gbk_decode_failure_raises_datasource_error(requests_mocker) -> None:
    # Bytes illegal for GBK (0xff lead byte) must surface as a DataSourceError.
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sh688017",
        content=b"\xff\xfe\x00\x01garbage",
    )
    client = TencentClient()
    with pytest.raises(DataSourceError):
        client.quote(["688017"])


def test_index_snapshots_http_error_raises_datasource_error(requests_mocker) -> None:
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688,sh000300,sh000905",
        exc=requests.ConnectionError("boom"),
    )
    with pytest.raises(DataSourceError):
        TencentClient().index_snapshots()


def test_normalize_market_board_rows() -> None:
    rows = TencentClient.normalize_market_board_rows(
        [
            {"code": "sh600000", "name": "浦发银行", "price": "10.1", "zdf": "9.9"},
            {"symbol": "sz300001", "n": "特锐德", "p": "12.0", "pct": "20.0"},
        ]
    )

    assert rows == [
        {"code": "600000", "name": "浦发银行", "close": 10.1, "change_pct": 9.9},
        {"code": "300001", "name": "特锐德", "close": 12.0, "change_pct": 20.0},
    ]


def test_injected_session_is_used(requests_mocker) -> None:
    session = requests.Session()
    requests_mocker.get(
        "https://qt.gtimg.cn/q=sz000001",
        content=_load_tencent_fixture(),
    )
    client = TencentClient(session=session)
    assert client.session is session
    assert client.quote(["000001"])["000001"]["price"] == pytest.approx(10.00)


def test_session_uses_configured_proxy() -> None:
    settings = AStockSettings(http_proxy="http://127.0.0.1:7890")

    session = TencentClient(settings=settings).session

    assert session.proxies == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }
