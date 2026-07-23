"""Daily-review CLI command registrations."""

from __future__ import annotations

from typing import Optional

import typer

from . import api


def register_daily_review_commands(app: typer.Typer) -> None:
    """Register the daily-review facade commands on the root CLI app."""

    from .cli import (
        _FORMAT_OPT,
        _NO_CACHE_OPT,
        _apply_global_options,
        _disable_cache,
        _run,
    )

    @app.command("index-kline", help="Fetch recent daily K-line data for an index.")
    def index_kline(
        key: str = typer.Argument(..., help="Index key: sh, szci, cyb, or hs300."),
        days: int = typer.Option(10, "--days", help="Number of recent days to return."),
        format: Optional[str] = _FORMAT_OPT,
        no_cache: Optional[bool] = _NO_CACHE_OPT,
    ) -> None:
        """get_index_kline"""

        _apply_global_options(format=format, no_cache=no_cache)
        _disable_cache()
        _run(lambda: api.get_index_kline(key, days=days))

    @app.command("stock-amount", help="Fetch recent daily turnover data for a stock.")
    def stock_amount(
        ticker: str = typer.Argument(..., help="A-share ticker code."),
        days: int = typer.Option(10, "--days", help="Number of recent days to return."),
        format: Optional[str] = _FORMAT_OPT,
        no_cache: Optional[bool] = _NO_CACHE_OPT,
    ) -> None:
        """get_stock_amount"""

        _apply_global_options(format=format, no_cache=no_cache)
        _disable_cache()
        _run(lambda: api.get_stock_amount(ticker, days=days))

    @app.command("sector-fund-flow", help="Fetch sector fund-flow ranking and history.")
    def sector_fund_flow(
        curr_date: str = typer.Option("", "--curr-date", help="Reference date YYYY-MM-DD."),
        days: int = typer.Option(5, "--days", help="Number of history days to return."),
        format: Optional[str] = _FORMAT_OPT,
        no_cache: Optional[bool] = _NO_CACHE_OPT,
    ) -> None:
        """get_sector_fund_flow"""

        _apply_global_options(format=format, no_cache=no_cache)
        _disable_cache()
        _run(lambda: api.get_sector_fund_flow(curr_date, days=days))

    @app.command("sector-strength", help="Fetch sector strength metrics for a date.")
    def sector_strength(
        curr_date: str = typer.Option("", "--curr-date", help="Reference date YYYY-MM-DD."),
        format: Optional[str] = _FORMAT_OPT,
        no_cache: Optional[bool] = _NO_CACHE_OPT,
    ) -> None:
        """get_sector_strength"""

        _apply_global_options(format=format, no_cache=no_cache)
        _disable_cache()
        _run(lambda: api.get_sector_strength(curr_date))

    @app.command("sector-fund-flow-history", help="Fetch fund-flow history for sectors.")
    def sector_fund_flow_history(
        codes: list[str] = typer.Argument(..., help="One or more sector codes."),
        curr_date: str = typer.Option("", "--curr-date", help="Reference date YYYY-MM-DD."),
        days: int = typer.Option(5, "--days", help="Number of history days to return."),
        format: Optional[str] = _FORMAT_OPT,
        no_cache: Optional[bool] = _NO_CACHE_OPT,
    ) -> None:
        """get_sector_fund_flow_history"""

        _apply_global_options(format=format, no_cache=no_cache)
        _disable_cache()
        _run(lambda: api.get_sector_fund_flow_history(codes, curr_date, days))

    @app.command("etf-daily", help="Fetch recent daily K-line data for ETFs.")
    def etf_daily(
        codes: list[str] = typer.Argument(..., help="One or more ETF codes."),
        days: int = typer.Option(10, "--days", help="Number of recent days to return."),
        format: Optional[str] = _FORMAT_OPT,
        no_cache: Optional[bool] = _NO_CACHE_OPT,
    ) -> None:
        """get_etf_daily"""

        _apply_global_options(format=format, no_cache=no_cache)
        _disable_cache()
        _run(lambda: api.get_etf_daily(codes, days=days))
