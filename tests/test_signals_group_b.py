from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from astock_data.services.signals_b import (
    get_concept_blocks,
    get_dragon_tiger_board,
    get_fund_flow,
    get_industry_comparison,
    get_lockup_expiry,
)

pytestmark = pytest.mark.unit


class FakeEastmoney:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def concept_blocks(self, code: str) -> list[dict[str, Any]]:
        self.calls.append(("concept_blocks", (code,), {}))
        return [
            {"name": "人工智能", "change_pct": 1.2, "direction": "概念"},
            {"name": "申万计算机行业", "change_pct": 0.8},
            {"name": "广东省", "change_pct": -0.1},
        ]

    def push2(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("push2", (path, params), {}))
        if path.endswith("/stock/fflow/kline/get"):
            return {"data": {"klines": ["09:31,100,10,20,30,40", "09:32,-50,1,2,3,4"]}}
        if path.endswith("/clist/get"):
            return {
                "data": {
                    "diff": [
                        {"f12": "BK0001", "f14": "软件开发", "f3": 2.5, "f104": 80, "f105": 20, "f140": "样本股A"},
                        {"f12": "BK0002", "f14": "半导体", "f3": -1.1, "f104": 15, "f105": 75, "f140": "样本股B"},
                    ]
                }
            }
        return {"data": {"diff": []}}

    def push2his(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("push2his", (path, params), {}))
        return {"data": {"klines": ["2026-06-16,200,20,30,40,50"]}}

    def datacenter(
        self,
        report_name: str,
        columns: str = "ALL",
        filter_str: str = "",
        page_size: int = 50,
        sort_columns: str = "",
        sort_types: str = "-1",
    ) -> list[dict[str, Any]]:
        self.calls.append(
            (
                "datacenter",
                (report_name,),
                {
                    "columns": columns,
                    "filter_str": filter_str,
                    "page_size": page_size,
                    "sort_columns": sort_columns,
                    "sort_types": sort_types,
                },
            )
        )
        if report_name == "RPT_DAILYBILLBOARD_DETAILSNEW":
            return [
                {
                    "TRADE_DATE": "2026-06-16 00:00:00",
                    "EXPLANATION": "日涨幅偏离值达7%",
                    "BILLBOARD_NET_AMT": 1230000,
                    "CLOSE_PRICE": 10.5,
                    "CHANGE_RATE": 7.8,
                    "DEAL_AMT": 4560000,
                }
            ]
        if report_name == "RPT_BILLBOARD_DAILYDETAILSBUY":
            return [{"OPERATEDEPT_NAME": "机构专用", "OPERATEDEPT_CODE": "0", "BUY": 1000, "SELL": 100, "NET": 900}]
        if report_name == "RPT_BILLBOARD_DAILYDETAILSSELL":
            return [{"OPERATEDEPT_NAME": "营业部A", "OPERATEDEPT_CODE": "123", "BUY": 50, "SELL": 500, "NET": -450}]
        if report_name == "RPT_LIFT_STAGE" and "FREE_DATE>=" in filter_str:
            return [{"FREE_DATE": "2026-07-01", "HOLDER_NAME": "股东A", "FREE_SHARES_NUM": 1000000, "FREE_RATIO": 1.5}]
        if report_name == "RPT_LIFT_STAGE":
            return [{"FREE_DATE": "2026-05-01", "LIMITED_STOCK_TYPE": "首发限售", "FREE_SHARES_NUM": 2000000, "FREE_RATIO": 2.5}]
        return []


def _all_call_text(fake: FakeEastmoney) -> str:
    return repr(fake.calls)


def test_concept_blocks_use_eastmoney_slist_not_baidu() -> None:
    fake = FakeEastmoney()

    result = get_concept_blocks("SH600000", eastmoney=fake)

    assert fake.calls[0][0] == "concept_blocks"
    assert fake.calls[0][1] == ("600000",)
    assert "finance.pae.baidu" not in _all_call_text(fake)
    assert result.source == "eastmoney slist"
    assert isinstance(result.retrieved_at, dt.datetime)
    assert result.ticker == "600000"
    assert result.concept_tags == ["人工智能"]
    assert result.industries[0].name == "申万计算机行业"
    assert result.regions[0].name == "广东省"


def test_fund_flow_minute_history_and_factual_signal() -> None:
    fake = FakeEastmoney()

    result = get_fund_flow("SH600000", "2026-06-17", eastmoney=fake)

    assert result.source == "eastmoney push2"
    assert isinstance(result.retrieved_at, dt.datetime)
    assert result.ticker == "600000"
    assert result.minute[-1].main_net_inflow == -50
    assert result.daily is not None
    assert result.daily[0].time == "2026-06-16"
    assert result.signal == "OUTFLOW"
    assert "bullish" not in result.model_dump_json().lower()
    assert "bearish" not in result.model_dump_json().lower()
    assert fake.calls[0][0] == "push2"
    assert fake.calls[0][1][1]["secid"] == "1.600000"
    assert fake.calls[1][0] == "push2his"
    assert fake.calls[1][1][1]["secid"] == "1.600000"


def test_fund_flow_can_skip_history() -> None:
    fake = FakeEastmoney()

    result = get_fund_flow("000001", "2026-06-17", include_history=False, eastmoney=fake)

    assert result.daily is None
    assert [call[0] for call in fake.calls] == ["push2"]
    assert fake.calls[0][1][1]["secid"] == "0.000001"


def test_dragon_tiger_accepts_prefixed_ticker_before_eastmoney_call() -> None:
    fake = FakeEastmoney()

    result = get_dragon_tiger_board("SH600000", "2026-06-17", eastmoney=fake)

    assert result.source == "eastmoney datacenter"
    assert isinstance(result.retrieved_at, dt.datetime)
    assert result.ticker == "600000"
    assert result.events[0].date == dt.date(2026, 6, 16)
    assert result.buy_seats[0].seat_name == "机构专用"
    assert result.sell_seats[0].seat_name == "营业部A"
    assert result.institution_flow == {"buy_amount": 1000.0, "sell_amount": 0.0, "net_amount": 1000.0}
    filters = [call[2]["filter_str"] for call in fake.calls if call[0] == "datacenter"]
    assert all('SECURITY_CODE="600000"' in filter_text for filter_text in filters)
    assert all("SH600000" not in filter_text for filter_text in filters)


def test_lockup_expiry_accepts_prefixed_ticker() -> None:
    fake = FakeEastmoney()

    result = get_lockup_expiry("SH688017", "2026-06-17", eastmoney=fake)

    assert result.source == "eastmoney datacenter"
    assert isinstance(result.retrieved_at, dt.datetime)
    assert result.ticker == "688017"
    assert result.history[0].date == dt.date(2026, 5, 1)
    assert result.upcoming[0].date == dt.date(2026, 7, 1)
    filters = [call[2]["filter_str"] for call in fake.calls if call[0] == "datacenter"]
    assert all('SECURITY_CODE="688017"' in filter_text for filter_text in filters)
    assert all("SH688017" not in filter_text for filter_text in filters)


def test_industry_comparison_rows_do_not_overclaim_target_industry() -> None:
    fake = FakeEastmoney()

    result = get_industry_comparison("SH600000", "2026-06-17", top_n=2, eastmoney=fake)

    assert result.source == "eastmoney push2"
    assert isinstance(result.retrieved_at, dt.datetime)
    assert result.ticker == "600000"
    assert result.target_industry is None
    assert [row.name for row in result.rows] == ["软件开发", "半导体"]
    assert result.rows[0].raw["leader"] == "样本股A"
    assert fake.calls[0][0] == "push2"
    assert fake.calls[0][1][1]["fs"] == "m:90+t:2"
