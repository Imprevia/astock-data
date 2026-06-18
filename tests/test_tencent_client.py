"""Offline unit tests for TencentClient (qt.gtimg.cn).

All HTTP is intercepted; no live network. Marked ``unit``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from astock_data.clients.tencent import TencentClient, _market_prefix
from astock_data.errors import DataSourceError

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
        ("900001", "sh"),
        ("000001", "sz"),
        ("300750", "sz"),
        ("835185", "bj"),
        ("870007", "bj"),
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
        "turnover_pct", "pe_ttm", "mcap_yi", "float_mcap_yi", "pb",
        "limit_up", "limit_down", "pe_static",
    }
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
