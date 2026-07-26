"""Signal CLI command registrations."""

from __future__ import annotations

from typing import Optional

import typer

from . import api


def register_signal_commands(app: typer.Typer) -> None:
    """Register shareholder, flow, event, and comparison signal commands."""

    from . import cli as cli_runtime

    @app.command(help="Fetch F10 shareholder / insider transaction research.")
    def shareholders(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_insider_transactions"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._run(lambda: api.get_insider_transactions(symbol))

    @app.command(help="Fetch analyst EPS consensus profit forecast.")
    def profit_forecast(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        curr_date: Optional[str] = typer.Option(None, "--curr-date", help="Reference date YYYY-MM-DD."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_profit_forecast"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._run(
            lambda: api.get_profit_forecast(
                symbol,
                curr_date,
                settings=cli_runtime._fresh_settings() if cli_runtime._NO_CACHE else None,
            )
        )

    @app.command(help="Fetch today's limit-up hot stocks ranking.")
    def hot_stocks(
        date: Optional[str] = typer.Option(None, "--date", help="Trading date YYYY-MM-DD."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_hot_stocks"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._run(lambda: api.get_hot_stocks(date or ""))

    @app.command(help="Fetch northbound (HSGT) capital flow data.")
    def northbound(
        curr_date: str = typer.Option(..., "--curr-date", help="Reference date YYYY-MM-DD."),
        include_history: bool = typer.Option(False, "--include-history", help="Include historical series."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_northbound_flow"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        cli_runtime._run(
            lambda: api.get_northbound_flow(
                curr_date,
                include_history,
                settings=cli_runtime._fresh_settings() if cli_runtime._NO_CACHE else None,
            )
        )

    @app.command(help="Fetch concept/industry/region block membership for a symbol.")
    def concepts(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_concept_blocks"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._run(lambda: api.get_concept_blocks(symbol))

    @app.command(help="Fetch intraday + daily capital fund flow for a symbol.")
    def fund_flow(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        curr_date: str = typer.Option(..., "--curr-date", help="Reference date YYYY-MM-DD."),
        include_history: bool = typer.Option(
            True,
            "--include-history/--no-include-history",
            help="Include daily history.",
        ),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_fund_flow"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        cli_runtime._run(lambda: api.get_fund_flow(symbol, curr_date, include_history))

    @app.command(help="Fetch dragon-tiger board (龙虎榜) events + seats.")
    def dragon_tiger(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        trade_date: str = typer.Option(..., "--trade-date", help="Reference trade date YYYY-MM-DD."),
        look_back_days: int = typer.Option(30, "--look-back-days", help="Look-back window in days."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_dragon_tiger_board"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        cli_runtime._run(lambda: api.get_dragon_tiger_board(symbol, trade_date, look_back_days))

    @app.command(help="Fetch lock-up (限售解禁) expiry schedule.")
    def lockup(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        trade_date: str = typer.Option(..., "--trade-date", help="Reference trade date YYYY-MM-DD."),
        forward_days: int = typer.Option(90, "--forward-days", help="Forward window in days."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_lockup_expiry"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        cli_runtime._run(lambda: api.get_lockup_expiry(symbol, trade_date, forward_days))

    @app.command(help="Fetch industry comparison ranking for a symbol.")
    def industry(
        symbol: str = typer.Argument(..., help="Ticker / code / Chinese name."),
        trade_date: str = typer.Option(..., "--trade-date", help="Reference trade date YYYY-MM-DD."),
        top_n: int = typer.Option(20, "--top-n", help="Number of top industries to return."),
        format: Optional[str] = cli_runtime._FORMAT_OPT,
        no_cache: Optional[bool] = cli_runtime._NO_CACHE_OPT,
    ) -> None:
        """get_industry_comparison"""

        cli_runtime._apply_global_options(format=format, no_cache=no_cache)
        cli_runtime._disable_cache()
        cli_runtime._run(lambda: api.get_industry_comparison(symbol, trade_date, top_n))
