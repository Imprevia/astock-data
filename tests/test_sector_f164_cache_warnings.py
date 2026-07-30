from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from astock_data.cache import SQLiteStructuredCache
from astock_data.clients import eastmoney as eastmoney_module
from astock_data.clients.eastmoney import EastmoneyClient
from astock_data.config import AStockSettings
from astock_data.services import signals_b
from astock_data.services.signals_b import get_sector_fund_flow_history

pytestmark = pytest.mark.unit

_CACHE_KIND = "sector_f164"
_CACHE_SUB_KEY = "industry-five-day"


def _client() -> EastmoneyClient:
    return EastmoneyClient(min_interval=0.0, timeout=5.0)


def _settings(tmp_path) -> AStockSettings:
    return AStockSettings(cache_dir=tmp_path)


def test_push2his_five_day_rows_populate_real_sum(monkeypatch, tmp_path) -> None:
    # Given
    today = dt.date.today()
    values = [1.0, 0.0, -2.0, 3.0, 4.0]
    daily_rows = [
        {
            "date": (today - dt.timedelta(days=index)).isoformat(),
            "main_net_inflow": value,
        }
        for index, value in enumerate(values)
    ]
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        lambda *args, **kwargs: daily_rows,
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: pytest.fail("valid push2his must not load f164"),
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK9000"],
        today.isoformat(),
        days=5,
        eastmoney=_client(),
        settings=_settings(tmp_path),
    )

    # Then
    assert result.history_by_code["BK9000"] == daily_rows
    assert result.five_day_main_net_inflow_by_code == {"BK9000": 6.0}


def test_ths_market_bars_never_create_fund_flow_values(monkeypatch, tmp_path) -> None:
    # Given
    today = dt.date.today().isoformat()
    ths_rows = [
        {"date": today, "close": 100.0, "amount": 200.0, "pct_change": 1.0}
    ]
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        signals_b,
        "_fetch_ths_industry_kline",
        lambda *args, **kwargs: ths_rows,
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK1036"],
        today,
        days=5,
        eastmoney=_client(),
        settings=_settings(tmp_path),
    )

    # Then
    assert result.history_by_code["BK1036"] == ths_rows
    assert all("main_net_inflow" not in row for row in result.history_by_code["BK1036"])
    assert result.five_day_main_net_inflow_by_code == {}
    assert len(result.warnings) == 1
    assert "THS" in result.warnings[0]


def test_same_date_f164_cache_is_reused_without_upstream_call(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    today = dt.date.today().isoformat()
    SQLiteStructuredCache(tmp_path).write_general(
        _CACHE_KIND,
        _CACHE_SUB_KEY,
        today,
        {"values": {"BK9000": 0.0}},
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: pytest.fail("same-date cache must prevent an f164 call"),
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK9000"],
        today,
        days=5,
        eastmoney=_client(),
        settings=_settings(tmp_path),
    )

    # Then
    assert result.five_day_main_net_inflow_by_code == {"BK9000": 0.0}
    assert any("cache" in warning for warning in result.warnings)


def test_other_date_f164_cache_is_never_used_for_today(monkeypatch, tmp_path) -> None:
    # Given
    today = dt.date.today()
    SQLiteStructuredCache(tmp_path).write_general(
        _CACHE_KIND,
        _CACHE_SUB_KEY,
        (today - dt.timedelta(days=1)).isoformat(),
        {"values": {"BK9000": 99.0}},
    )
    bulk_calls: list[bool] = []
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: bulk_calls.append(True)
        or [
            {
                "code": "BK9000",
                "name": "今日值",
                "five_day_main_net_inflow": 7.0,
            }
        ],
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK9000"],
        today.isoformat(),
        days=5,
        eastmoney=_client(),
        settings=_settings(tmp_path),
    )

    # Then
    assert bulk_calls == [True]
    assert result.five_day_main_net_inflow_by_code == {"BK9000": 7.0}


def test_successful_f164_payload_is_cached_for_exact_target_date(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    today = dt.date.today().isoformat()
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: [
            {
                "code": "BK9000",
                "name": "行业",
                "five_day_main_net_inflow": 8.0,
            }
        ],
    )

    # When
    get_sector_fund_flow_history(
        ["BK9000"],
        today,
        days=5,
        eastmoney=_client(),
        settings=_settings(tmp_path),
    )

    # Then
    cached = SQLiteStructuredCache(tmp_path).read_general(
        _CACHE_KIND,
        _CACHE_SUB_KEY,
        today,
    )
    assert cached == {"values": {"BK9000": 8.0}}


def test_f164_cache_write_failure_keeps_result_and_emits_warning(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    today = dt.date.today().isoformat()
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: [
            {
                "code": "BK9000",
                "name": "行业",
                "five_day_main_net_inflow": 8.0,
            }
        ],
    )
    monkeypatch.setattr(
        SQLiteStructuredCache,
        "write_general",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            sqlite3.OperationalError("read-only cache")
        ),
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK9000"],
        today,
        days=5,
        eastmoney=_client(),
        settings=_settings(tmp_path),
    )

    # Then
    assert result.five_day_main_net_inflow_by_code == {"BK9000": 8.0}
    assert any("cache write" in warning for warning in result.warnings)


def test_all_fund_flow_sources_missing_emit_one_warning(monkeypatch, tmp_path) -> None:
    # Given
    today = dt.date.today().isoformat()
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: [],
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK9000"],
        today,
        days=5,
        eastmoney=_client(),
        settings=_settings(tmp_path),
    )

    # Then
    assert result.history_by_code["BK9000"] == []
    assert result.five_day_main_net_inflow_by_code == {}
    assert len(result.warnings) == 1
    assert "unavailable" in result.warnings[0]
