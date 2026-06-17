from __future__ import annotations

import datetime as dt

import pytest

from astock_data.cache import CsvKlineCache
from astock_data.config import AStockSettings
from astock_data.errors import MarketValidationError
from astock_data.models import OHLCVBar, StockDataResult
from astock_data.services.market_data import get_indicators, get_stock_data


pytestmark = pytest.mark.unit


def _row(day: str, close: float) -> dict:
    return {
        "date": day,
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 1000 + int(close),
    }


def _bars() -> list[dict]:
    return [
        _row("2026-05-09", 9),
        _row("2026-05-10", 10),
        _row("2026-05-11", 11),
        _row("2026-05-12", 12),
        _row("2026-05-13", 13),
    ]


class FakeTdx:
    def __init__(self, rows: list[dict] | None = None, *, raises: bool = False) -> None:
        self.rows = rows if rows is not None else _bars()
        self.raises = raises
        self.calls = 0

    def bars(self, code: str, period: str = "day") -> list[dict]:
        self.calls += 1
        if self.raises:
            raise RuntimeError("tdx failed")
        assert code == "688017"
        self.period = period
        return self.rows

    def daily_bars(self, code: str) -> list[dict]:
        return self.bars(code, period="day")


class FakeSina:
    def __init__(self, rows: list[dict] | None = None, *, raises: bool = False) -> None:
        self.rows = rows if rows is not None else [_row("2026-05-11", 21), _row("2026-05-12", 22)]
        self.raises = raises
        self.calls = 0

    def kline(self, code: str, start_date: str | None = None, end_date: str | None = None, period: str = "day") -> list[dict]:
        self.calls += 1
        if self.raises:
            raise RuntimeError("sina failed")
        assert code == "688017"
        self.period = period
        return [
            row
            for row in self.rows
            if (start_date is None or row["date"] >= start_date)
            and (end_date is None or row["date"] <= end_date)
        ]


def _cache(tmp_cache_dir) -> CsvKlineCache:
    return CsvKlineCache(tmp_cache_dir / "kline", ttl=dt.timedelta(hours=12))


def _settings(tmp_cache_dir) -> AStockSettings:
    return AStockSettings(cache_dir=tmp_cache_dir, kline_cache_ttl_hours=12)


def test_stock_data_returns_structured_sorted_bars_with_metadata(tmp_cache_dir) -> None:
    tdx = FakeTdx(rows=list(reversed(_bars())))
    result = get_stock_data(
        "SH688017",
        "2026-05-10",
        "2026-05-12",
        settings=_settings(tmp_cache_dir),
        cache=_cache(tmp_cache_dir),
        tdx=tdx,
        sina=FakeSina(rows=[_row("2026-05-12", 22), _row("2026-05-10", 20), _row("2026-05-11", 21)]),
    )

    assert isinstance(result, StockDataResult)
    assert result.ticker.code == "688017"
    assert result.source == "sina"
    assert result.period == "day"
    assert tdx.calls == 0
    assert result.retrieved_at.tzinfo is not None
    assert [bar.date for bar in result.bars] == [
        "2026-05-10",
        "2026-05-11",
        "2026-05-12",
    ]
    assert all(isinstance(bar, OHLCVBar) for bar in result.bars)


def test_cache_hit_avoids_client_calls(tmp_cache_dir) -> None:
    cache = _cache(tmp_cache_dir)
    cache.write(
        "688017",
        [OHLCVBar(date=dt.date(2026, 5, 12), open=1, high=2, low=0.5, close=1.5, volume=100)],
    )
    tdx = FakeTdx()
    sina = FakeSina()

    result = get_stock_data(
        "688017",
        "2026-05-12",
        "2026-05-12",
        settings=_settings(tmp_cache_dir),
        cache=cache,
        tdx=tdx,
        sina=sina,
    )

    assert result.source == "cache"
    assert tdx.calls == 0
    assert sina.calls == 0
    assert result.bars[0].close == 1.5


def test_week_uses_sina_primary_and_records_period(tmp_cache_dir) -> None:
    tdx = FakeTdx(rows=[])
    sina = FakeSina(rows=[_row("2026-05-11", 31), _row("2026-05-12", 32)])

    result = get_stock_data(
        "688017",
        "2026-05-11",
        "2026-05-12",
        period="week",
        settings=_settings(tmp_cache_dir),
        cache=_cache(tmp_cache_dir),
        tdx=tdx,
        sina=sina,
    )

    assert result.source == "sina"
    assert result.period == "week"
    assert tdx.calls == 0
    assert sina.calls == 1
    assert sina.period == "week"
    assert [bar.close for bar in result.bars] == [31, 32]


def test_month_falls_back_to_mootdx_when_sina_empty(tmp_cache_dir) -> None:
    tdx = FakeTdx(rows=[_row("2026-05-11", 41), _row("2026-05-12", 42)])
    result = get_stock_data(
        "688017",
        "2026-05-11",
        "2026-05-12",
        period="month",
        settings=_settings(tmp_cache_dir),
        cache=_cache(tmp_cache_dir),
        tdx=tdx,
        sina=FakeSina(rows=[]),
    )

    assert result.source == "mootdx"
    assert result.period == "month"
    assert tdx.period == "month"
    assert [bar.close for bar in result.bars] == [41, 42]


def test_one_minute_uses_sina_primary_with_minute_timestamp(tmp_cache_dir) -> None:
    tdx = FakeTdx(rows=[_row("2026-05-12 09:31", 51), _row("2026-05-12 09:32", 52)])
    sina = FakeSina(rows=[_row("2026-05-12 09:31", 99), _row("2026-05-12 09:32", 100)])

    result = get_stock_data(
        "688017",
        "2026-05-12",
        "2026-05-12",
        period="1min",
        settings=_settings(tmp_cache_dir),
        cache=_cache(tmp_cache_dir),
        tdx=tdx,
        sina=sina,
    )

    assert result.source == "sina"
    assert result.period == "1min"
    assert tdx.calls == 0
    assert sina.period == "1min"
    assert [bar.date for bar in result.bars] == ["2026-05-12 09:31", "2026-05-12 09:32"]


def test_stock_data_filters_future_bars_after_end_date(tmp_cache_dir) -> None:
    result = get_stock_data(
        "688017",
        "2026-05-10",
        "2026-05-12",
        settings=_settings(tmp_cache_dir),
        cache=_cache(tmp_cache_dir),
        tdx=FakeTdx(rows=_bars()),
        sina=FakeSina(rows=[]),
    )

    assert [bar.date for bar in result.bars] == [
        "2026-05-10",
        "2026-05-11",
        "2026-05-12",
    ]
    assert all(bar.date <= "2026-05-12" for bar in result.bars)


def test_indicators_rsi_returns_values_and_filters_after_curr_date(tmp_cache_dir) -> None:
    rows = [_row((dt.date(2026, 4, 1) + dt.timedelta(days=i)).isoformat(), float(10 + i)) for i in range(45)]
    result = get_indicators(
        "688017",
        "rsi",
        "2026-05-12",
        30,
        settings=_settings(tmp_cache_dir),
        tdx=FakeTdx(rows=rows),
        sina=FakeSina(),
    )

    assert result.ticker == "688017"
    assert result.indicator == "rsi"
    assert result.source == "stockstats"
    assert result.retrieved_at.tzinfo is not None
    assert result.points
    assert all(point.date <= "2026-05-12" for point in result.points)
    assert any(isinstance(point.value, float) for point in result.points)


def test_unsupported_indicator_raises_typed_error(tmp_cache_dir) -> None:
    with pytest.raises(MarketValidationError, match="Supported indicators"):
        get_indicators(
            "688017",
            "not_real",
            "2026-05-12",
            30,
            settings=_settings(tmp_cache_dir),
            tdx=FakeTdx(),
            sina=FakeSina(),
        )


def test_empty_range_returns_empty_bars(tmp_cache_dir) -> None:
    result = get_stock_data(
        "688017",
        "2026-05-20",
        "2026-05-21",
        settings=_settings(tmp_cache_dir),
        cache=_cache(tmp_cache_dir),
        tdx=FakeTdx(rows=_bars()),
        sina=FakeSina(rows=[]),
    )

    assert result.source == "mootdx"
    assert result.bars == []


def test_invalid_period_raises_typed_error(tmp_cache_dir) -> None:
    with pytest.raises(MarketValidationError, match="Supported periods"):
        get_stock_data(
            "688017",
            "2026-05-11",
            "2026-05-12",
            period="2min",
            settings=_settings(tmp_cache_dir),
            cache=_cache(tmp_cache_dir),
            tdx=FakeTdx(),
            sina=FakeSina(),
        )


def test_cache_key_includes_non_day_period(tmp_cache_dir) -> None:
    cache = _cache(tmp_cache_dir)
    get_stock_data(
        "688017",
        "2026-05-11",
        "2026-05-12",
        period="week",
        settings=_settings(tmp_cache_dir),
        cache=cache,
        tdx=FakeTdx(),
        sina=FakeSina(rows=[_row("2026-05-11", 61), _row("2026-05-12", 62)]),
    )

    assert (tmp_cache_dir / "kline" / "688017-week.csv").exists()
