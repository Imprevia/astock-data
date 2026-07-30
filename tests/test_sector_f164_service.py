from __future__ import annotations

import datetime as dt

import pytest

from astock_data.clients import eastmoney as eastmoney_module
from astock_data.clients.eastmoney import EastmoneyClient
from astock_data.config import AStockSettings
from astock_data.services import signals_b
from astock_data.services.signals_b import get_sector_fund_flow_history

pytestmark = pytest.mark.unit


def _client() -> EastmoneyClient:
    return EastmoneyClient(min_interval=0.0, timeout=5.0)


def test_current_five_day_missing_history_loads_one_shared_bulk_fallback(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
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
                "name": "精确命中",
                "five_day_main_net_inflow": 0.0,
            },
            {
                "code": "BK9002",
                "name": "未请求板块",
                "five_day_main_net_inflow": 9.0,
            },
        ],
        raising=False,
    )
    monkeypatch.setattr(signals_b, "_fetch_ths_industry_kline", lambda *args, **kwargs: [])

    # When
    result = get_sector_fund_flow_history(
        ["BK9000", "BK9001"],
        dt.date.today().isoformat(),
        days=5,
        eastmoney=_client(),
        settings=AStockSettings(cache_dir=tmp_path),
    )

    # Then
    assert bulk_calls == [True]
    assert result.history_by_code == {"BK9000": [], "BK9001": []}
    assert result.five_day_main_net_inflow_by_code == {"BK9000": 0.0}
    assert len(result.warnings) == 2
    assert sum(warning.startswith("BK9000:") for warning in result.warnings) == 1
    assert sum(warning.startswith("BK9001:") for warning in result.warnings) == 1


def test_complete_push2his_history_does_not_load_bulk_fallback(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    daily_rows = [
        {"date": dt.date.today().isoformat(), "main_net_inflow": 1.0},
    ]
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        lambda *args, **kwargs: daily_rows,
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: pytest.fail("complete push2his must not load f164"),
        raising=False,
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK9000"],
        dt.date.today().isoformat(),
        days=5,
        eastmoney=_client(),
        settings=AStockSettings(cache_dir=tmp_path),
    )

    # Then
    assert result.history_by_code["BK9000"] == daily_rows


def test_non_five_day_request_does_not_load_bulk_fallback(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: pytest.fail("non-five-day request must not load f164"),
        raising=False,
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK9000"],
        dt.date.today().isoformat(),
        days=3,
        eastmoney=_client(),
        settings=AStockSettings(cache_dir=tmp_path),
    )

    # Then
    assert result.days == 3


def test_past_target_date_does_not_load_bulk_fallback(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    past_date = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: pytest.fail("historical request must not load f164"),
        raising=False,
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK9000"],
        past_date,
        days=5,
        eastmoney=_client(),
        settings=AStockSettings(cache_dir=tmp_path),
    )

    # Then
    assert result.date == past_date

