"""Public service facade — the canonical import surface for ``astock_data``.

This module re-exports the 18 public functions of the library:
the 17 ``get_*`` data entrypoints (re-exported from
:mod:`astock_data.services`) plus :func:`resolve_ticker` (re-exported from
:mod:`astock_data.resolver`, the single ticker-resolution safety boundary).

All 18 functions return structured Pydantic models — never plain ``str``.

Example
-------
    >>> from astock_data.api import get_stock_data, resolve_ticker
    >>> from astock_data.api import __all__  # 18 names

Intentionally does NOT re-export the old ``route_to_vendor`` semantics or any
private helper; consumers depend only on this stable surface.
"""

from .resolver import resolve_ticker
from .services import (
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
)

__all__ = [
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
