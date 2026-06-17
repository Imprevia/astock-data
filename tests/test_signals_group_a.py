from __future__ import annotations

import csv
from pathlib import Path

import pytest

from astock_data.services.signals_a import (
    get_hot_stocks,
    get_insider_transactions,
    get_northbound_flow,
    get_profit_forecast,
)

pytestmark = pytest.mark.unit


class FakeResponse:
    def __init__(self, *, text: str = "", json_data: dict | None = None) -> None:
        self.text = text
        self._json_data = json_data or {}

    def json(self) -> dict:
        return self._json_data

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.urls: list[str] = []

    def get(self, url: str, **kwargs):
        self.urls.append(url)
        return self.response


class FakeTencent:
    def quote(self, codes: list[str]) -> dict:
        return {codes[0]: {"price": 24.0, "pe_ttm": 18.5}}


class FakeTdx:
    def f10_shareholders(self, code: str) -> dict:
        return {
            "content": f"【1.股东研究】\n{code} 股东户数下降\n【2.十大股东】\n机构持股",
            "sections": {"股东研究": "股东户数下降", "十大股东": "机构持股"},
        }


def test_profit_forecast_parses_analyst_coverage_and_low_coverage_warning():
    html = """
    <table>
      <tr><th>预测年度</th><th>研究员数</th><th>最小值</th><th>平均值</th><th>最大值</th></tr>
      <tr><td>2026</td><td>2</td><td>1.00</td><td>1.20</td><td>1.40</td></tr>
      <tr><td>2027</td><td>5</td><td>1.20</td><td>1.80</td><td>2.10</td></tr>
    </table>
    """
    result = get_profit_forecast(
        "SH688017",
        curr_date="2026-06-17",
        ths_session=FakeSession(FakeResponse(text=html)),
        tencent=FakeTencent(),
    )

    assert result.ticker == "688017"
    assert result.source == "ths+tencent"
    assert result.retrieved_at is not None
    assert result.rows[0] == {"fy": "2026", "analysts": 2, "min": 1.0, "avg": 1.2, "max": 1.4}
    assert result.forward_pe == pytest.approx(20.0)
    assert result.peg == pytest.approx(0.4)
    assert result.warnings == ["low analyst coverage for FY2026 (<3 analysts)"]


def test_hot_stocks_include_theme_frequency():
    payload = {
        "errocode": 0,
        "data": [
            {
                "code": "688017",
                "name": "样本科技",
                "reason": "AI+算力",
                "zhangfu": "20.00",
                "huanshou": "12.3",
                "chengjiaoe": "8.5",
                "ddejingliang": "1.2",
            },
            {
                "code": "000001",
                "name": "样本银行",
                "reason": "AI+金融",
                "zhangfu": "10.00",
                "huanshou": "3.1",
                "chengjiaoe": "5.0",
                "ddejingliang": "0.4",
            },
        ],
    }
    result = get_hot_stocks("2026-06-17", ths_session=FakeSession(FakeResponse(json_data=payload)))

    assert result.date.isoformat() == "2026-06-17"
    assert result.source == "ths"
    assert result.items[0].code == "688017"
    assert result.items[0].reason == "AI+算力"
    assert result.theme_frequency == {"AI": 2, "算力": 1, "金融": 1}


def test_northbound_flow_history_from_cache_only_when_requested(tmp_path: Path):
    cache_file = tmp_path / "northbound_daily.csv"
    with cache_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "hgt", "sgt"])
        writer.writerow(["2026-06-14", "1.00", "2.00"])
    payload = {"time": ["09:30", "15:00"], "hgt": ["1.5", "2.0"], "sgt": ["-0.5", "1.0"]}

    no_history = get_northbound_flow(
        "2026-06-17",
        ths_session=FakeSession(FakeResponse(json_data=payload)),
        cache=tmp_path,
    )
    with_history = get_northbound_flow(
        "2026-06-17",
        include_history=True,
        ths_session=FakeSession(FakeResponse(json_data=payload)),
        cache=tmp_path,
    )

    assert no_history.history is None
    assert with_history.history is not None
    assert {row["date"] for row in with_history.history} == {"2026-06-14", "2026-06-17"}
    assert with_history.realtime[-1]["total"] == pytest.approx(3.0)
    assert with_history.signal == "INFLOW"
    assert with_history.source == "ths+hsgt"


def test_insider_shareholder_returns_f10_content_and_sections():
    result = get_insider_transactions("688017", tdx=FakeTdx())

    assert result.ticker == "688017"
    assert "股东户数下降" in result.content
    assert result.sections == {"股东研究": "股东户数下降", "十大股东": "机构持股"}
    assert result.source == "mootdx F10"
    assert result.retrieved_at is not None


def test_signal_results_do_not_emit_buy_or_sell_advice(tmp_path: Path):
    flow = get_northbound_flow(
        "2026-06-17",
        ths_session=FakeSession(FakeResponse(json_data={"time": ["15:00"], "hgt": ["-1"], "sgt": ["0"]})),
        cache=tmp_path,
    )

    assert flow.signal == "OUTFLOW"
    dumped = flow.model_dump(mode="json")
    rendered = str(dumped).lower()
    assert "buy" not in rendered
    assert "sell" not in rendered
