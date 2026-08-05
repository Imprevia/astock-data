"""Resolver, market, fundamentals, and news CLI registrations."""

from __future__ import annotations

from typing import Optional

import typer
from pydantic import BaseModel

from . import api


def register_query_commands(app: typer.Typer) -> None:
    """Register resolver, market, fundamentals, and news commands."""

    from . import cli as cli_runtime

    period_option = typer.Option(
        "day",
        "--period",
        help="K-line period: day, week, month, 1min, 5min, 15min, 30min, or 60min.",
    )

    @app.command(help="Resolve a ticker/code/Chinese name to a canonical Ticker.")
    def resolve(
        ticker: str = typer.Argument(..., help="6-digit code, prefixed/suffixed code, or Chinese stock name."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """Resolve a ticker via the shared safety boundary."""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._run(lambda: api.resolve_ticker(ticker))

    @app.command(help="Fetch OHLCV K-line data for a date range.")
    def kline(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        start: str = typer.Option(..., "--start", help="Start date YYYY-MM-DD (inclusive)."),
        end: str = typer.Option(..., "--end", help="End date YYYY-MM-DD (inclusive)."),
        period: str = period_option,
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_stock_data"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()

        def call() -> BaseModel:
            if cli_runtime._NO_CACHE:
                return api.get_stock_data(
                    symbol,
                    start,
                    end,
                    period=period,
                    cache=cli_runtime._kline_cache(),
                    settings=cli_runtime._fresh_settings(),
                )
            return api.get_stock_data(symbol, start, end, period=period)

        cli_runtime._run(call)

    @app.command(help="Compute a technical indicator series for a symbol.")
    def indicator(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        indicator: str = typer.Option(..., "--indicator", help="Indicator name e.g. macd, rsi, close_50_sma."),
        curr_date: str = typer.Option(..., "--curr-date", help="Reference date YYYY-MM-DD."),
        look_back_days: int = typer.Option(..., "--look-back-days", help="Number of trading days to include."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_indicators"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._run(lambda: api.get_indicators(symbol, indicator, curr_date, look_back_days))

    @app.command("market-breadth", help="Fetch market breadth: indices, limit counts, and board ladders.")
    def market_breadth(
        date: Optional[str] = typer.Option(None, "--date", help="Trading date YYYY-MM-DD."),
        fast: bool = typer.Option(
            False,
            "--fast",
            help="Use bounded limit-stat sources and skip the full-market amount scan.",
        ),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_market_breadth"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        cli_runtime._run(lambda: api.get_market_breadth(date or "", fast=fast))

    @app.command(help="Fetch composite fundamentals snapshot for a symbol.")
    def fundamentals(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_fundamentals"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        cli_runtime._run(
            lambda: api.get_fundamentals(
                symbol,
                curr_date,
                settings=cli_runtime._fresh_settings() if cli_runtime._NO_CACHE else None,
            )
        )

    @app.command(help="Fetch balance sheet statement rows.")
    def balance_sheet(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        freq: str = typer.Option("quarterly", "--freq", help="Reporting frequency: quarterly or annual."),
        curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_balance_sheet"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        cli_runtime._run(
            lambda: api.get_balance_sheet(
                symbol,
                freq,
                curr_date,
                settings=cli_runtime._fresh_settings() if cli_runtime._NO_CACHE else None,
            )
        )

    @app.command(help="Fetch cashflow statement rows.")
    def cashflow(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        freq: str = typer.Option("quarterly", "--freq", help="Reporting frequency: quarterly or annual."),
        curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_cashflow"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        cli_runtime._run(
            lambda: api.get_cashflow(
                symbol,
                freq,
                curr_date,
                settings=cli_runtime._fresh_settings() if cli_runtime._NO_CACHE else None,
            )
        )

    @app.command(help="Fetch income statement rows.")
    def income_statement(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        freq: str = typer.Option("quarterly", "--freq", help="Reporting frequency: quarterly or annual."),
        curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_income_statement"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        cli_runtime._run(
            lambda: api.get_income_statement(
                symbol,
                freq,
                curr_date,
                settings=cli_runtime._fresh_settings() if cli_runtime._NO_CACHE else None,
            )
        )

    @app.command(help="Fetch stock-specific news within a date window.")
    def news(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        start: str = typer.Option(..., "--start", help="Start date YYYY-MM-DD (inclusive)."),
        end: str = typer.Option(..., "--end", help="End date YYYY-MM-DD (inclusive)."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_news"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        cli_runtime._run(
            lambda: api.get_news(
                symbol,
                start,
                end,
                settings=cli_runtime._fresh_settings() if cli_runtime._NO_CACHE else None,
            )
        )

    @app.command(help="Fetch merged China/global market wire news.")
    def global_news(
        curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
        look_back_days: int = typer.Option(7, "--look-back-days", help="Look-back window in days."),
        limit: int = typer.Option(10, "--limit", help="Maximum number of items."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_global_news"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        date_str = curr_date or ""
        cli_runtime._run(
            lambda: api.get_global_news(
                date_str,
                look_back_days,
                limit,
                settings=cli_runtime._fresh_settings() if cli_runtime._NO_CACHE else None,
            )
        )
