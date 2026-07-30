from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from astock_data import cli as cli_module
from astock_data.cli import app
from astock_data.models.signals import SectorFundFlowHistoryResult

pytestmark = pytest.mark.unit

runner = CliRunner()


def test_sector_history_result_defaults_five_day_aggregate_to_empty_mapping() -> None:
    # Given / When
    result = SectorFundFlowHistoryResult(
        date="2026-07-29",
        days=5,
        history_by_code={"BK1036": []},
    )

    # Then
    assert result.history_by_code == {"BK1036": []}
    assert result.five_day_main_net_inflow_by_code == {}


def test_sector_history_public_json_separates_daily_history_and_aggregate() -> None:
    # Given
    daily_rows = [{"date": "2026-07-29", "main_net_inflow": 1.0}]
    result = SectorFundFlowHistoryResult(
        date="2026-07-29",
        days=5,
        history_by_code={"BK1036": daily_rows, "BK1037": []},
        five_day_main_net_inflow_by_code={"BK1036": 1.0, "BK1037": 0.0},
        warnings=["BK1037: five-day aggregate only; daily history unavailable."],
    )

    # When
    payload = json.loads(result.model_dump_json())

    # Then
    assert payload["history_by_code"] == {
        "BK1036": daily_rows,
        "BK1037": [],
    }
    assert payload["five_day_main_net_inflow_by_code"] == {
        "BK1036": 1.0,
        "BK1037": 0.0,
    }
    assert payload["warnings"] == [
        "BK1037: five-day aggregate only; daily history unavailable."
    ]


def test_cli_serializes_sector_history_partial_result(monkeypatch) -> None:
    # Given
    result = SectorFundFlowHistoryResult(
        date="2026-07-29",
        days=5,
        history_by_code={"BK1037": []},
        five_day_main_net_inflow_by_code={"BK1037": 0.0},
        warnings=["BK1037: f164 aggregate only."],
    )
    monkeypatch.setattr(
        cli_module.api,
        "get_sector_fund_flow_history",
        lambda *args, **kwargs: result,
    )

    # When
    invocation = runner.invoke(
        app,
        ["sector-fund-flow-history", "BK1037", "--format", "json"],
    )

    # Then
    assert invocation.exit_code == 0, invocation.stderr or invocation.output
    assert json.loads(invocation.output) == result.model_dump(mode="json")


def test_mcp_serializes_sector_history_partial_result(monkeypatch) -> None:
    # Given
    result = SectorFundFlowHistoryResult(
        date="2026-07-29",
        days=5,
        history_by_code={"BK1037": []},
        five_day_main_net_inflow_by_code={"BK1037": 0.0},
        warnings=["BK1037: f164 aggregate only."],
    )
    monkeypatch.setattr(
        "astock_data.api.get_sector_fund_flow_history",
        lambda *args, **kwargs: result,
    )
    from astock_data.mcp import server

    # When
    payload = server.get_sector_fund_flow_history(["BK1037"], "2026-07-29", 5)

    # Then
    assert payload == result.model_dump(mode="json")
