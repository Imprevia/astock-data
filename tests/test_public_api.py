"""Public API facade contract tests (Task 20).

Asserts the 25 public functions (``resolve_ticker`` + 24 ``get_*``) are
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

# The 24 public get_* entrypoints (sorted for stable diffs).
GET_FUNCS = [
    "get_balance_sheet",
    "get_cashflow",
    "get_concept_blocks",
    "get_dragon_tiger_board",
    "get_etf_daily",
    "get_fund_flow",
    "get_fundamentals",
    "get_global_news",
    "get_hot_stocks",
    "get_income_statement",
    "get_industry_comparison",
    "get_index_kline",
    "get_indicators",
    "get_insider_transactions",
    "get_lockup_expiry",
    "get_market_breadth",
    "get_news",
    "get_northbound_flow",
    "get_profit_forecast",
    "get_sector_fund_flow",
    "get_sector_fund_flow_history",
    "get_sector_strength",
    "get_stock_amount",
    "get_stock_data",
]

PUBLIC_FUNCS = ["resolve_ticker", *GET_FUNCS]  # 25 total


# --------------------------------------------------------------------------- #
# __all__ sizing
# --------------------------------------------------------------------------- #
def test_api_all_has_exactly_25_names():
    assert len(api.__all__) == 25
    assert set(api.__all__) == set(PUBLIC_FUNCS)


def test_services_all_has_exactly_24_names():
    assert len(services.__all__) == 24
    assert set(services.__all__) == set(GET_FUNCS)


# --------------------------------------------------------------------------- #
# importability from the three canonical surfaces
# --------------------------------------------------------------------------- #
def test_all_25_importable_from_top_level():
    for name in PUBLIC_FUNCS:
        assert hasattr(astock_data, name), f"astock_data missing {name}"
        assert callable(getattr(astock_data, name))


def test_all_25_importable_from_api_module():
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


# --------------------------------------------------------------------------- #
# get_sector_fund_flow — sector-level fund flow (TDD RED: api not implemented yet)
# --------------------------------------------------------------------------- #
# Field mapping (verified by Atlas via live curl 2026-06-30):
#   rank endpoint data.diff[]:  f12=code, f14=name, f3=change_pct,
#       f62=main_net_inflow (元, raw), f184=main_net_inflow_pct
#   history endpoint data.klines: "date,f52_main_net_inflow,..." comma-split
# Client funcs already implemented in eastmoney.py: fetch_sector_fund_flow_rank
# / fetch_sector_fund_flow_history. api.get_sector_fund_flow NOT yet implemented.

from astock_data.models.signals import SectorFundFlowResult  # noqa: E402
from astock_data.clients import eastmoney as _em  # noqa: E402


def test_sector_fund_flow_normal(monkeypatch):
    """Happy path: rank + history return data -> SectorFundFlowResult."""
    rank_rows = [
        {"code": "BK0447", "name": "半导体", "change_pct": 2.5,
         "main_net_inflow": 1e8, "main_net_inflow_pct": 1.5},
    ]
    hist_rows = [{"date": f"2026-06-{30 - i}", "main_net_inflow": 1e8} for i in range(5)]
    monkeypatch.setattr(_em, "fetch_sector_fund_flow_rank", lambda **kw: rank_rows)
    monkeypatch.setattr(_em, "fetch_sector_fund_flow_history", lambda secid, days=5, **kw: hist_rows)
    # RED until api.get_sector_fund_flow is implemented in Task 4.
    from astock_data.api import get_sector_fund_flow
    result = get_sector_fund_flow(days=5)
    assert isinstance(result, SectorFundFlowResult)
    assert len(result.sectors) == 1
    assert result.sectors[0].name == "半导体"
    assert len(result.sectors[0].history) == 5
    assert result.date


def test_sector_fund_flow_empty(monkeypatch):
    """Empty upstream -> empty sectors + warning."""
    monkeypatch.setattr(_em, "fetch_sector_fund_flow_rank", lambda **kw: [])
    from astock_data.api import get_sector_fund_flow
    result = get_sector_fund_flow()
    assert result.sectors == []
    assert len(result.warnings) > 0


def test_sector_fund_flow_api_error(monkeypatch):
    """Upstream exception -> graceful degradation, no crash."""
    def _boom(**kw):
        raise RuntimeError("upstream down")
    monkeypatch.setattr(_em, "fetch_sector_fund_flow_rank", _boom)
    from astock_data.api import get_sector_fund_flow
    result = get_sector_fund_flow()
    assert result.sectors == []
    assert len(result.warnings) > 0


def test_sector_fund_flow_in_all():
    """get_sector_fund_flow must be in api.__all__ (contract)."""
    from astock_data import api as _api
    assert "get_sector_fund_flow" in _api.__all__


# --------------------------------------------------------------------------- #
# get_index_kline / get_stock_amount — K-line with amount (TDD RED: api not impl)
# --------------------------------------------------------------------------- #
from astock_data.models.market import IndexKlineResult, StockAmountResult  # noqa: E402
from astock_data.clients import eastmoney as _em  # noqa: E402


def test_index_kline_normal(monkeypatch):
    klines = [{"date": "2026-06-30", "open": 4058.0, "high": 4097.0, "low": 4052.0, "close": 4094.0, "volume": 5.98e8, "amount": 1.53e12}]
    monkeypatch.setattr(_em, "fetch_kline", lambda secid, days=10, **kw: klines)
    from astock_data.api import get_index_kline
    result = get_index_kline("sh", 5)
    assert isinstance(result, IndexKlineResult)
    assert len(result.bars) == 1
    assert result.bars[0].amount == 1.53e12
    assert result.warnings == []


def test_index_kline_empty(monkeypatch):
    monkeypatch.setattr(_em, "fetch_kline", lambda secid, days=10, **kw: [])
    from astock_data.services import market_data as _md

    class _EmptyTdx:
        def index_bars(self, key, days=10):
            return []

    monkeypatch.setattr(_md, "TdxClient", lambda: _EmptyTdx())
    from astock_data.api import get_index_kline
    result = get_index_kline("sh", 5)
    assert result.bars == []
    assert result.warnings == []


def test_index_kline_falls_back_to_tdx(monkeypatch):
    monkeypatch.setattr(_em, "fetch_kline", lambda secid, days=10, **kw: [])
    from astock_data.services import market_data as _md

    class _FallbackTdx:
        def index_bars(self, key, days=10):
            return [
                {
                    "date": "2026-07-01",
                    "open": 3000.0,
                    "high": 3010.0,
                    "low": 2990.0,
                    "close": 3005.0,
                    "volume": 123456.0,
                    "amount": 1666220425216.0,
                }
            ]

    monkeypatch.setattr(_md, "TdxClient", lambda: _FallbackTdx())
    from astock_data.api import get_index_kline

    result = get_index_kline("sh", 5)

    assert len(result.bars) == 1
    assert result.bars[0].amount == 1666220425216.0
    assert "已降级到 mootdx" in result.warnings[0]


def test_index_kline_api_error(monkeypatch):
    def _boom(secid, days=10, **kw):
        raise RuntimeError("upstream down")
    monkeypatch.setattr(_em, "fetch_kline", _boom)
    from astock_data.services import market_data as _md

    class _FailingTdx:
        def index_bars(self, key, days=10):
            raise RuntimeError("tdx down")

    monkeypatch.setattr(_md, "TdxClient", lambda: _FailingTdx())
    from astock_data.api import get_index_kline
    result = get_index_kline("sh", 5)
    assert result.bars == []
    assert len(result.warnings) > 0
    assert "upstream down" in result.warnings[0]
    assert "tdx down" in result.warnings[1]


def test_stock_amount_normal(monkeypatch):
    klines = [{"date": f"2026-06-{30 - i}", "amount": 1.1e9} for i in range(5)]
    monkeypatch.setattr(_em, "fetch_kline", lambda secid, days=10, **kw: klines)
    from astock_data.api import get_stock_amount
    result = get_stock_amount("000001", 5)
    assert isinstance(result, StockAmountResult)
    assert len(result.bars) == 5


def test_kline_funcs_in_all():
    from astock_data import api as _api
    assert "get_index_kline" in _api.__all__
    assert "get_stock_amount" in _api.__all__


# --------------------------------------------------------------------------- #
# get_sector_strength / get_sector_fund_flow_history / get_etf_daily
# (daily-review step-2 「定方向」data-source migration into the data layer)
# --------------------------------------------------------------------------- #
from astock_data.models.signals import (  # noqa: E402
    SectorFundFlowHistoryResult,
    SectorStrengthResult,
)
from astock_data.models.market import EtfDailyResult  # noqa: E402
from astock_data.clients import eastmoney as _em  # noqa: E402


def _clist_payload():
    return {
        "data": {
            "diff": [
                {"f12": "BK0447", "f14": "半导体", "f3": 2.5, "f6": 3e9,
                 "f62": 1e8, "f184": 1.5, "f104": 80, "f105": 10},
                {"f12": "BK0733", "f14": "半导体Ⅱ", "f3": 1.2, "f6": 1e9,
                 "f62": 5e7, "f184": 0.8, "f104": 40, "f105": 30},
            ]
        }
    }


def test_sector_strength_normal(monkeypatch, tmp_path):
    """Happy path: clist returns rows -> SectorStrengthResult with dedup."""
    monkeypatch.setenv("ASTOCK_CACHE_DIR", str(tmp_path))
    from astock_data.config import get_settings
    get_settings.cache_clear()

    monkeypatch.setattr(_em.EastmoneyClient, "push2", lambda self, path, params: _clist_payload())
    from astock_data.api import get_sector_strength
    result = get_sector_strength("2026-07-20")
    assert isinstance(result, SectorStrengthResult)
    # Dedup: 半导体 and 半导体Ⅱ collapse to one row keeping the larger |f62|.
    assert len(result.rows) == 1
    assert result.rows[0].name == "半导体"
    assert result.rows[0].amount == 3e9
    assert result.rows[0].up_count == 80
    assert result.cache_source is None


def test_sector_strength_falls_back_to_cache(monkeypatch, tmp_path):
    """Upstream push2 raises -> cache fallback surfaces prior snapshot."""
    monkeypatch.setenv("ASTOCK_CACHE_DIR", str(tmp_path))
    from astock_data.config import get_settings
    get_settings.cache_clear()

    def _boom(self, path, params):
        raise ConnectionError("blocked by anti-crawler")
    monkeypatch.setattr(_em.EastmoneyClient, "push2", _boom)

    # Seed a cache snapshot for today.
    from astock_data.cache import SQLiteStructuredCache
    target = "2026-07-20"
    cache = SQLiteStructuredCache(base_dir=tmp_path)
    cache.write_general(
        "sector_strength",
        f"{target}-15",
        target,
        {"rows": [{"f12": "BK0447", "f14": "半导体", "f3": 2.5}]},
    )

    from astock_data.api import get_sector_strength
    result = get_sector_strength(target)
    assert result.cache_source == target
    assert len(result.rows) == 1
    assert any("缓存回退" in w for w in result.warnings)


def test_sector_strength_empty_when_no_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTOCK_CACHE_DIR", str(tmp_path))
    from astock_data.config import get_settings
    get_settings.cache_clear()

    def _boom(self, path, params):
        raise ConnectionError("down")
    monkeypatch.setattr(_em.EastmoneyClient, "push2", _boom)

    from astock_data.api import get_sector_strength
    result = get_sector_strength("2026-07-20")
    assert result.rows == []
    assert any("无可用缓存" in w for w in result.warnings)


def test_sector_fund_flow_history_normal(monkeypatch, tmp_path):
    """Happy path: each code returns its history list."""
    monkeypatch.setenv("ASTOCK_CACHE_DIR", str(tmp_path))
    from astock_data.config import get_settings
    get_settings.cache_clear()

    hist = [{"date": f"2026-07-{20 - i}", "main_net_inflow": 1e8} for i in range(5)]
    monkeypatch.setattr(
        _em, "fetch_sector_fund_flow_history",
        lambda secid, days=5, **kw: hist,
    )
    from astock_data.api import get_sector_fund_flow_history
    result = get_sector_fund_flow_history(["BK0447", "BK0733"], "2026-07-20", days=5)
    assert isinstance(result, SectorFundFlowHistoryResult)
    assert set(result.history_by_code.keys()) == {"BK0447", "BK0733"}
    assert len(result.history_by_code["BK0447"]) == 5


def test_sector_fund_flow_history_partial_failure(monkeypatch, tmp_path):
    """One code raising -> that code maps to [] but others still resolve."""
    monkeypatch.setenv("ASTOCK_CACHE_DIR", str(tmp_path))
    from astock_data.config import get_settings
    get_settings.cache_clear()

    def _hist(secid, days=5, **kw):
        if "bk0733" in secid:
            raise RuntimeError("upstream down")
        return [{"date": "2026-07-20", "main_net_inflow": 1e8}]
    monkeypatch.setattr(_em, "fetch_sector_fund_flow_history", _hist)
    from astock_data.api import get_sector_fund_flow_history
    result = get_sector_fund_flow_history(["BK0447", "BK0733"], "2026-07-20")
    assert result.history_by_code["BK0447"]
    assert result.history_by_code["BK0733"] == []


def test_etf_daily_normal(monkeypatch):
    klines = [{"date": "2026-07-20", "open": 1.0, "high": 1.1, "low": 0.9,
               "close": 1.05, "volume": 1000.0, "amount": 1050.0}]
    monkeypatch.setattr(_em, "fetch_kline", lambda secid, days=10, **kw: klines)
    from astock_data.api import get_etf_daily
    result = get_etf_daily(["512480", "159995"])
    assert isinstance(result, EtfDailyResult)
    assert len(result.bars_by_code["512480"]) == 1
    assert result.bars_by_code["512480"][0].amount == 1050.0


def test_etf_daily_rejects_unknown_code():
    from astock_data.api import get_etf_daily
    result = get_etf_daily(["999999"])
    assert result.bars_by_code["999999"] == []
    assert any("不在行业ETF映射内" in w for w in result.warnings)


def test_new_sector_funcs_in_all():
    from astock_data import api as _api
    assert "get_sector_strength" in _api.__all__
    assert "get_sector_fund_flow_history" in _api.__all__
    assert "get_etf_daily" in _api.__all__
