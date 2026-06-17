"""Live smoke tests — opt-in only.

These tests MAY call real third-party APIs (mootdx TCP, Tencent/Sina/Eastmoney
HTTP). They are marked ``@pytest.mark.live`` and the project ``conftest.py``
auto-skips every ``live`` item unless the environment variable
``ASTOCK_LIVE_TESTS=1`` is set. So the default ``python -m pytest`` run hits
NO real network.

Run them explicitly::

    $env:ASTOCK_LIVE_TESTS='1'
    python -m pytest tests/live -q

Design notes
------------
* Dates are computed relative to ``today`` (never hardcoded) so the smoke
  window always overlaps recent trading days.
* Calls are intentionally SEQUENTIAL — each test issues the minimum number of
  vendor calls and respects the Eastmoney throttle (default 1s + jitter built
  into ``EastmoneyClient``). No parallel fan-out.
* A vendor/network failure surfaces as a test failure when live tests are
  opted-in — that is expected and acceptable; the deliverable is the correct
  skip-guard scaffolding, not a guarantee that every upstream is reachable.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import subprocess
import sys

import pytest

# Module-level marker: every test in this module is a live test and is
# auto-skipped by ``conftest.pytest_collection_modifyitems`` unless
# ``ASTOCK_LIVE_TESTS=1`` is set.
pytestmark = pytest.mark.live

# A liquid, well-known 科创板 ticker (绿的谐波) used as the smoke fixture.
TICKER = "688017"
TICKER_NAME = "绿的谐波"


def _recent_window(days: int = 14) -> tuple[str, str]:
    """Return ``(start, end)`` ISO dates covering the last ``days`` calendar days.

    Uses calendar days (not trading days) so the window reliably spans several
    A-share trading sessions regardless of where weekends/holidays fall.
    """

    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    return start.isoformat(), today.isoformat()


def test_resolver_live() -> None:
    """resolve_ticker returns a Ticker for both a bare code and a Chinese name.

    The Chinese-name path exercises the lazy live mootdx name map build.
    """

    from astock_data.api import resolve_ticker
    from astock_data.models.base import Ticker

    by_code = resolve_ticker(TICKER)
    assert isinstance(by_code, Ticker)
    assert by_code.code == TICKER

    # Chinese-name resolution goes through the live mootdx name map. If the
    # upstream map is unreachable this raises a typed AStockDataError — which
    # is an acceptable live failure, surfaced as a test error.
    by_name = resolve_ticker(TICKER_NAME)
    assert isinstance(by_name, Ticker)
    assert by_name.code == TICKER


def test_kline_live() -> None:
    """get_stock_data returns structured OHLCV bars from a recent window."""

    from astock_data.api import get_stock_data
    from astock_data.models.market import StockDataResult

    start, end = _recent_window(days=14)
    result = get_stock_data(TICKER, start, end)
    assert isinstance(result, StockDataResult)
    assert result.source in {"mootdx", "sina", "cache"}
    assert result.retrieved_at is not None
    assert len(result.bars) >= 1, "expected at least one OHLCV bar in the window"
    bar = result.bars[0]
    assert bar.date is not None
    assert bar.close > 0


def test_fundamentals_live() -> None:
    """get_fundamentals returns a composite result with source + retrieved_at."""

    from astock_data.api import get_fundamentals
    from astock_data.models.fundamentals import FundamentalsResult

    result = get_fundamentals(TICKER)
    assert isinstance(result, FundamentalsResult)
    assert result.source
    assert result.retrieved_at is not None


def test_fund_flow_live() -> None:
    """get_fund_flow returns structured intraday minute rows from Eastmoney push2."""

    from astock_data.api import get_fund_flow
    from astock_data.models.signals import FundFlowResult

    today_iso = dt.date.today().isoformat()
    # include_history=False keeps this to a single push2 minute call.
    result = get_fund_flow(TICKER, today_iso, include_history=False)
    assert isinstance(result, FundFlowResult)
    assert result.source
    assert result.retrieved_at is not None
    # Minute rows are intraday; on a non-trading day this may legitimately be
    # empty, so we only assert the structured shape, not a minimum row count.
    assert isinstance(result.minute, list)


def test_concept_blocks_live() -> None:
    """get_concept_blocks resolves via Eastmoney — NO Baidu PAE call.

    Pins the v0.2.7 migration: the source field must indicate eastmoney, never
    the retired Baidu PAE / gushitong endpoints.
    """

    from astock_data.api import get_concept_blocks
    from astock_data.models.signals import ConceptBlocksResult

    result = get_concept_blocks(TICKER)
    assert isinstance(result, ConceptBlocksResult)
    assert "eastmoney" in result.source.lower(), (
        f"concept blocks must come from eastmoney, got source={result.source!r}"
    )
    assert "baidu" not in result.source.lower()
    assert result.retrieved_at is not None


def test_cli_json_live() -> None:
    """The kline CLI subcommand exits 0 and emits JSON containing a ticker."""

    start, end = _recent_window(days=14)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "astock_data.cli",
            "kline",
            TICKER,
            "--start",
            start,
            "--end",
            end,
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"CLI exited {proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    payload = json.loads(proc.stdout)
    assert "ticker" in payload
    # Ticker is serialized as {code, market, ...}; the resolved code must match.
    ticker_field = payload["ticker"]
    assert isinstance(ticker_field, dict)
    assert ticker_field.get("code") == TICKER


def test_mcp_tools_registered_live() -> None:
    """The MCP server registers exactly 18 tools.

    ``mcp.list_tools()`` is async; ``asyncio.run`` drives it synchronously
    (the project pytest config has no asyncio_mode, so async-def tests are
    unavailable). Importing the server module does NOT start the stdio server
    (that only happens under ``__main__``), so this is safe to call.
    """

    from astock_data.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    assert len(names) == 18, f"expected 18 MCP tools, got {len(names)}: {sorted(names)}"
