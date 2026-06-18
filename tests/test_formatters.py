from __future__ import annotations

from datetime import date, datetime, timezone
import importlib
import sys

import pytest

from astock_data.models import (
    ConceptBlocksResult,
    DragonTigerResult,
    FinancialStatementResult,
    FundFlowResult,
    FundamentalsResult,
    GlobalNewsResult,
    HotStocksResult,
    IndexSnapshot,
    IndicatorResult,
    IndustryComparisonResult,
    LockupExpiryResult,
    LimitStats,
    MarketBreadthResult,
    NewsResult,
    NorthboundFlowResult,
    ProfitForecastResult,
    Quote,
    ShareholderResult,
    StockDataResult,
    Ticker,
)

RETRIEVED_AT = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)


def _instances() -> list[object]:
    return [
        StockDataResult(source="mootdx", retrieved_at=RETRIEVED_AT, ticker=Ticker(code="688017", market="sh"), bars=[]),
        IndicatorResult(source="stockstats", retrieved_at=RETRIEVED_AT, indicator="rsi", description="相对强弱指标", points=[]),
        MarketBreadthResult(source="eastmoney+derived", retrieved_at=RETRIEVED_AT, date="2026-06-17", indices=[IndexSnapshot(key="sh", name="上证指数", price=4108.0)], limit_stats=LimitStats(limit_up_count=65, limit_down_count=2), board_ladders={}),
        FundamentalsResult(source="tencent", retrieved_at=RETRIEVED_AT, quote=Quote(price=10.5, pe_ttm=12.3), snapshot={"turnover_pct": 1.2}, consensus_forecast={"eps_next_year": 1.5}),
        FinancialStatementResult(source="sina", retrieved_at=RETRIEVED_AT, statement_type="income", freq="annual", rows=[]),
        NewsResult(source="eastmoney", retrieved_at=RETRIEVED_AT, items=[]),
        GlobalNewsResult(source="cls", retrieved_at=RETRIEVED_AT, items=[]),
        ShareholderResult(source="mootdx", retrieved_at=RETRIEVED_AT, content="股东信息", sections={"概要": "稳定"}),
        ProfitForecastResult(source="10jqka", retrieved_at=RETRIEVED_AT, rows=[{"year": 2026, "eps": 1.2, "revenue": 100.0, "net_profit": 10.0}], forward_pe=15.2, peg=0.8),
        HotStocksResult(source="10jqka", retrieved_at=RETRIEVED_AT, date=date(2026, 6, 17), items=[{"code": "000001", "name": "平安银行", "reason": "题材活跃", "zhangfu": 3.2, "huanshou": 1.1}], theme_frequency={"银行": 2}),
        NorthboundFlowResult(source="eastmoney", retrieved_at=RETRIEVED_AT, realtime=[{"name": "沪股通", "net_inflow": 12.3}], history=[{"date": "2026-06-16", "net_inflow": 8.8}]),
        ConceptBlocksResult(source="baidu", retrieved_at=RETRIEVED_AT, concepts=[{"name": "人工智能", "ratio": 0.2, "describe": "主题"}], industries=[], regions=[], concept_tags=["科技"]),
        FundFlowResult(source="eastmoney", retrieved_at=RETRIEVED_AT, minute=[{"time": "09:31", "main_net_inflow": 1.2, "super_large_net_inflow": 0.8}], daily=[{"time": "2026-06-16", "main_net_inflow": 5.6}]),
        DragonTigerResult(source="eastmoney", retrieved_at=RETRIEVED_AT, events=[{"date": "2026-06-16", "reason": "上榜", "close": 10.5, "change_pct": 3.2, "net_buy": 1.1, "amount": 20.0}], buy_seats=[{"seat_name": "机构专用", "buy_amount": 10.0, "net_amount": 6.0}], sell_seats=[{"seat_name": "营业部A", "sell_amount": 4.0, "net_amount": -4.0}]),
        LockupExpiryResult(source="eastmoney", retrieved_at=RETRIEVED_AT, history=[], upcoming=[]),
        IndustryComparisonResult(source="eastmoney", retrieved_at=RETRIEVED_AT, rows=[]),
        Ticker(code="000001", market="sz", name="平安银行"),
    ]


@pytest.mark.parametrize("result", _instances())
def test_each_public_result_model_has_markdown_and_text_renderer(result: object) -> None:
    from astock_data.formatters import to_markdown, to_text
    from astock_data.formatters.dispatch import MARKDOWN_RENDERERS, TEXT_RENDERERS

    assert type(result) in MARKDOWN_RENDERERS
    assert type(result) in TEXT_RENDERERS
    assert isinstance(to_markdown(result), str)
    assert isinstance(to_text(result), str)


@pytest.mark.parametrize(
    "result",
    [
        StockDataResult(source="mootdx", retrieved_at=RETRIEVED_AT, ticker=Ticker(code="688017", market="sh"), bars=[]),
        NewsResult(source="eastmoney", retrieved_at=RETRIEVED_AT, items=[]),
        FundFlowResult(source="eastmoney", retrieved_at=RETRIEVED_AT, minute=[]),
    ],
)
def test_empty_results_render_explicit_no_data_message(result: object) -> None:
    from astock_data.formatters import to_markdown, to_text

    assert "No data" in to_markdown(result) or "无数据" in to_markdown(result)
    assert "No data" in to_text(result) or "无数据" in to_text(result)


def test_output_includes_source_and_retrieved_at() -> None:
    from astock_data.formatters import to_markdown, to_text

    result = IndicatorResult(source="stockstats", retrieved_at=RETRIEVED_AT, indicator="rsi", points=[])

    markdown = to_markdown(result)
    text = to_text(result)

    assert "source: stockstats" in markdown
    assert "retrieved_at: 2026-06-17T12:00:00Z" in markdown
    assert "source: stockstats" in text
    assert "retrieved_at: 2026-06-17T12:00:00Z" in text


def test_stockdata_markdown_contains_ohlcv_table_header() -> None:
    from astock_data.formatters import to_markdown, to_text

    result = StockDataResult(
        source="mootdx",
        retrieved_at=RETRIEVED_AT,
        ticker=Ticker(code="688017", market="sh"),
        bars=[{"date": date(2026, 6, 17), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}],
    )

    markdown = to_markdown(result)
    text = to_text(result)

    assert "| date | open | high | low | close | volume |" in markdown
    assert "date" in text and "open" in text
    assert "| date |" not in text


def test_dragon_tiger_renders_seat_rows() -> None:
    from astock_data.formatters import to_markdown, to_text

    result = DragonTigerResult(
        source="eastmoney",
        retrieved_at=RETRIEVED_AT,
        events=[{"date": "2026-06-16", "reason": "上榜", "close": 10.5, "change_pct": 3.2, "net_buy": 1.1, "amount": 20.0}],
        buy_seats=[{"seat_name": "机构专用", "buy_amount": 10.0, "net_amount": 6.0}],
        sell_seats=[{"seat_name": "营业部A", "sell_amount": 4.0, "net_amount": -4.0}],
    )

    markdown = to_markdown(result)
    text = to_text(result)

    assert "Buy Seats" in markdown and "机构专用" in markdown
    assert "Sell Seats" in markdown and "营业部A" in markdown
    assert "seat_name" in text


def test_empty_lockup_expiry_renders_no_data_message() -> None:
    from astock_data.formatters import to_markdown, to_text

    result = LockupExpiryResult(source="eastmoney", retrieved_at=RETRIEVED_AT, history=[], upcoming=[])

    assert "No data" in to_markdown(result) or "无数据" in to_markdown(result)
    assert "No data" in to_text(result) or "无数据" in to_text(result)


def test_formatter_import_does_not_pull_network_vendor_modules() -> None:
    sys.modules.pop("astock_data.formatters", None)
    sys.modules.pop("astock_data.formatters.dispatch", None)
    sys.modules.pop("requests", None)
    sys.modules.pop("mootdx", None)

    importlib.import_module("astock_data.formatters")

    assert "requests" not in sys.modules
    assert "mootdx" not in sys.modules
