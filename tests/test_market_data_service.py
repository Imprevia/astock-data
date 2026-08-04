from __future__ import annotations

import datetime as dt

import pytest

from astock_data.cache import CsvKlineCache
from astock_data.config import AStockSettings
from astock_data.errors import DataSourceError, MarketValidationError
from astock_data.models import OHLCVBar, OrderBookResult, StockDataResult
from astock_data.services.market_data import (
    get_indicators,
    get_order_book,
    get_stock_data,
)


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


def _order_book_snapshot(
    timestamp: str,
    *,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
) -> dict:
    bid_depth = sum(volume for _, volume in bids)
    ask_depth = sum(volume for _, volume in asks)
    total_depth = bid_depth + ask_depth
    return {
        "name": "平安银行",
        "vendor_timestamp": timestamp,
        "last_price": 10.0,
        "bids": [
            {"position": index, "price": price, "volume_lots": volume}
            for index, (price, volume) in enumerate(bids, start=1)
        ],
        "asks": [
            {"position": index, "price": price, "volume_lots": volume}
            for index, (price, volume) in enumerate(asks, start=1)
        ],
        "bid_depth_lots": bid_depth,
        "ask_depth_lots": ask_depth,
        "spread": asks[0][0] - bids[0][0],
        "imbalance": (bid_depth - ask_depth) / total_depth,
    }


class FakeTencentOrderBook:
    def __init__(self, snapshots: list[dict | Exception]) -> None:
        self.snapshots = iter(snapshots)
        self.calls = 0

    def order_book(self, code: str) -> dict:
        assert code == "000001"
        self.calls += 1
        snapshot = next(self.snapshots)
        if isinstance(snapshot, Exception):
            raise snapshot
        return snapshot


def test_order_book_default_is_one_snapshot_without_waiting() -> None:
    client = FakeTencentOrderBook(
        [
            _order_book_snapshot(
                "20260804101530",
                bids=[(9.99, 100)],
                asks=[(10.01, 120)],
            )
        ]
    )

    result = get_order_book(
        "000001",
        tencent=client,
        sleep=lambda _seconds: pytest.fail("single snapshot must not wait"),
    )

    assert isinstance(result, OrderBookResult)
    assert result.samples_requested == 1
    assert result.exact_cancellation_available is False
    assert client.calls == 1
    assert len(result.snapshots) == 1
    assert result.changes == []


def test_order_book_compares_only_same_side_and_same_price() -> None:
    client = FakeTencentOrderBook(
        [
            _order_book_snapshot(
                "20260804101530",
                bids=[(9.99, 100), (9.98, 80)],
                asks=[(10.01, 120)],
            ),
            _order_book_snapshot(
                "20260804101531",
                bids=[(9.99, 60), (9.97, 90)],
                asks=[(10.01, 150)],
            ),
        ]
    )
    waits: list[float] = []

    result = get_order_book(
        "000001",
        samples=2,
        interval_seconds=1.5,
        tencent=client,
        sleep=waits.append,
    )

    by_coordinate = {(change.side, change.price): change for change in result.changes}
    decreased = by_coordinate[("bid", 9.99)]
    assert decreased.event == "depth-decrease"
    assert decreased.previous_volume_lots == 100
    assert decreased.current_volume_lots == 60
    assert decreased.delta_volume_lots == -40
    assert decreased.attribution == "unattributed"
    assert by_coordinate[("bid", 9.98)].event == "left-view"
    assert by_coordinate[("bid", 9.97)].event == "entered-view"
    assert by_coordinate[("ask", 10.01)].event == "depth-increase"
    assert waits == [1.5]


def test_order_book_duplicate_vendor_timestamp_skips_dynamic_comparison() -> None:
    client = FakeTencentOrderBook(
        [
            _order_book_snapshot(
                "20260804101530",
                bids=[(9.99, 100)],
                asks=[(10.01, 120)],
            ),
            _order_book_snapshot(
                "20260804101530",
                bids=[(9.99, 50)],
                asks=[(10.01, 120)],
            ),
        ]
    )

    result = get_order_book(
        "000001",
        samples=2,
        tencent=client,
        sleep=lambda _seconds: None,
    )

    assert len(result.snapshots) == 2
    assert result.changes == []
    assert any("duplicate Tencent vendor timestamp" in item for item in result.warnings)


@pytest.mark.parametrize(
    "samples",
    [
        [DataSourceError("upstream timeout")],
        [{}],
        [{"vendor_timestamp": "invalid"}],
        [DataSourceError("upstream timeout"), {}],
    ],
)
def test_order_book_all_failed_samples_raise_typed_source_error(
    samples: list[dict | Exception],
) -> None:
    client = FakeTencentOrderBook(samples)

    with pytest.raises(
        DataSourceError,
        match=r"Tencent order-book sampling returned no usable snapshots.*ticker=000001",
    ):
        get_order_book(
            "000001",
            samples=len(samples),
            tencent=client,
            sleep=lambda _seconds: None,
        )


def test_order_book_partial_failure_preserves_snapshot_and_warning() -> None:
    client = FakeTencentOrderBook(
        [
            DataSourceError("upstream timeout"),
            _order_book_snapshot(
                "20260804101531",
                bids=[(9.99, 100)],
                asks=[(10.01, 120)],
            ),
        ]
    )

    result = get_order_book(
        "000001",
        samples=2,
        tencent=client,
        sleep=lambda _seconds: None,
    )

    assert len(result.snapshots) == 1
    assert result.changes == []
    assert any("Tencent order-book sample 1 failed" in item for item in result.warnings)


@pytest.mark.parametrize(
    ("samples", "interval_seconds"),
    [(0, 1.0), (61, 1.0), (2, 0.5), (2, 61.0), (60, 6.0)],
)
def test_order_book_rejects_invalid_sampling_before_vendor_access(
    samples: int,
    interval_seconds: float,
) -> None:
    client = FakeTencentOrderBook([])

    with pytest.raises(MarketValidationError):
        get_order_book(
            "000001",
            samples=samples,
            interval_seconds=interval_seconds,
            tencent=client,
        )

    assert client.calls == 0
