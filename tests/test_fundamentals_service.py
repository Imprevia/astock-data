from __future__ import annotations

import datetime as dt

import pytest

from astock_data.cache import SQLiteStructuredCache
from astock_data.errors import DataSourceError
from astock_data.services.fundamentals import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
)

pytestmark = pytest.mark.unit


class FakeTencent:
    calls: int

    def __init__(self, payload: dict | None = None, exc: Exception | None = None) -> None:
        self.payload = payload or {
            "688017": {
                "name": "测试股份",
                "price": 10.5,
                "pe_ttm": 21.2,
                "pe_static": 18.6,
                "pb": 2.4,
                "mcap_yi": 120.0,
                "float_mcap_yi": 80.0,
                "turnover_pct": 3.2,
                "change_pct": 1.5,
                "limit_up": 11.55,
                "limit_down": 9.45,
            }
        }
        self.exc = exc
        self.calls = 0

    def quote(self, codes: list[str]) -> dict:
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return {code: self.payload[code] for code in codes if code in self.payload}


class FakeTdx:
    def __init__(self, payload: dict | None = None, exc: Exception | None = None) -> None:
        self.payload = payload or {
            "code": "688017",
            "eps": 1.23,
            "nav_per_share": 8.8,
            "net_assets": 1000000,
            "operating_revenue": 2000000,
            "_raw": {"meigushouyi": 1.23},
        }
        self.exc = exc
        self.calls = 0

    def financial_snapshot(self, code: str) -> dict:
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.payload | {"code": code}


class FakeEastmoney:
    def __init__(self, payload: dict | None = None, exc: Exception | None = None) -> None:
        self.payload = payload or {
            "data": {
                "f12": "688017",
                "f14": "测试股份",
                "f26": "20200101",
                "f84": 50000000,
                "f100": "通用设备",
            }
        }
        self.exc = exc
        self.calls = []

    def push2(self, path: str, params: dict) -> dict:
        self.calls.append((path, params))
        if self.exc is not None:
            raise self.exc
        return self.payload


class FakeResponse:
    text = "<table><tr><th>年度</th><th>EPS</th></tr><tr><td>2026E</td><td>1.50</td></tr></table>"


class FakeThsSession:
    def get(self, url: str, timeout: int) -> FakeResponse:
        assert "688017" in url
        assert timeout == 15
        return FakeResponse()


class FakeSina:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or [
            {"report_date": "2026-09-30", "fields": {"报告日": "2026-09-30", "资产": 9}},
            {"report_date": "2026-06-30", "fields": {"报告日": "2026-06-30", "资产": 6}},
            {"report_date": "2025-12-31", "fields": {"报告日": "2025-12-31", "资产": 12}},
            {"report_date": "2025-09-30", "fields": {"报告日": "2025-09-30", "资产": 5}},
        ]
        self.calls = []

    def financial_report(self, code: str, report_type: str, freq: str = "quarterly") -> list[dict]:
        self.calls.append((code, report_type, freq))
        return list(self.rows)


def test_fundamentals_aggregates_available_sources(tmp_path) -> None:
    result = get_fundamentals(
        "688017",
        "2026-06-17",
        tencent=FakeTencent(),
        tdx=FakeTdx(),
        eastmoney=FakeEastmoney(),
        ths_session=FakeThsSession(),
        cache=SQLiteStructuredCache(tmp_path),
    )

    assert result.ticker == "688017"
    assert result.name == "测试股份"
    assert result.source == "composite"
    assert isinstance(result.retrieved_at, dt.datetime)
    assert result.quote.price == pytest.approx(10.5)
    assert result.quote.market_cap_yi == pytest.approx(120.0)
    assert result.snapshot["eps"] == pytest.approx(1.23)
    assert result.snapshot["industry"] == "通用设备"
    assert result.snapshot["raw"] == {"meigushouyi": 1.23}
    assert result.consensus_forecast is not None
    assert result.consensus_forecast["rows"][0]["EPS"] == pytest.approx(1.5)
    assert result.warnings == []


def test_missing_optional_source_records_warning_not_failure(tmp_path) -> None:
    result = get_fundamentals(
        "688017",
        "2026-06-17",
        tencent=FakeTencent(),
        tdx=FakeTdx(),
        eastmoney=FakeEastmoney(exc=RuntimeError("eastmoney down")),
        ths_session=None,
        cache=SQLiteStructuredCache(tmp_path),
    )

    assert result.quote.pe_ttm == pytest.approx(21.2)
    assert any("Eastmoney stock info unavailable" in warning for warning in result.warnings)


def test_all_required_fundamental_sources_fail(tmp_path) -> None:
    with pytest.raises(DataSourceError):
        get_fundamentals(
            "688017",
            "2026-06-17",
            tencent=FakeTencent(exc=RuntimeError("tencent down")),
            tdx=FakeTdx(exc=RuntimeError("tdx down")),
            eastmoney=FakeEastmoney(exc=RuntimeError("eastmoney down")),
            cache=SQLiteStructuredCache(tmp_path),
        )


def test_fundamentals_uses_sqlite_cache_roundtrip(tmp_path) -> None:
    cache = SQLiteStructuredCache(tmp_path)
    tencent = FakeTencent()
    first = get_fundamentals(
        "688017",
        "2026-06-17",
        tencent=tencent,
        tdx=FakeTdx(),
        eastmoney=FakeEastmoney(),
        cache=cache,
    )
    second = get_fundamentals(
        "688017",
        "2026-06-17",
        tencent=FakeTencent(exc=AssertionError("should hit cache")),
        tdx=FakeTdx(exc=AssertionError("should hit cache")),
        eastmoney=FakeEastmoney(exc=AssertionError("should hit cache")),
        cache=cache,
    )

    assert tencent.calls == 1
    assert second.quote.price == first.quote.price
    assert second.retrieved_at == first.retrieved_at


def test_statement_filters_future_reports_and_annual_december_only(tmp_path) -> None:
    result = get_balance_sheet(
        "688017",
        freq="annual",
        curr_date="2026-06-17",
        sina=FakeSina(),
        cache=SQLiteStructuredCache(tmp_path),
    )

    assert result.source == "sina"
    assert result.statement_type == "balance"
    assert result.freq == "annual"
    assert [row.report_date.isoformat() for row in result.rows] == ["2025-12-31"]
    assert result.rows[0].fields["报告日"] == "2025-12-31"


def test_statement_quarterly_filters_by_curr_date_and_keeps_raw_fields(tmp_path) -> None:
    result = get_income_statement(
        "688017",
        curr_date="2026-06-30",
        sina=FakeSina(),
        cache=SQLiteStructuredCache(tmp_path),
    )

    assert result.statement_type == "income"
    assert [row.report_date.isoformat() for row in result.rows] == ["2026-06-30", "2025-12-31", "2025-09-30"]
    assert result.rows[0].fields == {"报告日": "2026-06-30", "资产": 6}


def test_statements_use_sqlite_cache_roundtrip(tmp_path) -> None:
    cache = SQLiteStructuredCache(tmp_path)
    sina = FakeSina()
    first = get_cashflow(
        "688017",
        curr_date="2026-06-30",
        sina=sina,
        cache=cache,
    )
    second = get_cashflow(
        "688017",
        curr_date="2026-06-30",
        sina=FakeSina(rows=[]),
        cache=cache,
    )

    assert sina.calls == [("688017", "cashflow", "quarterly")]
    assert [row.report_date for row in second.rows] == [row.report_date for row in first.rows]
    assert second.retrieved_at == first.retrieved_at
