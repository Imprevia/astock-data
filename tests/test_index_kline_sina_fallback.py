from __future__ import annotations

import json

import pytest

from astock_data.clients import eastmoney
from astock_data.clients.sina import SinaClient
from astock_data.services import market_data


pytestmark = pytest.mark.unit


def _sina_rows(count: int = 10) -> list[dict[str, str]]:
    return [
        {
            "day": f"2026-07-{day:02d}",
            "open": "3791.662",
            "high": "3831.659",
            "low": "3741.110",
            "close": "3796.281",
            "volume": str(70_000_000_000 + day),
        }
        for day in range(1, count + 1)
    ]


def test_index_kline_client_returns_requested_daily_bars_with_amount_payload(
    requests_mocker,
) -> None:
    # Given
    requests_mocker.get(SinaClient.INDEX_KLINE_URL, text=json.dumps(_sina_rows()))

    # When
    rows = SinaClient().index_kline("sh000001", datalen=10)

    # Then
    assert len(rows) == 10
    assert rows[0] == {
        "date": "2026-07-01",
        "open": pytest.approx(3791.662),
        "high": pytest.approx(3831.659),
        "low": pytest.approx(3741.110),
        "close": pytest.approx(3796.281),
        "volume": pytest.approx(70_000_000_001),
    }
    request = requests_mocker.request_history[-1]
    assert request.qs == {
        "datalen": ["10"],
        "ma": ["no"],
        "scale": ["240"],
        "symbol": ["sh000001"],
    }
    assert request.headers["Referer"] == "https://finance.sina.com.cn/"


def test_index_kline_uses_sina_when_eastmoney_fails(monkeypatch) -> None:
    # Given
    def fail_eastmoney(secid: str, days: int = 10) -> list[dict]:
        raise RuntimeError("push2his blocked")

    class SuccessfulSina:
        def index_kline(self, symbol: str, datalen: int = 10) -> list[dict]:
            assert symbol == "sz399001"
            assert datalen == 10
            return [
                {
                    "date": "2026-07-20",
                    "open": 100.0,
                    "high": 103.0,
                    "low": 99.0,
                    "close": 102.0,
                    "volume": 70_923_406_900.0,
                }
            ]

    class UnexpectedTdx:
        def index_bars(self, key: str, days: int = 10) -> list[dict]:
            pytest.fail("mootdx must not run after a successful Sina fallback")

    monkeypatch.setattr(eastmoney, "fetch_kline", fail_eastmoney)
    monkeypatch.setattr(market_data, "SinaClient", SuccessfulSina)
    monkeypatch.setattr(market_data, "TdxClient", UnexpectedTdx)

    # When
    result = market_data.get_index_kline("szci", 10)

    # Then
    assert len(result.bars) == 1
    assert result.bars[0].amount == pytest.approx(70_923_406_900.0)
    assert "已降级到新浪" in result.warnings[-1]


def test_index_kline_uses_mootdx_when_eastmoney_and_sina_fail(monkeypatch) -> None:
    # Given
    monkeypatch.setattr(eastmoney, "fetch_kline", lambda secid, days=10: [])

    class FailingSina:
        def index_kline(self, symbol: str, datalen: int = 10) -> list[dict]:
            raise RuntimeError("sina unavailable")

    class SuccessfulTdx:
        def index_bars(self, key: str, days: int = 10) -> list[dict]:
            return [
                {
                    "date": "2026-07-20",
                    "open": 100.0,
                    "high": 103.0,
                    "low": 99.0,
                    "close": 102.0,
                    "volume": 123.0,
                    "amount": 456.0,
                }
            ]

    monkeypatch.setattr(market_data, "SinaClient", FailingSina)
    monkeypatch.setattr(market_data, "TdxClient", SuccessfulTdx)

    # When
    result = market_data.get_index_kline("sh", 10)

    # Then
    assert result.bars[0].amount == pytest.approx(456.0)
    assert any("新浪 fallback 失败" in warning for warning in result.warnings)
    assert "已降级到 mootdx" in result.warnings[-1]


def test_index_kline_does_not_call_sina_when_eastmoney_succeeds(monkeypatch) -> None:
    # Given
    monkeypatch.setattr(
        eastmoney,
        "fetch_kline",
        lambda secid, days=10, **kwargs: [
            {
                "date": "2026-07-20",
                "open": 100.0,
                "high": 103.0,
                "low": 99.0,
                "close": 102.0,
                "volume": 123.0,
                "amount": 456.0,
            }
        ],
    )

    class UnexpectedSina:
        def __init__(self) -> None:
            pytest.fail("Sina must not run after Eastmoney succeeds")

    monkeypatch.setattr(market_data, "SinaClient", UnexpectedSina)

    # When
    result = market_data.get_index_kline("sh", 10)

    # Then
    assert result.bars[0].amount == pytest.approx(456.0)
    assert result.warnings == []
