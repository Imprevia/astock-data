"""Public service facade re-exporting every ``get_*`` entrypoint.

The individual service modules (``market_data`` / ``fundamentals`` / ``news``
/ ``signals_a`` / ``signals_b``) own the implementation; this package init is
the single re-export surface so callers can do ``from astock_data.services
import get_stock_data`` for any of the 18 public ``get_*`` functions.

Note: ``resolve_ticker`` is NOT re-exported here — it lives in
``astock_data.resolver`` (the resolver is a cross-cutting safety boundary, not
a data service). The top-level :mod:`astock_data` package and :mod:`astock_data.api`
expose it alongside these data functions as the 19th public function.
"""

from .fundamentals import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
)
from .market_data import (
    get_indicators,
    get_stock_data,
)
from .market_breadth import get_market_breadth
from .news import (
    get_global_news,
    get_news,
)
from .signals_a import (
    get_hot_stocks,
    get_insider_transactions,
    get_northbound_flow,
    get_profit_forecast,
)
from .signals_b import (
    get_concept_blocks,
    get_dragon_tiger_board,
    get_fund_flow,
    get_industry_comparison,
    get_lockup_expiry,
)

__all__ = [
    # fundamentals
    "get_balance_sheet",
    "get_cashflow",
    "get_fundamentals",
    "get_income_statement",
    # market_data
    "get_indicators",
    "get_market_breadth",
    "get_stock_data",
    # news
    "get_global_news",
    "get_news",
    # signals_a
    "get_hot_stocks",
    "get_insider_transactions",
    "get_northbound_flow",
    "get_profit_forecast",
    # signals_b
    "get_concept_blocks",
    "get_dragon_tiger_board",
    "get_fund_flow",
    "get_industry_comparison",
    "get_lockup_expiry",
]
