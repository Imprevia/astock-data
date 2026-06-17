"""Unit tests for the Typer-based ``astock-data`` CLI.

All tests are fully offline: the public facade (``astock_data.api``) is mocked
at the module reference the CLI imports, so no real network/vendor code runs.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from typer.testing import CliRunner

from astock_data import cli as cli_module
from astock_data.cli import app

pytestmark = pytest.mark.unit

runner = CliRunner()


def _fake_stock_data_result():
    """Build a minimal real StockDataResult so model_dump / formatters work."""

    from astock_data.models.base import Ticker
    from astock_data.models.market import OHLCVBar, StockDataResult

    return StockDataResult(
        source="tdx",
        retrieved_at="2026-05-12T10:00:00",
        ticker=Ticker(code="688017", market="sh"),
        bars=[
            OHLCVBar(date="2026-05-09", open=10.0, high=10.5, low=9.8, close=10.2, volume=100000),
        ],
    )


# ---------------------------------------------------------------------------
# help / structure
# ---------------------------------------------------------------------------
def test_help_exits_zero_and_lists_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = result.output
    for name in (
        "resolve",
        "kline",
        "indicator",
        "fundamentals",
        "balance-sheet",
        "cashflow",
        "income-statement",
        "news",
        "global-news",
        "shareholders",
        "profit-forecast",
        "hot-stocks",
        "northbound",
        "concepts",
        "fund-flow",
        "dragon-tiger",
        "lockup",
        "industry",
    ):
        assert name in out, f"missing subcommand in --help: {name}"


def test_eighteen_subcommands_registered():
    from typer.main import get_command

    cmds = get_command(app).commands
    assert len(cmds) == 18


def test_default_format_is_json():
    # The global option default is reflected by invoking a command without --format
    # and asserting the CLI surfaces json as the documented default.
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "json" in result.output


# ---------------------------------------------------------------------------
# json output (mocked facade)
# ---------------------------------------------------------------------------
def test_kline_json_output_is_parseable_and_has_ticker():
    """``--format json`` must produce machine-parseable JSON containing ticker.

    Mocks ``astock_data.cli.api.get_stock_data`` — the exact module-level
    reference the CLI's kline command invokes. No real network.
    """

    fake = _fake_stock_data_result()
    with mock.patch.object(cli_module.api, "get_stock_data", return_value=fake) as patched:
        result = runner.invoke(
            app,
            ["kline", "688017", "--start", "2026-05-01", "--end", "2026-05-12", "--format", "json"],
        )

    assert patched.called, "CLI did not call the mocked api.get_stock_data"
    args, _ = patched.call_args
    assert args[0] == "688017"
    assert args[1] == "2026-05-01"
    assert args[2] == "2026-05-12"

    assert patched.call_args.kwargs["period"] == "day"

    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.output)
    assert isinstance(payload, dict)
    assert payload["ticker"]["code"] == "688017"
    assert payload["bars"][0]["date"] == "2026-05-09"


def test_kline_default_format_is_json_without_flag():
    fake = _fake_stock_data_result()
    with mock.patch.object(cli_module.api, "get_stock_data", return_value=fake):
        result = runner.invoke(
            app,
            ["kline", "688017", "--start", "2026-05-01", "--end", "2026-05-12"],
        )
    assert result.exit_code == 0, result.stderr
    # Must still be valid JSON (default format == json).
    payload = json.loads(result.output)
    assert payload["ticker"]["code"] == "688017"


def test_kline_period_option_is_forwarded_to_facade():
    fake = _fake_stock_data_result()
    with mock.patch.object(cli_module.api, "get_stock_data", return_value=fake) as patched:
        result = runner.invoke(
            app,
            ["kline", "688017", "--start", "2026-05-01", "--end", "2026-05-12", "--period", "week"],
        )

    assert result.exit_code == 0, result.stderr
    assert patched.call_args.kwargs["period"] == "week"


# ---------------------------------------------------------------------------
# markdown output routes through the formatter
# ---------------------------------------------------------------------------
def test_kline_markdown_routes_through_formatter():
    fake = _fake_stock_data_result()
    with mock.patch.object(cli_module.api, "get_stock_data", return_value=fake), \
            mock.patch.object(
                cli_module.formatters,
                "to_markdown",
                return_value="## MARKDOWN RENDERED",
            ) as md_patch:
        result = runner.invoke(
            app,
            ["kline", "688017", "--start", "2026-05-01", "--end", "2026-05-12", "--format", "markdown"],
        )

    assert result.exit_code == 0, result.stderr
    md_patch.assert_called_once_with(fake)
    assert "MARKDOWN RENDERED" in result.output


def test_kline_text_routes_through_formatter():
    fake = _fake_stock_data_result()
    with mock.patch.object(cli_module.api, "get_stock_data", return_value=fake), \
            mock.patch.object(
                cli_module.formatters,
                "to_text",
                return_value="TEXT RENDERED",
            ) as txt_patch:
        result = runner.invoke(
            app,
            ["kline", "688017", "--start", "2026-05-01", "--end", "2026-05-12", "--format", "text"],
        )

    assert result.exit_code == 0, result.stderr
    txt_patch.assert_called_once_with(fake)
    assert "TEXT RENDERED" in result.output


# ---------------------------------------------------------------------------
# typed errors -> structured stderr, non-zero exit, no traceback
# ---------------------------------------------------------------------------
def test_invalid_ticker_emits_structured_error_and_nonzero_exit():
    """An ``InvalidTickerError`` must yield a structured stderr error, never a traceback."""

    from astock_data.errors import InvalidTickerError

    with mock.patch.object(
        cli_module.api,
        "get_stock_data",
        side_effect=InvalidTickerError("invalid ticker: ../x"),
    ):
        result = runner.invoke(
            app,
            ["kline", "../x", "--start", "2026-05-01", "--end", "2026-05-12", "--format", "json"],
        )

    assert result.exit_code != 0
    assert result.exit_code == 1
    err = result.stderr
    assert "Traceback" not in err, "raw Python traceback leaked to stderr"
    payload = json.loads(err.strip().splitlines()[-1])
    assert payload["error"]["type"] == "InvalidTickerError"
    assert "invalid ticker" in payload["error"]["message"]


def test_resolve_invalid_ticker_emits_structured_error():
    from astock_data.errors import InvalidTickerError

    with mock.patch.object(
        cli_module.api,
        "resolve_ticker",
        side_effect=InvalidTickerError("bad"),
    ):
        result = runner.invoke(app, ["resolve", "../evil", "--format", "json"])

    assert result.exit_code == 1
    assert "Traceback" not in result.stderr
    payload = json.loads(result.stderr.strip().splitlines()[-1])
    assert payload["error"]["type"] == "InvalidTickerError"


def test_resolve_valid_outputs_json():
    from astock_data.models.base import Ticker

    with mock.patch.object(cli_module.api, "resolve_ticker", return_value=Ticker(code="688017", market="sh")):
        result = runner.invoke(app, ["resolve", "688017", "--format", "json"])

    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.output)
    assert payload["code"] == "688017"
    assert payload["market"] == "sh"


def test_invalid_format_option_exits_nonzero():
    result = runner.invoke(app, ["--format", "yaml", "resolve", "688017"])
    assert result.exit_code != 0
    assert "error" in result.stderr


# ---------------------------------------------------------------------------
# routing coverage: each command calls the expected facade function
# ---------------------------------------------------------------------------
def test_each_command_routes_to_facade():
    """Smoke-test that every subcommand invokes its corresponding api function
    with the right argument names — fully mocked, no network."""

    from astock_data.models.base import Ticker

    ticker_result = Ticker(code="688017", market="sh")
    generic_result = _fake_stock_data_result()

    cases = [
        (["resolve", "688017"], "resolve_ticker", lambda m: m.return_value, ticker_result),
        (["kline", "688017", "--start", "2026-05-01", "--end", "2026-05-12"], "get_stock_data", lambda m: m.return_value, generic_result),
        (["indicator", "688017", "--indicator", "macd", "--curr-date", "2026-05-12", "--look-back-days", "30"], "get_indicators", lambda m: m.return_value, generic_result),
        (["fundamentals", "688017"], "get_fundamentals", lambda m: m.return_value, generic_result),
        (["balance-sheet", "688017", "--freq", "annual"], "get_balance_sheet", lambda m: m.return_value, generic_result),
        (["cashflow", "688017"], "get_cashflow", lambda m: m.return_value, generic_result),
        (["income-statement", "688017"], "get_income_statement", lambda m: m.return_value, generic_result),
        (["news", "688017", "--start", "2026-05-01", "--end", "2026-05-12"], "get_news", lambda m: m.return_value, generic_result),
        (["global-news", "--curr-date", "2026-05-12", "--limit", "5"], "get_global_news", lambda m: m.return_value, generic_result),
        (["shareholders", "688017"], "get_insider_transactions", lambda m: m.return_value, generic_result),
        (["profit-forecast", "688017"], "get_profit_forecast", lambda m: m.return_value, generic_result),
        (["hot-stocks", "--date", "2026-05-12"], "get_hot_stocks", lambda m: m.return_value, generic_result),
        (["northbound", "--curr-date", "2026-05-12"], "get_northbound_flow", lambda m: m.return_value, generic_result),
        (["concepts", "688017"], "get_concept_blocks", lambda m: m.return_value, generic_result),
        (["fund-flow", "688017", "--curr-date", "2026-05-12"], "get_fund_flow", lambda m: m.return_value, generic_result),
        (["dragon-tiger", "688017", "--trade-date", "2026-05-12"], "get_dragon_tiger_board", lambda m: m.return_value, generic_result),
        (["lockup", "688017", "--trade-date", "2026-05-12"], "get_lockup_expiry", lambda m: m.return_value, generic_result),
        (["industry", "688017", "--trade-date", "2026-05-12"], "get_industry_comparison", lambda m: m.return_value, generic_result),
    ]

    for argv, fn_name, _resolver, fake in cases:
        with mock.patch.object(cli_module.api, fn_name, return_value=fake) as patched:
            result = runner.invoke(app, argv)
        assert patched.called, f"{fn_name} not called for {argv}"
        assert result.exit_code == 0, f"{argv} failed: {result.stderr or result.output}"
