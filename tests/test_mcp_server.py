"""Unit tests for the FastMCP server (Task 21).

All tests are fully offline — the public ``astock_data.api`` facade is mocked,
so no network, no mootdx TCP, and no vendor HTTP is ever reached.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _model(model_cls, **kwargs):
    """Build a minimal valid instance, auto-supplying required shared fields."""
    shared = {"source": "stub", "retrieved_at": _now()}
    shared.update(kwargs)
    return model_cls(**shared)


# The 19 public functions, one per MCP tool.
EXPECTED_TOOLS = [
    "resolve_ticker",
    "get_stock_data",
    "get_indicators",
    "get_market_breadth",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_global_news",
    "get_insider_transactions",
    "get_profit_forecast",
    "get_hot_stocks",
    "get_northbound_flow",
    "get_concept_blocks",
    "get_fund_flow",
    "get_dragon_tiger_board",
    "get_lockup_expiry",
    "get_industry_comparison",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _registered_tool_names() -> list[str]:
    """Use FastMCP's own introspection (``list_tools``) to read registered names."""
    from astock_data.mcp.server import mcp

    tools = asyncio.run(mcp.list_tools())
    return sorted(t.name for t in tools)


def _server_module():
    """Import the server module fresh (so monkeypatch of ``astock_data.api`` sticks)."""
    import astock_data.mcp.server as server

    return server


# ---------------------------------------------------------------------------
# tool_registration
# ---------------------------------------------------------------------------


class TestToolRegistration:
    def test_exactly_19_tools_registered(self):
        names = _registered_tool_names()
        assert len(names) == 19

    def test_expected_tool_names_match_exactly(self):
        names = _registered_tool_names()
        assert names == sorted(EXPECTED_TOOLS)

    def test_server_name_is_astock_data(self):
        from astock_data.mcp.server import mcp

        # FastMCP exposes the configured name via the ``name`` attribute.
        assert getattr(mcp, "name", None) == "astock-data"

    def test_each_tool_has_docstring(self):
        """FastMCP derives the tool description from the function docstring."""
        import astock_data.mcp.server as server

        tools = asyncio.run(server.mcp.list_tools())
        by_name = {t.name: t for t in tools}
        for name in EXPECTED_TOOLS:
            tool = by_name[name]
            desc = getattr(tool, "description", None) or ""
            assert desc.strip(), f"tool {name!r} has empty description/docstring"

    def test_input_schema_generated_for_parameterized_tools(self):
        """FastMCP auto-generates an input schema from annotations."""
        import astock_data.mcp.server as server

        tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
        # get_stock_data(symbol, start_date, end_date) — 3 params, all strings.
        sd = tools["get_stock_data"]
        schema = _input_schema(sd)
        assert set(schema.get("required", [])) == {
            "symbol",
            "start_date",
            "end_date",
        }
        assert schema["properties"]["symbol"]["type"] == "string"
        # Optional/ defaulted params are NOT required.
        fund_schema = _input_schema(tools["get_fundamentals"])
        assert "curr_date" in fund_schema["properties"]
        assert "curr_date" not in fund_schema.get("required", [])


# ---------------------------------------------------------------------------
# json_serializable — call tools with MOCKED api; assert json.dumps succeeds
# ---------------------------------------------------------------------------


class TestJsonSerializable:
    def test_get_stock_data_result_is_json_serializable(self, monkeypatch):
        from astock_data.models.base import Ticker
        from astock_data.models.market import StockDataResult

        fake = _model(
            StockDataResult, ticker=Ticker(code="688017", market="sh"), bars=[]
        )
        monkeypatch.setattr(
            "astock_data.api.get_stock_data", lambda *a, **k: fake
        )
        server = _server_module()

        result = server.get_stock_data("688017", "2026-01-01", "2026-01-10")
        # Must be JSON-serializable end-to-end.
        serialized = json.dumps(result)
        assert json.loads(serialized)["source"] == "stub"
        # ticker serializes to the nested dict form.
        assert result["ticker"]["code"] == "688017"

    def test_resolve_ticker_result_is_json_serializable(self, monkeypatch):
        from astock_data.models.base import Ticker

        fake = Ticker(code="000001", market="sz", name="平安银行")
        monkeypatch.setattr(
            "astock_data.api.resolve_ticker", lambda *a, **k: fake
        )
        server = _server_module()

        result = server.resolve_ticker("平安银行")
        serialized = json.dumps(result)
        assert json.loads(serialized)["code"] == "000001"

    def test_get_fundamentals_result_is_json_serializable(self, monkeypatch):
        from astock_data.models.fundamentals import FundamentalsResult, Quote

        # model_construct bypasses validation so we don't have to build a
        # fully-populated Quote — we only assert the MCP tool serializes it.
        fake = FundamentalsResult.model_construct(
            source="stub", retrieved_at=_now(), quote=Quote.model_construct()
        )
        monkeypatch.setattr(
            "astock_data.api.get_fundamentals", lambda *a, **k: fake
        )
        server = _server_module()

        result = server.get_fundamentals("688017", "2026-05-12")
        json.dumps(result)  # must not raise
        assert result["source"] == "stub"

    def test_get_news_result_is_json_serializable(self, monkeypatch):
        from astock_data.models.news import NewsResult

        fake = _model(NewsResult, ticker="688017", items=[])
        monkeypatch.setattr("astock_data.api.get_news", lambda *a, **k: fake)
        server = _server_module()

        result = server.get_news("688017", "2026-01-01", "2026-01-10")
        json.dumps(result)
        assert result["ticker"] == "688017"

    def test_all_19_tools_produce_json_serializable_output(self, monkeypatch):
        """Every tool, with its api function stubbed to a minimal model,
        must return a dict that ``json.dumps`` accepts."""
        from astock_data.models.base import ResultBase, Ticker

        # model_construct bypasses per-subclass required-field validation;
        # we only assert the MCP adapter serializes whatever the facade returns.
        def _stub(*a, **k):
            return ResultBase.model_construct(
                source="stub", retrieved_at=_now()
            )

        server = _server_module()
        for name in EXPECTED_TOOLS:
            monkeypatch.setattr(f"astock_data.api.{name}", _stub)
            # resolve_ticker returns a Ticker specifically.
            if name == "resolve_ticker":
                monkeypatch.setattr(
                    "astock_data.api.resolve_ticker",
                    lambda *a, **k: Ticker(code="000001", market="sz"),
                )

        # Call each tool with the right number of positional args.
        calls = {
            "resolve_ticker": (server.resolve_ticker, ("000001",)),
            "get_stock_data": (server.get_stock_data, ("000001", "2026-01-01", "2026-01-02")),
            "get_indicators": (server.get_indicators, ("000001", "rsi", "2026-01-02", 14)),
            "get_market_breadth": (server.get_market_breadth, ("2026-01-02",)),
            "get_fundamentals": (server.get_fundamentals, ("000001", "2026-01-02")),
            "get_balance_sheet": (server.get_balance_sheet, ("000001", "quarterly", "2026-01-02")),
            "get_cashflow": (server.get_cashflow, ("000001", "quarterly", "2026-01-02")),
            "get_income_statement": (server.get_income_statement, ("000001", "quarterly", "2026-01-02")),
            "get_news": (server.get_news, ("000001", "2026-01-01", "2026-01-02")),
            "get_global_news": (server.get_global_news, ("2026-01-02", 7, 10)),
            "get_insider_transactions": (server.get_insider_transactions, ("000001",)),
            "get_profit_forecast": (server.get_profit_forecast, ("000001", "2026-01-02")),
            "get_hot_stocks": (server.get_hot_stocks, ("2026-01-02",)),
            "get_northbound_flow": (server.get_northbound_flow, ("2026-01-02", False)),
            "get_concept_blocks": (server.get_concept_blocks, ("000001",)),
            "get_fund_flow": (server.get_fund_flow, ("000001", "2026-01-02", True)),
            "get_dragon_tiger_board": (server.get_dragon_tiger_board, ("000001", "2026-01-02", 30)),
            "get_lockup_expiry": (server.get_lockup_expiry, ("000001", "2026-01-02", 90)),
            "get_industry_comparison": (server.get_industry_comparison, ("000001", "2026-01-02", 20)),
        }

        for name in EXPECTED_TOOLS:
            fn, args = calls[name]
            result = fn(*args)
            assert isinstance(result, dict), f"{name} did not return a dict"
            # No error payload on the happy path.
            assert "error" not in result, f"{name} unexpectedly errored"
            serialized = json.dumps(result)  # must not raise
            loaded = json.loads(serialized)
            if name == "resolve_ticker":
                # resolve_ticker returns a Ticker (code/market), not a ResultBase.
                assert loaded["code"] == "000001"
            else:
                assert loaded["source"] == "stub", f"{name} missing source"


# ---------------------------------------------------------------------------
# error_payload — typed errors convert to structured {error: {...}}
# ---------------------------------------------------------------------------


class TestErrorPayload:
    def test_invalid_ticker_error_becomes_structured_payload(self, monkeypatch):
        from astock_data.errors import InvalidTickerError

        def _raise(*a, **k):
            raise InvalidTickerError("not a valid A-share ticker")

        monkeypatch.setattr("astock_data.api.resolve_ticker", _raise)
        server = _server_module()

        result = server.resolve_ticker("bogus")
        assert result == {
            "error": {
                "type": "InvalidTickerError",
                "message": "not a valid A-share ticker",
            }
        }
        # Must be JSON-serializable.
        json.dumps(result)

    def test_rate_limit_error_subtype_preserved(self, monkeypatch):
        from astock_data.errors import RateLimitError

        def _raise(*a, **k):
            raise RateLimitError("upstream 429")

        monkeypatch.setattr("astock_data.api.get_news", _raise)
        server = _server_module()

        result = server.get_news("000001", "2026-01-01", "2026-01-02")
        # The MOST SPECIFIC type name is reported (RateLimitError, not its
        # DataSourceError / AStockDataError parents).
        assert result["error"]["type"] == "RateLimitError"
        assert "429" in result["error"]["message"]

    def test_no_data_error_does_not_crash(self, monkeypatch):
        from astock_data.errors import NoDataError

        def _raise(*a, **k):
            raise NoDataError("empty")

        monkeypatch.setattr("astock_data.api.get_stock_data", _raise)
        server = _server_module()

        result = server.get_stock_data("000001", "2026-01-01", "2026-01-02")
        assert result["error"]["type"] == "NoDataError"
        # No stack-trace leakage — only the two structured keys.
        assert set(result) == {"error"}
        assert set(result["error"]) == {"type", "message"}

    def test_non_astock_error_propagates_uncaught(self, monkeypatch):
        """Only typed AStockDataError is converted; unexpected exceptions are
        NOT silently swallowed into an error payload (don't mask real bugs)."""
        monkeypatch.setattr(
            "astock_data.api.get_fundamentals",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        server = _server_module()
        with pytest.raises(RuntimeError, match="boom"):
            server.get_fundamentals("000001", "2026-01-02")


# ---------------------------------------------------------------------------
# import safety
# ---------------------------------------------------------------------------


def test_server_import_is_clean():
    """Importing the server must not pull forbidden heavy frameworks."""
    import astock_data.mcp.server as server

    import sys

    forbidden = [
        "langchain",
        "openai",
        "anthropic",
        "streamlit",
        "fastapi",
    ]
    loaded = set(sys.modules)
    for mod in forbidden:
        assert mod not in loaded, f"forbidden module '{mod}' was imported"

    # FastMCP + facade + errors are the only astock_data deps.
    assert hasattr(server, "mcp")
    assert server.mcp.name == "astock-data"


def test_main_guard_does_not_run_on_import():
    """Importing must not start the server (the ``mcp.run()`` guard)."""
    import astock_data.mcp.server as server  # noqa: F401

    # If the guard executed, the process would have blocked / errored.
    # Reaching this assertion means import returned cleanly.
    assert True


# ---------------------------------------------------------------------------
# utilities
# ---------------------------------------------------------------------------


def _input_schema(tool) -> dict:
    """Read the JSON input schema from a FastMCP Tool object across versions."""
    # FastMCP 3.x Tool stores it under ``parameters`` (Pydantic Field alias).
    schema = getattr(tool, "parameters", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    if isinstance(schema, dict):
        return schema
    # Some versions wrap it in a pydantic model — coerce.
    if hasattr(schema, "model_dump"):
        return schema.model_dump(mode="json")
    return {}
