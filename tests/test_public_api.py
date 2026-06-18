"""Public API facade contract tests (Task 20).

Asserts the 19 public functions (``resolve_ticker`` + 18 ``get_*``) are
importable from the three canonical surfaces, that the ``__all__`` lists have
the exact expected sizes, and that every public ``get_*`` returns a Pydantic
``BaseModel`` subclass (never a plain ``str``) per the plan's "structured
Pydantic models" Must-Have.

Fully offline: only inspects annotations / ``__all__`` / module attributes,
no live HTTP, no mootdx TCP.
"""

from __future__ import annotations

import pytest

import astock_data
from astock_data import api, resolver, services
from astock_data.models.base import Ticker

pytestmark = pytest.mark.unit

# The 18 public get_* entrypoints (sorted for stable diffs).
GET_FUNCS = [
    "get_balance_sheet",
    "get_cashflow",
    "get_concept_blocks",
    "get_dragon_tiger_board",
    "get_fund_flow",
    "get_fundamentals",
    "get_global_news",
    "get_hot_stocks",
    "get_income_statement",
    "get_indicators",
    "get_industry_comparison",
    "get_insider_transactions",
    "get_lockup_expiry",
    "get_market_breadth",
    "get_news",
    "get_northbound_flow",
    "get_profit_forecast",
    "get_stock_data",
]

PUBLIC_FUNCS = ["resolve_ticker", *GET_FUNCS]  # 19 total


# --------------------------------------------------------------------------- #
# __all__ sizing
# --------------------------------------------------------------------------- #
def test_api_all_has_exactly_19_names():
    assert len(api.__all__) == 19
    assert set(api.__all__) == set(PUBLIC_FUNCS)


def test_services_all_has_exactly_18_names():
    assert len(services.__all__) == 18
    assert set(services.__all__) == set(GET_FUNCS)


# --------------------------------------------------------------------------- #
# importability from the three canonical surfaces
# --------------------------------------------------------------------------- #
def test_all_19_importable_from_top_level():
    for name in PUBLIC_FUNCS:
        assert hasattr(astock_data, name), f"astock_data missing {name}"
        assert callable(getattr(astock_data, name))


def test_all_19_importable_from_api_module():
    for name in PUBLIC_FUNCS:
        assert hasattr(api, name), f"astock_data.api missing {name}"
        assert callable(getattr(api, name))


def test_get_funcs_and_resolver_importable_from_services_and_resolver():
    # 18 get_* from services
    for name in GET_FUNCS:
        assert hasattr(services, name), f"astock_data.services missing {name}"
        assert callable(getattr(services, name))
    # resolve_ticker from resolver
    assert hasattr(resolver, "resolve_ticker")
    assert callable(resolver.resolve_ticker)
    # and re-exported at top-level alongside the 18 data functions
    assert astock_data.resolve_ticker is resolver.resolve_ticker


def test_version_still_exposed():
    assert isinstance(astock_data.__version__, str)
    assert astock_data.__version__  # non-empty


# --------------------------------------------------------------------------- #
# structured-model contract: no public get_* returns a plain str
# --------------------------------------------------------------------------- #
def _return_class(func) -> type:
    """Resolve a function's ``return`` annotation to a concrete class.

    Service modules use ``from __future__ import annotations`` (PEP 563), so
    ``func.__annotations__["return"]`` is a *string* forward ref. We resolve it
    against the function's own module globals. Crucially we resolve ONLY the
    return annotation (not the full annotation set via ``get_type_hints``),
    because some modules keep ``requests``/``Mapping`` lazily imported and
    therefore unresolved in their globals — evaluating every parameter
    annotation would raise ``NameError`` on those unrelated names.
    """
    ret = func.__annotations__.get("return")
    if ret is None:
        raise AssertionError(f"{func.__name__} missing return annotation")
    if isinstance(ret, type):
        return ret
    # string forward ref -> resolve in the defining module's namespace
    return eval(ret, func.__globals__)  # noqa: S307


def test_every_get_func_returns_basemodel_subclass():
    """Each of the 18 get_* must annotate its return as a BaseModel subclass."""
    from pydantic import BaseModel

    for name in GET_FUNCS:
        func = getattr(api, name)
        ret = _return_class(func)
        assert isinstance(ret, type), f"{name} return annotation is not a class: {ret!r}"
        assert issubclass(ret, BaseModel), (
            f"{name} must return a pydantic BaseModel subclass, got {ret!r}"
        )
        assert ret is not str, f"{name} must not return a plain str"


def test_resolve_ticker_returns_ticker_model():
    ret = _return_class(resolver.resolve_ticker)
    assert ret is Ticker
    # Ticker is itself a BaseModel subclass — not a plain str.
    from pydantic import BaseModel

    assert issubclass(Ticker, BaseModel)
