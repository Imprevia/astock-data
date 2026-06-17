"""astock_data — A-share market data service.

Top-level package exposing the 18 public functions:
17 ``get_*`` data entrypoints plus :func:`resolve_ticker`.
All return structured Pydantic models (never plain ``str``).
"""

from .api import (
    get_balance_sheet,
    get_cashflow,
    get_concept_blocks,
    get_dragon_tiger_board,
    get_fund_flow,
    get_fundamentals,
    get_global_news,
    get_hot_stocks,
    get_income_statement,
    get_indicators,
    get_industry_comparison,
    get_insider_transactions,
    get_lockup_expiry,
    get_news,
    get_northbound_flow,
    get_profit_forecast,
    get_stock_data,
    resolve_ticker,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # resolver (1)
    "resolve_ticker",
    # market_data (2)
    "get_stock_data",
    "get_indicators",
    # fundamentals (4)
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    # news (2)
    "get_news",
    "get_global_news",
    # signals_a (4)
    "get_insider_transactions",
    "get_profit_forecast",
    "get_hot_stocks",
    "get_northbound_flow",
    # signals_b (5)
    "get_concept_blocks",
    "get_fund_flow",
    "get_dragon_tiger_board",
    "get_lockup_expiry",
    "get_industry_comparison",
]
