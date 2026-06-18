from __future__ import annotations

import datetime as dt

import pytest

from astock_data.errors import MarketValidationError
from astock_data.models import OHLCVBar, StockDataResult, Ticker
from astock_data.services.market_breadth import get_market_breadth

pytestmark = pytest.mark.unit


class FakeEastmoney:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.index_calls: list[str] = []

    def index_snapshot(self, secid: str) -> dict:
        self.index_calls.append(secid)
        names = {
            "1.000001": "上证指数",
            "0.399001": "深证成指",
            "0.399006": "创业板指",
            "1.000688": "科创50",
            "1.000300": "沪深300",
            "1.000905": "中证500",
        }
        return {"f58": names[secid], "f43": 1000.0, "f169": 1.0, "f170": 0.1}

    def clist_all(self, *, fields: str = "") -> list[dict]:
        self.fields = fields
        return self.rows


def _bars(code: str, closes: list[float], start: str = "2026-06-15") -> StockDataResult:
    start_date = dt.date.fromisoformat(start)
    return StockDataResult(
        source="mock",
        retrieved_at=dt.datetime(2026, 6, 17, tzinfo=dt.UTC),
        ticker=Ticker(code=code, market="sh" if code.startswith("6") else "sz"),
        bars=[
            OHLCVBar(
                date=(start_date + dt.timedelta(days=index)).isoformat(),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1000,
            )
            for index, close in enumerate(closes)
        ],
    )


def test_market_breadth_counts_limits_and_returns_indices() -> None:
    eastmoney = FakeEastmoney(
        [
            {"f12": "000001", "f14": "平安银行", "f2": 10.98, "f3": 9.8},
            {"f12": "300001", "f14": "特锐德", "f2": 12.0, "f3": 19.6},
            {"f12": "688017", "f14": "绿的谐波", "f2": 8.0, "f3": -19.5},
            {"f12": "920001", "f14": "北证样本", "f2": 13.0, "f3": 29.6},
            {"f12": "600001", "f14": "*ST样本", "f2": 4.8, "f3": -4.8},
        ]
    )

    result = get_market_breadth("2026-06-17", eastmoney=eastmoney, stock_data_func=lambda *args: _bars(args[0], [10, 11, 12.1]))

    assert [item.key for item in result.indices] == ["sh", "sz", "cyb", "kc50", "hs300", "zz500"]
    assert eastmoney.index_calls == ["1.000001", "0.399001", "0.399006", "1.000688", "1.000300", "1.000905"]
    assert result.limit_stats.limit_up_count == 3
    assert result.limit_stats.limit_down_count == 2
    assert result.source == "eastmoney+derived"
    assert result.raw["sources"]["board_ladders"] == "derived.kline.threshold"


def test_board_ladder_derives_three_boards_and_breaks_chain() -> None:
    rows = [{"f12": "688017", "f14": "绿的谐波", "f2": 13.31, "f3": 20.0}]
    eastmoney = FakeEastmoney(rows)

    def stock_data_func(symbol: str, start: str, end: str) -> StockDataResult:
        assert symbol == "688017"
        assert end == "2026-06-17"
        return _bars(symbol, [10.0, 12.0, 14.4, 17.28], start="2026-06-14")

    result = get_market_breadth("2026-06-17", eastmoney=eastmoney, stock_data_func=stock_data_func)

    assert 3 in result.board_ladders
    assert result.board_ladders[3][0].code == "688017"
    assert result.board_ladders[3][0].boards == 3
    assert any("derived" in warning for warning in result.warnings)


def test_non_limit_day_breaks_board_chain() -> None:
    rows = [{"f12": "688017", "f14": "绿的谐波", "f2": 14.52, "f3": 20.0}]
    eastmoney = FakeEastmoney(rows)

    def stock_data_func(symbol: str, start: str, end: str) -> StockDataResult:
        return _bars(symbol, [10.0, 12.0, 12.1, 14.52], start="2026-06-14")

    result = get_market_breadth("2026-06-17", eastmoney=eastmoney, stock_data_func=stock_data_func)

    assert list(result.board_ladders) == [1]
    assert result.board_ladders[1][0].code == "688017"


def test_invalid_date_rejected() -> None:
    with pytest.raises(MarketValidationError):
        get_market_breadth("2026/06/17", eastmoney=FakeEastmoney([]))


def test_no_persistent_state_file_created(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = get_market_breadth("2026-06-17", eastmoney=FakeEastmoney([]), stock_data_func=lambda *args: _bars(args[0], []))

    assert result.board_ladders == {}
    assert not list(tmp_path.glob("*.sqlite"))
