"""MCP server for ``astock-data`` — exposes the 26 public API functions as tools.

Uses the official FastMCP Python SDK (`from fastmcp import FastMCP`) over the
default stdio transport. Each tool is a thin adapter around the public facade
:mod:`astock_data.api`:

* success → JSON-serializable dict via ``model_dump(mode="json")``
* typed error (any :class:`~astock_data.errors.AStockDataError` subclass) →
  structured payload ``{"error": {"type": ..., "message": ...}}`` — stack
  traces are never leaked to the MCP client.

Only the *user-facing* parameters of each public function are exposed as the
MCP input schema. Internal dependency-injection kwargs (``settings``,
``cache``, ``tdx``, ``sina``, ``eastmoney``, ``cls_session``, ``ths_session``,
``tencent``) are intentionally hidden — they are composition hooks for tests,
not part of the LLM-facing contract.

Run directly (defaults to stdio)::

    python -m astock_data.mcp.server
"""

from __future__ import annotations

import re
from typing import Any, Final

from fastmcp import FastMCP

import astock_data.api as api
from astock_data.errors import AStockDataError, MarketValidationError

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP("astock-data")

_MAX_CODES: Final = 50
_MAX_DAYS: Final = 365
_MAX_ORDER_BOOK_SAMPLES: Final = 60
_MAX_ORDER_BOOK_INTERVAL_SECONDS: Final = 60.0
_MAX_ORDER_BOOK_WAIT_SECONDS: Final = 300.0
_ETF_CODE_PATTERN: Final = re.compile(r"\d{6}")
_SECTOR_CODE_PATTERN: Final = re.compile(r"BK\d{4}")


# ---------------------------------------------------------------------------
# Serialization / error helpers
# ---------------------------------------------------------------------------


def _serialize(result: Any) -> dict[str, Any]:
    """Convert a public-API return value into a JSON-serializable dict.

    Every public function returns a Pydantic ``BaseModel`` (incl. ``Ticker``),
    so ``model_dump(mode="json")`` is the canonical path. Anything that is
    already a plain mapping is returned untouched as a defensive fallback.
    """
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if isinstance(result, dict):
        return result
    # Last resort — let json handle primitives, wrap everything else.
    return {"value": result}


def _error_payload(err: AStockDataError) -> dict[str, dict[str, str]]:
    """Build a structured MCP error payload from a typed error.

    Never exposes ``str(exc)`` internals beyond the error message; the
    traceback is deliberately dropped.
    """
    return {
        "error": {
            "type": type(err).__name__,
            "message": str(err),
        }
    }


def _parse_days(days: int) -> int:
    if 1 <= days <= _MAX_DAYS:
        return days
    raise MarketValidationError(f"days must be between 1 and {_MAX_DAYS}")


def _parse_codes(
    codes: list[str], pattern: re.Pattern[str], code_type: str
) -> list[str]:
    if not codes:
        raise MarketValidationError("codes must not be empty")
    if len(codes) > _MAX_CODES:
        raise MarketValidationError(f"codes must contain at most {_MAX_CODES} items")
    invalid_code = next(
        (code for code in codes if pattern.fullmatch(code) is None),
        None,
    )
    if invalid_code is not None:
        raise MarketValidationError(f"invalid {code_type} code: {invalid_code!r}")
    return list(dict.fromkeys(codes))


def _parse_order_book_sampling(
    samples: int,
    interval_seconds: float,
) -> tuple[int, float]:
    if (
        isinstance(samples, bool)
        or not isinstance(samples, int)
        or not 1 <= samples <= _MAX_ORDER_BOOK_SAMPLES
    ):
        raise MarketValidationError(
            f"samples must be between 1 and {_MAX_ORDER_BOOK_SAMPLES}"
        )
    if (
        isinstance(interval_seconds, bool)
        or not isinstance(interval_seconds, (int, float))
        or not 1 <= interval_seconds <= _MAX_ORDER_BOOK_INTERVAL_SECONDS
    ):
        raise MarketValidationError(
            "interval_seconds must be between 1 and "
            f"{_MAX_ORDER_BOOK_INTERVAL_SECONDS:g}"
        )
    planned_wait = (samples - 1) * float(interval_seconds)
    if planned_wait > _MAX_ORDER_BOOK_WAIT_SECONDS:
        raise MarketValidationError(
            "planned order-book sampling wait must not exceed "
            f"{_MAX_ORDER_BOOK_WAIT_SECONDS:g} seconds"
        )
    return samples, float(interval_seconds)


# ---------------------------------------------------------------------------
# Tools — 1:1 with the 26 public API functions
# ---------------------------------------------------------------------------


@mcp.tool()
def resolve_ticker(user_input: str) -> dict[str, Any]:
    """Resolve a ticker symbol or Chinese stock name into a normalized Ticker.

    Accepts bare 6-digit codes (e.g. ``688017``), exchange-prefixed forms
    (``SH688017`` / ``688017.SH``), or a Chinese stock name. Returns the
    normalized ``Ticker`` (code + market).
    """
    try:
        return _serialize(api.resolve_ticker(user_input))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_stock_data(
    symbol: str, start_date: str, end_date: str, period: str = "day"
) -> dict[str, Any]:
    """Fetch OHLCV K-line bars for an A-share between two dates.

    Parameters
    ----------
    symbol:
        Ticker symbol or Chinese stock name (resolved internally).
    start_date, end_date:
        Inclusive date range as ``YYYY-MM-DD`` strings.
    period:
        K-line period: day, week, month, 1min, 5min, 15min, 30min, or 60min.
    """
    try:
        return _serialize(api.get_stock_data(symbol, start_date, end_date, period=period))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_indicators(
    symbol: str, indicator: str, curr_date: str, look_back_days: int
) -> dict[str, Any]:
    """Compute a single technical indicator series ending at ``curr_date``.

    Supported indicators include ``close_50_sma``, ``close_200_sma``,
    ``close_10_ema``, ``macd``, ``macds``, ``macdh``, ``rsi``, ``boll``,
    ``boll_ub``, ``boll_lb``, ``atr``, ``vwma``, ``mfi``.
    """
    try:
        return _serialize(
            api.get_indicators(symbol, indicator, curr_date, look_back_days)
        )
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_market_breadth(date: str = "", fast: bool = False) -> dict[str, Any]:
    """Fetch market breadth: fixed index snapshots, limit counts, and board ladders."""
    try:
        return _serialize(api.get_market_breadth(date, fast=fast))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_fundamentals(
    ticker: str, curr_date: str | None = None
) -> dict[str, Any]:
    """Fetch a fundamentals composite snapshot (quote + snapshot + consensus).

    Combines the live Tencent quote, a mootdx financial snapshot, Eastmoney
    stock info and an optional THS EPS consensus forecast.
    """
    try:
        return _serialize(api.get_fundamentals(ticker, curr_date))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_balance_sheet(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None
) -> dict[str, Any]:
    """Fetch the balance-sheet financial statement (Sina source).

    ``freq`` selects the reporting frequency. Reports dated after
    ``curr_date`` are filtered out.
    """
    try:
        return _serialize(api.get_balance_sheet(ticker, freq, curr_date))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_cashflow(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None
) -> dict[str, Any]:
    """Fetch the cash-flow financial statement (Sina source)."""
    try:
        return _serialize(api.get_cashflow(ticker, freq, curr_date))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_income_statement(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None
) -> dict[str, Any]:
    """Fetch the income-statement financial statement (Sina source)."""
    try:
        return _serialize(api.get_income_statement(ticker, freq, curr_date))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_news(
    ticker: str, start_date: str, end_date: str
) -> dict[str, Any]:
    """Fetch stock-specific news for an A-share between two inclusive dates.

    Eastmoney is the primary source; Sina is the fallback.
    """
    try:
        return _serialize(api.get_news(ticker, start_date, end_date))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_global_news(
    curr_date: str, look_back_days: int = 7, limit: int = 10
) -> dict[str, Any]:
    """Fetch global market news (CLS + Eastmoney fast-news), deduped + limited."""
    try:
        return _serialize(
            api.get_global_news(curr_date, look_back_days, limit)
        )
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_insider_transactions(ticker: str) -> dict[str, Any]:
    """Fetch major-shareholder / insider transactions from mootdx F10."""
    try:
        return _serialize(api.get_insider_transactions(ticker))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_profit_forecast(
    ticker: str, curr_date: str | None = None
) -> dict[str, Any]:
    """Fetch the analyst EPS profit forecast (THS consensus) + forward PE/PEG."""
    try:
        return _serialize(api.get_profit_forecast(ticker, curr_date))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_hot_stocks(curr_date: str = "") -> dict[str, Any]:
    """Fetch the day's limit-up (harden) hot stocks and aggregate theme tags."""
    try:
        return _serialize(api.get_hot_stocks(curr_date))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_northbound_flow(
    curr_date: str, include_history: bool = False
) -> dict[str, Any]:
    """Fetch northbound (HK Stock Connect) capital flow signal for a date."""
    try:
        return _serialize(
            api.get_northbound_flow(curr_date, include_history)
        )
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_concept_blocks(ticker: str) -> dict[str, Any]:
    """Fetch the concept/theme block memberships for an A-share."""
    try:
        return _serialize(api.get_concept_blocks(ticker))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_fund_flow(
    ticker: str, curr_date: str, include_history: bool = True
) -> dict[str, Any]:
    """Fetch intraday / daily main-capital fund flow for an A-share."""
    try:
        return _serialize(
            api.get_fund_flow(ticker, curr_date, include_history)
        )
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_dragon_tiger_board(
    ticker: str, trade_date: str, look_back_days: int = 30
) -> dict[str, Any]:
    """Fetch the dragon-tiger (龙虎榜) board seats for an A-share."""
    try:
        return _serialize(
            api.get_dragon_tiger_board(ticker, trade_date, look_back_days)
        )
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_lockup_expiry(
    ticker: str, trade_date: str, forward_days: int = 90
) -> dict[str, Any]:
    """Fetch upcoming share-lockup (限售解禁) expiries for an A-share."""
    try:
        return _serialize(
            api.get_lockup_expiry(ticker, trade_date, forward_days)
        )
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_industry_comparison(
    ticker: str, trade_date: str, top_n: int = 20
) -> dict[str, Any]:
    """Fetch the industry peer comparison (top-N) for an A-share."""
    try:
        return _serialize(
            api.get_industry_comparison(ticker, trade_date, top_n)
        )
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_index_kline(key: str, days: int = 10) -> dict[str, Any]:
    """Fetch index K-line bars for a key (sh/szci/cyb/hs300)."""
    try:
        return _serialize(api.get_index_kline(key, _parse_days(days)))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_stock_amount(ticker: str, days: int = 10) -> dict[str, Any]:
    """Fetch recent daily amount (成交额) series for an A-share."""
    try:
        return _serialize(api.get_stock_amount(ticker, _parse_days(days)))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_order_book(
    ticker: str,
    samples: int = 1,
    interval_seconds: float = 1.0,
) -> dict[str, Any]:
    """Fetch bounded Tencent five-level snapshots and visible-depth changes."""
    try:
        parsed_samples, parsed_interval = _parse_order_book_sampling(
            samples,
            interval_seconds,
        )
        return _serialize(
            api.get_order_book(ticker, parsed_samples, parsed_interval)
        )
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_etf_daily(codes: list[str], days: int = 10) -> dict[str, Any]:
    """Fetch recent daily K-line for a set of ETF codes."""
    try:
        parsed_codes = _parse_codes(codes, _ETF_CODE_PATTERN, "ETF")
        return _serialize(api.get_etf_daily(parsed_codes, _parse_days(days)))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_sector_fund_flow(
    curr_date: str = "", days: int = 5
) -> dict[str, Any]:
    """Fetch industry sector fund-flow ranking + recent history."""
    try:
        return _serialize(api.get_sector_fund_flow(curr_date, _parse_days(days)))
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_sector_fund_flow_history(
    codes: list[str], curr_date: str = "", days: int = 5
) -> dict[str, Any]:
    """Fetch multi-sector recent daily main fund-flow history."""
    try:
        parsed_codes = _parse_codes(codes, _SECTOR_CODE_PATTERN, "sector")
        return _serialize(
            api.get_sector_fund_flow_history(
                parsed_codes,
                curr_date,
                _parse_days(days),
            )
        )
    except AStockDataError as exc:
        return _error_payload(exc)


@mcp.tool()
def get_sector_strength(curr_date: str = "") -> dict[str, Any]:
    """Fetch 6-dimension industry sector strength ranking."""
    try:
        return _serialize(api.get_sector_strength(curr_date))
    except AStockDataError as exc:
        return _error_payload(exc)


# ---------------------------------------------------------------------------
# Entrypoint — stdio transport is FastMCP's default
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
