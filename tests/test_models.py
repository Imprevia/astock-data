from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from astock_data.models import (
    BoardItem,
    ConceptBlock,
    ConceptBlocksResult,
    FinancialRow,
    FinancialStatementResult,
    FundFlowResult,
    FundFlowRow,
    FundamentalsResult,
    GlobalNewsResult,
    HotStockItem,
    HotStocksResult,
    IndexSnapshot,
    IndicatorPoint,
    IndicatorResult,
    KlineBar,
    NewsItem,
    NewsResult,
    LimitStats,
    MarketBreadthResult,
    OHLCVBar,
    OrderBookChange,
    OrderBookLevel,
    OrderBookResult,
    OrderBookSnapshot,
    Quote,
    ResultBase,
    ResultMeta,
    StockDataResult,
    Ticker,
)


RETRIEVED_AT = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)


def test_ticker_code_validation_accepts_supported_markets() -> None:
    assert Ticker(code="688017", market="sh").code == "688017"
    assert Ticker(code="000001", market="sz").code == "000001"
    assert Ticker(code="835185", market="bj").code == "835185"
    assert Ticker(code="920267", market="bj").code == "920267"
    assert Ticker(code="430047", market="bj").code == "430047"


def test_ticker_code_validation_rejects_path_like_values() -> None:
    with pytest.raises(ValidationError):
        Ticker(code="../x", market="sh")


def test_result_meta_and_base_carry_common_fields() -> None:
    meta = ResultMeta(source="mootdx", retrieved_at=RETRIEVED_AT, ticker="000001")
    base = ResultBase(source="eastmoney", retrieved_at=RETRIEVED_AT, raw={"ok": True})

    assert meta.model_dump(mode="json")["retrieved_at"] == "2026-06-17T12:00:00Z"
    assert base.source == "eastmoney"
    assert base.warnings == []


def test_market_models_serialize_to_json() -> None:
    stock = StockDataResult(
        source="mootdx",
        retrieved_at=RETRIEVED_AT,
        ticker=Ticker(code="688017", market="sh", name="绿的谐波"),
        bars=[OHLCVBar(date=date(2026, 6, 17), open=1, high=2, low=0.5, close=1.5, volume=1000)],
    )
    indicator = IndicatorResult(
        source="stockstats",
        retrieved_at=RETRIEVED_AT,
        indicator="rsi",
        points=[IndicatorPoint(date=date(2026, 6, 17), value="N/A")],
    )

    assert stock.model_dump(mode="json")["bars"][0]["date"] == "2026-06-17"
    assert indicator.model_dump(mode="json")["points"][0]["value"] == "N/A"


def test_order_book_models_preserve_visible_depth_semantics() -> None:
    snapshot = OrderBookSnapshot(
        vendor_timestamp="20260804101530",
        last_price=10.0,
        bids=[OrderBookLevel(position=1, price=9.99, volume_lots=100)],
        asks=[OrderBookLevel(position=1, price=10.01, volume_lots=120)],
        bid_depth_lots=100,
        ask_depth_lots=120,
        spread=0.02,
        imbalance=-20 / 220,
    )
    change = OrderBookChange(
        side="bid",
        price=9.99,
        previous_volume_lots=100,
        current_volume_lots=60,
        delta_volume_lots=-40,
        event="depth-decrease",
        attribution="unattributed",
        from_vendor_timestamp="20260804101530",
        to_vendor_timestamp="20260804101531",
    )
    result = OrderBookResult(
        source="tencent",
        retrieved_at=RETRIEVED_AT,
        ticker=Ticker(code="000001", market="sz"),
        samples_requested=2,
        interval_seconds=1.0,
        snapshots=[snapshot],
        changes=[change],
    )

    dumped = result.model_dump(mode="json")
    assert dumped["snapshots"][0]["vendor_timestamp"] == "20260804101530"
    assert dumped["snapshots"][0]["bid_depth_lots"] == 100
    assert dumped["exact_cancellation_available"] is False
    assert dumped["changes"][0]["event"] == "depth-decrease"
    assert dumped["changes"][0]["attribution"] == "unattributed"


def test_order_book_level_schema_uses_position_contract() -> None:
    schema = OrderBookLevel.model_json_schema()

    assert set(schema["properties"]) == {"position", "price", "volume_lots"}
    assert set(schema["required"]) == {"position", "price", "volume_lots"}
    assert "level" not in schema["properties"]


def test_market_breadth_models_serialize_to_json() -> None:
    result = MarketBreadthResult(
        source="eastmoney+derived",
        retrieved_at=RETRIEVED_AT,
        date="2026-06-17",
        indices=[IndexSnapshot(key="sh", name="上证指数", price=4108.07, change=16.2, change_pct=0.39)],
        limit_stats=LimitStats(limit_up_count=65, limit_down_count=2),
        board_ladders={3: [BoardItem(code="688017", name="绿的谐波", boards=3, close=80.0, change_pct=20.0)]},
        warnings=["derived"],
    )

    dumped = result.model_dump(mode="json")
    assert dumped["source"] == "eastmoney+derived"
    assert dumped["indices"][0]["key"] == "sh"
    assert dumped["limit_stats"]["limit_down_count"] == 2
    assert dumped["limit_stats"]["status"] == "available"
    assert dumped["board_ladders"]["3"][0]["boards"] == 3


def test_limit_stats_preserve_unavailable_side_without_fabricating_zero() -> None:
    stats = LimitStats(
        limit_up_count=3,
        limit_down_count=None,
        status="partial",
    )

    assert stats.limit_up_count == 3
    assert stats.limit_down_count is None
    assert stats.status == "partial"


def test_kline_bar_additive_evidence_metrics_are_optional() -> None:
    bare = KlineBar(date="2026-08-05")
    enriched = KlineBar(
        date="2026-08-05",
        change_pct=9.98,
        turnover_pct=12.34,
    )

    assert bare.change_pct is None
    assert bare.turnover_pct is None
    assert enriched.change_pct == 9.98
    assert enriched.turnover_pct == 12.34


def test_fundamentals_models_serialize_to_json() -> None:
    fundamentals = FundamentalsResult(
        source="tencent",
        retrieved_at=RETRIEVED_AT,
        quote=Quote(price=10.5, pe_ttm=12.3, pb=1.8),
        snapshot={"roe": 8.2},
    )
    statement = FinancialStatementResult(
        source="sina",
        retrieved_at=RETRIEVED_AT,
        statement_type="income",
        freq="annual",
        rows=[FinancialRow(report_date=date(2025, 12, 31), fields={"revenue": 100})],
    )

    assert fundamentals.model_dump(mode="json")["quote"]["price"] == 10.5
    assert statement.model_dump(mode="json")["rows"][0]["report_date"] == "2025-12-31"


def test_news_models_serialize_to_json() -> None:
    item = NewsItem(title="公告", content="内容", time=RETRIEVED_AT, source="cls", url="https://example.com")
    news = NewsResult(source="eastmoney", retrieved_at=RETRIEVED_AT, items=[item])
    global_news = GlobalNewsResult(source="cls", retrieved_at=RETRIEVED_AT, items=[item])

    assert news.model_dump(mode="json")["items"][0]["time"] == "2026-06-17T12:00:00Z"
    assert global_news.model_dump(mode="json")["items"][0]["title"] == "公告"


def test_signal_models_serialize_to_json() -> None:
    hot = HotStocksResult(
        source="10jqka",
        retrieved_at=RETRIEVED_AT,
        date=date(2026, 6, 17),
        items=[HotStockItem(code="000001", name="平安银行", reason="放量", zhangfu=2.5)],
        theme_frequency={"银行": 1},
    )
    concepts = ConceptBlocksResult(
        source="baidu",
        retrieved_at=RETRIEVED_AT,
        concepts=[ConceptBlock(name="机器人", ratio=0.8, describe="概念")],
        industries=[],
        regions=[],
        concept_tags=["机器人"],
    )
    flow = FundFlowResult(
        source="eastmoney",
        retrieved_at=RETRIEVED_AT,
        minute=[FundFlowRow(time=RETRIEVED_AT, main_net_inflow=100.0)],
        signal="inflow",
    )

    assert hot.model_dump(mode="json")["date"] == "2026-06-17"
    assert concepts.model_dump(mode="json")["concepts"][0]["name"] == "机器人"
    assert flow.model_dump(mode="json")["minute"][0]["time"] == "2026-06-17T12:00:00Z"
