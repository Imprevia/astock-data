"""Public service facade — the canonical import surface for ``astock_data``.

This module re-exports the 25 public functions of the library:
24 ``get_*`` data entrypoints (re-exported from
:mod:`astock_data.services`) plus :func:`resolve_ticker` (re-exported from
:mod:`astock_data.resolver`, the single ticker-resolution safety boundary).

All public functions return structured Pydantic models — never plain ``str``.

Example
-------
    >>> from astock_data.api import get_stock_data, resolve_ticker
    >>> from astock_data.api import __all__  # 25 names

Intentionally does NOT re-export the old ``route_to_vendor`` semantics or any
private helper; consumers depend only on this stable surface.
"""

from .resolver import resolve_ticker
from .services import (
    get_balance_sheet,
    get_cashflow,
    get_concept_blocks,
    get_dragon_tiger_board,
    get_etf_daily,
    get_fund_flow,
    get_fundamentals,
    get_global_news,
    get_hot_stocks,
    get_income_statement,
    get_index_kline,
    get_indicators,
    get_industry_comparison,
    get_insider_transactions,
    get_lockup_expiry,
    get_market_breadth,
    get_news,
    get_northbound_flow,
    get_profit_forecast,
    get_sector_fund_flow,
    get_sector_fund_flow_history,
    get_sector_strength,
    get_stock_amount,
    get_stock_data,
)

__all__ = [
    # resolver (1)
    "resolve_ticker",
    # market_data (5)
    "get_stock_data",
    "get_indicators",
    "get_market_breadth",
    "get_index_kline",
    "get_stock_amount",
    "get_etf_daily",
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
    # signals_b (8)
    "get_concept_blocks",
    "get_fund_flow",
    "get_dragon_tiger_board",
    "get_lockup_expiry",
    "get_industry_comparison",
    "get_sector_fund_flow",
    "get_sector_fund_flow_history",
    "get_sector_strength",
]
