"""Typer-based command-line interface for ``astock-data``.

Exposes one subcommand per public facade function (18 in total) plus a
``--format json|markdown|text`` (default ``json``) and ``--no-cache`` option.

``--format`` / ``--no-cache`` may be passed either before or after the
subcommand name (each command also accepts them), matching the documented
invocation style ``astock-data kline 688017 --start ... --format json``.

All commands route exclusively through :mod:`astock_data.api` (the public
facade) and :mod:`astock_data.formatters` (output rendering) — no service
logic is duplicated here. Typed :mod:`astock_data.errors` exceptions are
caught and emitted as a structured JSON error object on stderr with a
non-zero exit code, never a raw Python traceback.

Example
-------
    astock-data kline 688017 --start 2026-05-01 --end 2026-05-12 --format json
    astock-data fundamentals 688017 --format markdown
    astock-data resolve 688017
"""

from __future__ import annotations

import json as _json
import os
import tempfile
from typing import Optional

import typer

from . import api, errors, formatters

# Global option storage. Populated by the :func:`callback` (options before the
# subcommand) and/or by each command's trailing ``--format``/``--no-cache``
# options. Either placement wins; the last value seen takes effect.
_FORMAT: str = "json"
_NO_CACHE: bool = False


def _apply_global_options(*, format: Optional[str], no_cache: Optional[bool]) -> None:
    """Validate and stash the active ``--format`` / ``--no-cache``."""

    global _FORMAT, _NO_CACHE
    if format is not None:
        if format not in ("json", "markdown", "text"):
            typer.echo(
                _json.dumps(
                    {"error": {"type": "InvalidOption", "message": f"unknown format: {format!r}"}},
                    ensure_ascii=False,
                ),
                err=True,
            )
            raise typer.Exit(code=2)
        _FORMAT = format
    if no_cache:
        _NO_CACHE = True


# Reusable per-command option defaults. Each command carries ``format`` /
# ``no_cache`` as trailing parameters so users may place these flags after the
# subcommand name (Typer resolves the OptionInfo markers at parse time).
_FORMAT_OPT = typer.Option(
    None,
    "--format",
    "-f",
    help="Output format: json (default), markdown, or text.",
)
_NO_CACHE_OPT = typer.Option(
    None,
    "--no-cache",
    help="Bypass the on-disk cache for this invocation.",
)
_PERIOD_OPT = typer.Option(
    "day",
    "--period",
    help="K-line period: day, week, month, 1min, 5min, 15min, 30min, or 60min.",
)


def callback(
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: json (default), markdown, or text.",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Bypass the on-disk cache for this invocation.",
    ),
) -> None:
    """astock-data — A-share structured market data, fundamentals, news and signal CLI."""

    _apply_global_options(format=format, no_cache=no_cache)


app = typer.Typer(
    name="astock-data",
    help="A-share structured market data, fundamentals, news and signal CLI.",
    no_args_is_help=True,
    callback=callback,
)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def _disable_cache() -> None:
    """Bypass the persistent cache for this process invocation.

    The service layer builds its caches lazily from ``get_settings().cache_dir``.
    Redirecting ``ASTOCK_CACHE_DIR`` to a disposable temp directory (and clearing
    the settings lru_cache) guarantees no stale reads and no writes to the user's
    real cache, without touching other tasks' source files.
    """

    if not _NO_CACHE:
        return
    tmp = tempfile.mkdtemp(prefix="astock-nocache-")
    os.environ["ASTOCK_CACHE_DIR"] = tmp
    try:
        from .config import get_settings

        get_settings.cache_clear()
    except Exception:
        pass


def _emit(result: object) -> None:
    """Render ``result`` to stdout according to the active ``--format``."""

    fmt = _FORMAT
    if fmt == "json":
        payload = result.model_dump(mode="json")
        typer.echo(_json.dumps(payload, ensure_ascii=False, indent=2))
    elif fmt == "markdown":
        typer.echo(formatters.to_markdown(result))
    else:  # text
        typer.echo(formatters.to_text(result))


def _run(call: object) -> None:
    """Invoke a zero-arg callable, emit its result, or emit a structured error.

    Catches the typed :mod:`astock_data.errors` taxonomy (never bare
    ``Exception`` for business failures) and prints a machine-parseable
    ``{"error": {"type", "message"}}`` object to stderr before exiting non-zero.
    """

    try:
        result = call()
    except errors.AStockDataError as exc:
        payload = {"error": {"type": type(exc).__name__, "message": str(exc)}}
        typer.echo(_json.dumps(payload, ensure_ascii=False), err=True)
        raise typer.Exit(code=1)
    _emit(result)


def _fresh_settings():
    """Return settings freshly reloaded after an env override."""

    from .config import get_settings

    get_settings.cache_clear()
    return get_settings()


def _kline_cache():
    """Return a fresh empty CsvKlineCache backed by the (possibly temp) cache dir."""

    import pathlib

    from .cache import CsvKlineCache

    return CsvKlineCache(base_dir=pathlib.Path(_fresh_settings().cache_dir))


# ---------------------------------------------------------------------------
# resolver
# ---------------------------------------------------------------------------
@app.command(help="Resolve a ticker/code/Chinese name to a canonical Ticker.")
def resolve(
    ticker: str = typer.Argument(..., help="6-digit code, prefixed/suffixed code, or Chinese stock name."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """Resolve a ticker via the shared safety boundary."""

    _apply_global_options(format=format, no_cache=no_cache)
    _run(lambda: api.resolve_ticker(ticker))


# ---------------------------------------------------------------------------
# market_data
# ---------------------------------------------------------------------------
@app.command(help="Fetch OHLCV K-line data for a date range.")
def kline(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    start: str = typer.Option(..., "--start", help="Start date YYYY-MM-DD (inclusive)."),
    end: str = typer.Option(..., "--end", help="End date YYYY-MM-DD (inclusive)."),
    period: str = _PERIOD_OPT,
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_stock_data"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()

    def _call():
        if _NO_CACHE:
            return api.get_stock_data(
                symbol,
                start,
                end,
                period=period,
                cache=_kline_cache(),
                settings=_fresh_settings(),
            )
        return api.get_stock_data(symbol, start, end, period=period)

    _run(_call)


@app.command(help="Compute a technical indicator series for a symbol.")
def indicator(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    indicator: str = typer.Option(..., "--indicator", help="Indicator name e.g. macd, rsi, close_50_sma."),
    curr_date: str = typer.Option(..., "--curr-date", help="Reference date YYYY-MM-DD."),
    look_back_days: int = typer.Option(..., "--look-back-days", help="Number of trading days to include."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_indicators"""

    _apply_global_options(format=format, no_cache=no_cache)
    _run(lambda: api.get_indicators(symbol, indicator, curr_date, look_back_days))


# ---------------------------------------------------------------------------
# fundamentals
# ---------------------------------------------------------------------------
@app.command(help="Fetch composite fundamentals snapshot for a symbol.")
def fundamentals(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_fundamentals"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()
    _run(lambda: api.get_fundamentals(symbol, curr_date, settings=_fresh_settings() if _NO_CACHE else None))


@app.command(help="Fetch balance sheet statement rows.")
def balance_sheet(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    freq: str = typer.Option("quarterly", "--freq", help="Reporting frequency: quarterly or annual."),
    curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_balance_sheet"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()
    _run(lambda: api.get_balance_sheet(symbol, freq, curr_date, settings=_fresh_settings() if _NO_CACHE else None))


@app.command(help="Fetch cashflow statement rows.")
def cashflow(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    freq: str = typer.Option("quarterly", "--freq", help="Reporting frequency: quarterly or annual."),
    curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_cashflow"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()
    _run(lambda: api.get_cashflow(symbol, freq, curr_date, settings=_fresh_settings() if _NO_CACHE else None))


@app.command(help="Fetch income statement rows.")
def income_statement(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    freq: str = typer.Option("quarterly", "--freq", help="Reporting frequency: quarterly or annual."),
    curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_income_statement"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()
    _run(lambda: api.get_income_statement(symbol, freq, curr_date, settings=_fresh_settings() if _NO_CACHE else None))


# ---------------------------------------------------------------------------
# news
# ---------------------------------------------------------------------------
@app.command(help="Fetch stock-specific news within a date window.")
def news(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    start: str = typer.Option(..., "--start", help="Start date YYYY-MM-DD (inclusive)."),
    end: str = typer.Option(..., "--end", help="End date YYYY-MM-DD (inclusive)."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_news"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()
    _run(lambda: api.get_news(symbol, start, end, settings=_fresh_settings() if _NO_CACHE else None))


@app.command(help="Fetch merged China/global market wire news.")
def global_news(
    curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
    look_back_days: int = typer.Option(7, "--look-back-days", help="Look-back window in days."),
    limit: int = typer.Option(10, "--limit", help="Maximum number of items."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_global_news"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()
    date_str = curr_date or ""
    _run(lambda: api.get_global_news(date_str, look_back_days, limit, settings=_fresh_settings() if _NO_CACHE else None))


# ---------------------------------------------------------------------------
# signals_a
# ---------------------------------------------------------------------------
@app.command(help="Fetch F10 shareholder / insider transaction research.")
def shareholders(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_insider_transactions"""

    _apply_global_options(format=format, no_cache=no_cache)
    _run(lambda: api.get_insider_transactions(symbol))


@app.command(help="Fetch analyst EPS consensus profit forecast.")
def profit_forecast(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_profit_forecast"""

    _apply_global_options(format=format, no_cache=no_cache)
    _run(lambda: api.get_profit_forecast(symbol, curr_date, settings=_fresh_settings() if _NO_CACHE else None))


@app.command(help="Fetch today's limit-up hot stocks ranking.")
def hot_stocks(
    date: Optional[str] = typer.Option(None, "--date", help="Trading date YYYY-MM-DD."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_hot_stocks"""

    _apply_global_options(format=format, no_cache=no_cache)
    _run(lambda: api.get_hot_stocks(date or ""))


@app.command(help="Fetch northbound (HSGT) capital flow data.")
def northbound(
    curr_date: str = typer.Option(..., "--curr-date", help="Reference date YYYY-MM-DD."),
    include_history: bool = typer.Option(False, "--include-history", help="Include historical series."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_northbound_flow"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()
    _run(lambda: api.get_northbound_flow(curr_date, include_history, settings=_fresh_settings() if _NO_CACHE else None))


# ---------------------------------------------------------------------------
# signals_b
# ---------------------------------------------------------------------------
@app.command(help="Fetch concept/industry/region block membership for a symbol.")
def concepts(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_concept_blocks"""

    _apply_global_options(format=format, no_cache=no_cache)
    _run(lambda: api.get_concept_blocks(symbol))


@app.command(help="Fetch intraday + daily capital fund flow for a symbol.")
def fund_flow(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    curr_date: str = typer.Option(..., "--curr-date", help="Reference date YYYY-MM-DD."),
    include_history: bool = typer.Option(True, "--include-history/--no-include-history", help="Include daily history."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_fund_flow"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()
    _run(lambda: api.get_fund_flow(symbol, curr_date, include_history))


@app.command(help="Fetch dragon-tiger board (龙虎榜) events + seats.")
def dragon_tiger(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    trade_date: str = typer.Option(..., "--trade-date", help="Reference trade date YYYY-MM-DD."),
    look_back_days: int = typer.Option(30, "--look-back-days", help="Look-back window in days."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_dragon_tiger_board"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()
    _run(lambda: api.get_dragon_tiger_board(symbol, trade_date, look_back_days))


@app.command(help="Fetch lock-up (限售解禁) expiry schedule.")
def lockup(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    trade_date: str = typer.Option(..., "--trade-date", help="Reference trade date YYYY-MM-DD."),
    forward_days: int = typer.Option(90, "--forward-days", help="Forward window in days."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_lockup_expiry"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()
    _run(lambda: api.get_lockup_expiry(symbol, trade_date, forward_days))


@app.command(help="Fetch industry comparison ranking for a symbol.")
def industry(
    symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
    trade_date: str = typer.Option(..., "--trade-date", help="Reference trade date YYYY-MM-DD."),
    top_n: int = typer.Option(20, "--top-n", help="Number of top industries to return."),
    format: Optional[str] = _FORMAT_OPT,
    no_cache: Optional[bool] = _NO_CACHE_OPT,
) -> None:
    """get_industry_comparison"""

    _apply_global_options(format=format, no_cache=no_cache)
    _disable_cache()
    _run(lambda: api.get_industry_comparison(symbol, trade_date, top_n))


def main() -> None:
    """Console-script entry point (``astock-data``)."""

    app()


if __name__ == "__main__":
    main()
