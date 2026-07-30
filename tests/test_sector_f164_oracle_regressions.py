from __future__ import annotations

import datetime as dt

import pytest

from astock_data.clients import eastmoney as eastmoney_module
from astock_data.clients.eastmoney import EastmoneyClient
from astock_data.config import AStockSettings
from astock_data.errors import DataSourceError
from astock_data.services import signals_b
from astock_data.services.signals_b import get_sector_fund_flow_history

pytestmark = pytest.mark.unit


def _client() -> EastmoneyClient:
    return EastmoneyClient(min_interval=0.0, timeout=5.0)


def test_invalid_push2his_rows_trigger_f164_without_claiming_daily_source(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    today = dt.date.today().isoformat()
    invalid_rows = [
        {"date": today, "main_net_inflow": None},
        {"date": today, "main_net_inflow": "invalid"},
        {"date": today, "main_net_inflow": True},
    ]
    bulk_calls: list[bool] = []
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        lambda *args, **kwargs: invalid_rows,
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: bulk_calls.append(True)
        or [
            {
                "code": "BK9000",
                "name": "行业",
                "five_day_main_net_inflow": 12.0,
            }
        ],
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK9000"],
        today,
        days=5,
        eastmoney=_client(),
        settings=AStockSettings(cache_dir=tmp_path),
    )

    # Then
    assert bulk_calls == [True]
    assert result.history_by_code["BK9000"] == []
    assert result.five_day_main_net_inflow_by_code == {"BK9000": 12.0}
    assert not any(warning.startswith("push2his daily") for warning in result.warnings)
    assert sum(warning.startswith("BK9000:") for warning in result.warnings) == 1


def test_current_five_day_error_still_attempts_later_push2his_sector(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    today = dt.date.today().isoformat()
    requested_secids: list[str] = []
    valid_rows = [{"date": today, "main_net_inflow": 5.0}]
    real_executor = signals_b.ThreadPoolExecutor

    def fetch_history(secid, **kwargs):
        requested_secids.append(secid)
        if secid == "90.bk9000":
            raise DataSourceError("first sector unavailable")
        return valid_rows

    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        fetch_history,
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: [
            {
                "code": "BK9000",
                "name": "首板块",
                "five_day_main_net_inflow": 11.0,
            },
            {
                "code": "BK9001",
                "name": "后续板块",
                "five_day_main_net_inflow": 99.0,
            },
        ],
    )
    monkeypatch.setattr(
        signals_b,
        "ThreadPoolExecutor",
        lambda max_workers: real_executor(max_workers=1),
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK9000", "BK9001"],
        today,
        days=5,
        eastmoney=_client(),
        settings=AStockSettings(cache_dir=tmp_path),
    )

    # Then
    assert requested_secids == ["90.bk9000", "90.bk9001"]
    assert result.history_by_code == {"BK9000": [], "BK9001": valid_rows}
    assert result.five_day_main_net_inflow_by_code == {
        "BK9000": 11.0,
        "BK9001": 5.0,
    }
    assert "push2his daily fund-flow history used for 1 sectors." in result.warnings
    assert sum(warning.startswith("BK9000:") for warning in result.warnings) == 1
    assert not any(warning.startswith("BK9001:") for warning in result.warnings)


def test_past_date_error_preserves_fail_fast_for_later_sectors(
    monkeypatch,
    tmp_path,
) -> None:
    # Given
    past_date = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    requested_secids: list[str] = []
    real_executor = signals_b.ThreadPoolExecutor

    def fetch_history(secid, **kwargs):
        requested_secids.append(secid)
        if secid == "90.bk9000":
            raise DataSourceError("first sector unavailable")
        return [{"date": past_date, "main_net_inflow": 5.0}]

    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_fund_flow_history",
        fetch_history,
    )
    monkeypatch.setattr(
        eastmoney_module,
        "fetch_sector_five_day_main_net_inflow",
        lambda **kwargs: pytest.fail("historical request must not load f164"),
    )
    monkeypatch.setattr(
        signals_b,
        "ThreadPoolExecutor",
        lambda max_workers: real_executor(max_workers=1),
    )

    # When
    result = get_sector_fund_flow_history(
        ["BK9000", "BK9001"],
        past_date,
        days=5,
        eastmoney=_client(),
        settings=AStockSettings(cache_dir=tmp_path),
    )

    # Then
    assert requested_secids == ["90.bk9000"]
    assert result.history_by_code == {"BK9000": [], "BK9001": []}
