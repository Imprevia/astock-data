from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from pydantic import BaseModel

from astock_data.models import (
    ConceptBlocksResult,
    DragonTigerResult,
    FinancialStatementResult,
    FundFlowResult,
    FundamentalsResult,
    GlobalNewsResult,
    HotStocksResult,
    IndicatorResult,
    IndustryComparisonResult,
    LockupExpiryResult,
    NewsResult,
    NorthboundFlowResult,
    ProfitForecastResult,
    ShareholderResult,
    StockDataResult,
    Ticker,
)

Renderer = Callable[[BaseModel], str]

NO_DATA_MESSAGE = "No data / 无数据"


def to_markdown(result: BaseModel) -> str:
    renderer = MARKDOWN_RENDERERS.get(type(result), _default_markdown)
    return renderer(result)


def to_text(result: BaseModel) -> str:
    renderer = TEXT_RENDERERS.get(type(result), _default_text)
    return renderer(result)


def _dump(result: BaseModel) -> dict[str, Any]:
    return result.model_dump(mode="json")


def _title(result: BaseModel) -> str:
    return type(result).__name__


def _metadata_lines(data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if "source" in data:
        lines.append(f"source: {data.get('source')}")
    if "retrieved_at" in data:
        lines.append(f"retrieved_at: {data.get('retrieved_at')}")
    return lines


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return ", ".join(f"{key}={_flatten(item)}" for key, item in value.items() if item is not None)
    if isinstance(value, list):
        return "; ".join(_flatten(item) for item in value if item is not None)
    return str(value)


def _present(value: Any) -> bool:
    return value not in (None, [], {})


def _first_columns(rows: Sequence[dict[str, Any]], limit: int = 6) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key, value in row.items():
            if key == "raw" or not _present(value):
                continue
            if key not in columns:
                columns.append(key)
            if len(columns) >= limit:
                return columns
    return columns


def _ordered_columns(rows: Sequence[dict[str, Any]], preferred: Sequence[str], limit: int = 8) -> list[str]:
    columns = [column for column in preferred if any(_present(row.get(column)) for row in rows)]
    for column in _first_columns(rows, limit=limit):
        if column not in columns:
            columns.append(column)
        if len(columns) >= limit:
            break
    return columns


def _markdown_escape(value: Any) -> str:
    return _flatten(value).replace("|", "\\|").replace("\n", " ")


def _markdown_table(rows: Sequence[dict[str, Any]], columns: Sequence[str] | None = None) -> list[str]:
    if not rows:
        return [NO_DATA_MESSAGE]
    table_columns = list(columns or _first_columns(rows))
    if not table_columns:
        return [NO_DATA_MESSAGE]
    lines = ["| " + " | ".join(table_columns) + " |", "| " + " | ".join("---" for _ in table_columns) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_escape(row.get(column)) for column in table_columns) + " |")
    return lines


def _text_table(rows: Sequence[dict[str, Any]], columns: Sequence[str] | None = None) -> list[str]:
    if not rows:
        return [NO_DATA_MESSAGE]
    table_columns = list(columns or _first_columns(rows))
    if not table_columns:
        return [NO_DATA_MESSAGE]
    widths = {column: len(column) for column in table_columns}
    for row in rows:
        for column in table_columns:
            widths[column] = max(widths[column], len(_flatten(row.get(column))))
    header = "  ".join(column.ljust(widths[column]) for column in table_columns)
    divider = "  ".join("-" * widths[column] for column in table_columns)
    body = ["  ".join(_flatten(row.get(column)).ljust(widths[column]) for column in table_columns) for row in rows]
    return [header, divider, *body]


def _pairs(data: dict[str, Any], keys: Iterable[str]) -> list[tuple[str, Any]]:
    return [(key, data.get(key)) for key in keys if _present(data.get(key))]


def _markdown_pairs(data: dict[str, Any], keys: Iterable[str] | None = None) -> list[str]:
    pairs = _pairs(data, keys or data.keys())
    return [f"- {key}: {_flatten(value)}" for key, value in pairs] or [NO_DATA_MESSAGE]


def _text_pairs(data: dict[str, Any], keys: Iterable[str] | None = None) -> list[str]:
    pairs = _pairs(data, keys or data.keys())
    return [f"{key}: {_flatten(value)}" for key, value in pairs] or [NO_DATA_MESSAGE]


def _markdown_section(title: str, lines: Sequence[str]) -> list[str]:
    return [f"## {title}", *(lines or [NO_DATA_MESSAGE])]


def _text_section(title: str, lines: Sequence[str]) -> list[str]:
    return [title, *(lines or [NO_DATA_MESSAGE])]


def _markdown_document(result: BaseModel, body: Sequence[str]) -> str:
    data = _dump(result)
    lines = [f"# {_title(result)}", *_metadata_lines(data), "", *body]
    return "\n".join(lines).strip() + "\n"


def _text_document(result: BaseModel, body: Sequence[str]) -> str:
    data = _dump(result)
    lines = [_title(result), *_metadata_lines(data), "", *body]
    return "\n".join(lines).strip() + "\n"


def _ticker_lines(data: dict[str, Any], markdown: bool) -> list[str]:
    ticker = data.get("ticker")
    pairs: dict[str, Any] = {}
    if isinstance(ticker, dict):
        pairs.update({f"ticker_{key}": value for key, value in ticker.items()})
    elif ticker:
        pairs["ticker"] = ticker
    if data.get("name"):
        pairs["name"] = data.get("name")
    return _markdown_pairs(pairs) if markdown else _text_pairs(pairs)


def _stock_markdown(result: BaseModel) -> str:
    data = _dump(result)
    rows = data.get("bars") or []
    body = [*_markdown_section("Ticker", _ticker_lines(data, markdown=True)), "", *_markdown_section("OHLCV", _markdown_table(rows, ("date", "open", "high", "low", "close", "volume")))]
    return _markdown_document(result, body)


def _stock_text(result: BaseModel) -> str:
    data = _dump(result)
    rows = data.get("bars") or []
    body = [*_text_section("Ticker", _ticker_lines(data, markdown=False)), "", *_text_section("OHLCV", _text_table(rows, ("date", "open", "high", "low", "close", "volume")))]
    return _text_document(result, body)


def _indicator_markdown(result: BaseModel) -> str:
    data = _dump(result)
    summary = _markdown_pairs(data, ("indicator", "description"))
    body = [*_markdown_section("Indicator", summary), "", *_markdown_section("Values", _markdown_table(data.get("points") or [], ("date", "value")))]
    return _markdown_document(result, body)


def _indicator_text(result: BaseModel) -> str:
    data = _dump(result)
    summary = _text_pairs(data, ("indicator", "description"))
    body = [*_text_section("Indicator", summary), "", *_text_section("Values", _text_table(data.get("points") or [], ("date", "value")))]
    return _text_document(result, body)


def _fundamentals_markdown(result: BaseModel) -> str:
    data = _dump(result)
    quote_keys = ("price", "change_pct", "pe_ttm", "pe_static", "pb", "market_cap_yi", "float_market_cap_yi", "turnover_pct", "limit_up", "limit_down")
    body = [
        *_markdown_section("Quote Snapshot", _markdown_pairs(data.get("quote") or {}, quote_keys)),
        "",
        *_markdown_section("Financial Snapshot", _markdown_pairs(data.get("snapshot") or {})),
        "",
        *_markdown_section("Consensus Forecast", _markdown_pairs(data.get("consensus_forecast") or {})),
    ]
    return _markdown_document(result, body)


def _fundamentals_text(result: BaseModel) -> str:
    data = _dump(result)
    quote_keys = ("price", "change_pct", "pe_ttm", "pe_static", "pb", "market_cap_yi", "float_market_cap_yi", "turnover_pct", "limit_up", "limit_down")
    body = [
        *_text_section("Quote Snapshot", _text_pairs(data.get("quote") or {}, quote_keys)),
        "",
        *_text_section("Financial Snapshot", _text_pairs(data.get("snapshot") or {})),
        "",
        *_text_section("Consensus Forecast", _text_pairs(data.get("consensus_forecast") or {})),
    ]
    return _text_document(result, body)


def _financial_statement_markdown(result: BaseModel) -> str:
    data = _dump(result)
    rows = [{"report_date": row.get("report_date"), **(row.get("fields") or {})} for row in data.get("rows") or []]
    columns = _ordered_columns(rows, ("report_date", "revenue", "net_profit", "total_assets", "operating_cash_flow"))
    body = [*_markdown_section("Statement", _markdown_pairs(data, ("ticker", "name", "statement_type", "freq"))), "", *_markdown_section("Rows", _markdown_table(rows, columns))]
    return _markdown_document(result, body)


def _financial_statement_text(result: BaseModel) -> str:
    data = _dump(result)
    rows = [{"report_date": row.get("report_date"), **(row.get("fields") or {})} for row in data.get("rows") or []]
    columns = _ordered_columns(rows, ("report_date", "revenue", "net_profit", "total_assets", "operating_cash_flow"))
    body = [*_text_section("Statement", _text_pairs(data, ("ticker", "name", "statement_type", "freq"))), "", *_text_section("Rows", _text_table(rows, columns))]
    return _text_document(result, body)


def _news_markdown(result: BaseModel) -> str:
    data = _dump(result)
    items = data.get("items") or []
    lines = [f"{index}. **{item.get('title', '')}** — {item.get('source') or ''} — {item.get('time') or ''}\n   {item.get('url') or ''}" for index, item in enumerate(items, 1)]
    return _markdown_document(result, _markdown_section("News", lines or [NO_DATA_MESSAGE]))


def _news_text(result: BaseModel) -> str:
    data = _dump(result)
    items = data.get("items") or []
    lines = [f"{index}. {item.get('title', '')} | source: {item.get('source') or ''} | time: {item.get('time') or ''} | url: {item.get('url') or ''}" for index, item in enumerate(items, 1)]
    return _text_document(result, _text_section("News", lines or [NO_DATA_MESSAGE]))


def _shareholder_markdown(result: BaseModel) -> str:
    data = _dump(result)
    body = [*_markdown_section("Summary", _markdown_pairs(data, ("ticker", "name", "content"))), "", *_markdown_section("Sections", _markdown_pairs(data.get("sections") or {}))]
    return _markdown_document(result, body)


def _shareholder_text(result: BaseModel) -> str:
    data = _dump(result)
    body = [*_text_section("Summary", _text_pairs(data, ("ticker", "name", "content"))), "", *_text_section("Sections", _text_pairs(data.get("sections") or {}))]
    return _text_document(result, body)


def _profit_forecast_markdown(result: BaseModel) -> str:
    data = _dump(result)
    rows = data.get("rows") or []
    columns = _ordered_columns(rows, ("year", "eps", "revenue", "net_profit", "pe"))
    body = [*_markdown_section("Valuation", _markdown_pairs(data, ("ticker", "name", "forward_pe", "peg"))), "", *_markdown_section("Forecast Rows", _markdown_table(rows, columns))]
    return _markdown_document(result, body)


def _profit_forecast_text(result: BaseModel) -> str:
    data = _dump(result)
    rows = data.get("rows") or []
    columns = _ordered_columns(rows, ("year", "eps", "revenue", "net_profit", "pe"))
    body = [*_text_section("Valuation", _text_pairs(data, ("ticker", "name", "forward_pe", "peg"))), "", *_text_section("Forecast Rows", _text_table(rows, columns))]
    return _text_document(result, body)


def _hot_stocks_markdown(result: BaseModel) -> str:
    data = _dump(result)
    body = [*_markdown_section("Themes", _markdown_pairs(data.get("theme_frequency") or {})), "", *_markdown_section("Hot Stocks", _markdown_table(data.get("items") or [], ("code", "name", "reason", "zhangfu", "huanshou", "chengjiaoe")))]
    return _markdown_document(result, body)


def _hot_stocks_text(result: BaseModel) -> str:
    data = _dump(result)
    body = [*_text_section("Themes", _text_pairs(data.get("theme_frequency") or {})), "", *_text_section("Hot Stocks", _text_table(data.get("items") or [], ("code", "name", "reason", "zhangfu", "huanshou", "chengjiaoe")))]
    return _text_document(result, body)


def _northbound_markdown(result: BaseModel) -> str:
    data = _dump(result)
    body = [*_markdown_section("Signal", _markdown_pairs(data, ("signal",))), "", *_markdown_section("Realtime", _markdown_table(data.get("realtime") or [])), "", *_markdown_section("History", _markdown_table(data.get("history") or []))]
    return _markdown_document(result, body)


def _northbound_text(result: BaseModel) -> str:
    data = _dump(result)
    body = [*_text_section("Signal", _text_pairs(data, ("signal",))), "", *_text_section("Realtime", _text_table(data.get("realtime") or [])), "", *_text_section("History", _text_table(data.get("history") or []))]
    return _text_document(result, body)


def _concepts_markdown(result: BaseModel) -> str:
    data = _dump(result)
    body = [
        *_markdown_section("Tags", _markdown_pairs({"concept_tags": data.get("concept_tags")})),
        "",
        *_markdown_section("Concepts", _markdown_table(data.get("concepts") or [], ("name", "ratio", "describe"))),
        "",
        *_markdown_section("Industries", _markdown_table(data.get("industries") or [], ("name", "ratio", "describe"))),
        "",
        *_markdown_section("Regions", _markdown_table(data.get("regions") or [], ("name", "ratio", "describe"))),
    ]
    return _markdown_document(result, body)


def _concepts_text(result: BaseModel) -> str:
    data = _dump(result)
    body = [
        *_text_section("Tags", _text_pairs({"concept_tags": data.get("concept_tags")})),
        "",
        *_text_section("Concepts", _text_table(data.get("concepts") or [], ("name", "ratio", "describe"))),
        "",
        *_text_section("Industries", _text_table(data.get("industries") or [], ("name", "ratio", "describe"))),
        "",
        *_text_section("Regions", _text_table(data.get("regions") or [], ("name", "ratio", "describe"))),
    ]
    return _text_document(result, body)


def _fund_flow_markdown(result: BaseModel) -> str:
    data = _dump(result)
    columns = ("time", "main_net_inflow", "super_large_net_inflow", "large_net_inflow", "medium_net_inflow", "small_net_inflow")
    body = [*_markdown_section("Signal", _markdown_pairs(data, ("signal",))), "", *_markdown_section("Minute Flow", _markdown_table(data.get("minute") or [], columns)), "", *_markdown_section("Daily Flow", _markdown_table(data.get("daily") or [], columns))]
    return _markdown_document(result, body)


def _fund_flow_text(result: BaseModel) -> str:
    data = _dump(result)
    columns = ("time", "main_net_inflow", "super_large_net_inflow", "large_net_inflow", "medium_net_inflow", "small_net_inflow")
    body = [*_text_section("Signal", _text_pairs(data, ("signal",))), "", *_text_section("Minute Flow", _text_table(data.get("minute") or [], columns)), "", *_text_section("Daily Flow", _text_table(data.get("daily") or [], columns))]
    return _text_document(result, body)


def _dragon_tiger_markdown(result: BaseModel) -> str:
    data = _dump(result)
    event_columns = ("date", "reason", "close", "change_pct", "net_buy", "amount")
    seat_columns = ("seat_name", "buy_amount", "sell_amount", "net_amount")
    body = [
        *_markdown_section("Institution Flow", _markdown_pairs(data.get("institution_flow") or {})),
        "",
        *_markdown_section("Events", _markdown_table(data.get("events") or [], event_columns)),
        "",
        *_markdown_section("Buy Seats", _markdown_table(data.get("buy_seats") or [], seat_columns)),
        "",
        *_markdown_section("Sell Seats", _markdown_table(data.get("sell_seats") or [], seat_columns)),
    ]
    return _markdown_document(result, body)


def _dragon_tiger_text(result: BaseModel) -> str:
    data = _dump(result)
    event_columns = ("date", "reason", "close", "change_pct", "net_buy", "amount")
    seat_columns = ("seat_name", "buy_amount", "sell_amount", "net_amount")
    body = [
        *_text_section("Institution Flow", _text_pairs(data.get("institution_flow") or {})),
        "",
        *_text_section("Events", _text_table(data.get("events") or [], event_columns)),
        "",
        *_text_section("Buy Seats", _text_table(data.get("buy_seats") or [], seat_columns)),
        "",
        *_text_section("Sell Seats", _text_table(data.get("sell_seats") or [], seat_columns)),
    ]
    return _text_document(result, body)


def _lockup_markdown(result: BaseModel) -> str:
    data = _dump(result)
    columns = ("date", "holder", "shares", "market_value_yi", "ratio")
    body = [*_markdown_section("History", _markdown_table(data.get("history") or [], columns)), "", *_markdown_section("Upcoming", _markdown_table(data.get("upcoming") or [], columns))]
    return _markdown_document(result, body)


def _lockup_text(result: BaseModel) -> str:
    data = _dump(result)
    columns = ("date", "holder", "shares", "market_value_yi", "ratio")
    body = [*_text_section("History", _text_table(data.get("history") or [], columns)), "", *_text_section("Upcoming", _text_table(data.get("upcoming") or [], columns))]
    return _text_document(result, body)


def _industry_markdown(result: BaseModel) -> str:
    data = _dump(result)
    columns = ("code", "name", "industry", "price", "change_pct", "pe_ttm", "pb", "market_cap_yi")
    body = [*_markdown_section("Target", _markdown_pairs(data, ("target_industry",))), "", *_markdown_section("Industry Rows", _markdown_table(data.get("rows") or [], columns))]
    return _markdown_document(result, body)


def _industry_text(result: BaseModel) -> str:
    data = _dump(result)
    columns = ("code", "name", "industry", "price", "change_pct", "pe_ttm", "pb", "market_cap_yi")
    body = [*_text_section("Target", _text_pairs(data, ("target_industry",))), "", *_text_section("Industry Rows", _text_table(data.get("rows") or [], columns))]
    return _text_document(result, body)


def _default_markdown(result: BaseModel) -> str:
    return _markdown_document(result, _markdown_pairs(_dump(result)))


def _default_text(result: BaseModel) -> str:
    return _text_document(result, _text_pairs(_dump(result)))


MARKDOWN_RENDERERS: dict[type[BaseModel], Renderer] = {
    StockDataResult: _stock_markdown,
    IndicatorResult: _indicator_markdown,
    FundamentalsResult: _fundamentals_markdown,
    FinancialStatementResult: _financial_statement_markdown,
    NewsResult: _news_markdown,
    GlobalNewsResult: _news_markdown,
    ShareholderResult: _shareholder_markdown,
    ProfitForecastResult: _profit_forecast_markdown,
    HotStocksResult: _hot_stocks_markdown,
    NorthboundFlowResult: _northbound_markdown,
    ConceptBlocksResult: _concepts_markdown,
    FundFlowResult: _fund_flow_markdown,
    DragonTigerResult: _dragon_tiger_markdown,
    LockupExpiryResult: _lockup_markdown,
    IndustryComparisonResult: _industry_markdown,
    Ticker: _default_markdown,
}

TEXT_RENDERERS: dict[type[BaseModel], Renderer] = {
    StockDataResult: _stock_text,
    IndicatorResult: _indicator_text,
    FundamentalsResult: _fundamentals_text,
    FinancialStatementResult: _financial_statement_text,
    NewsResult: _news_text,
    GlobalNewsResult: _news_text,
    ShareholderResult: _shareholder_text,
    ProfitForecastResult: _profit_forecast_text,
    HotStocksResult: _hot_stocks_text,
    NorthboundFlowResult: _northbound_text,
    ConceptBlocksResult: _concepts_text,
    FundFlowResult: _fund_flow_text,
    DragonTigerResult: _dragon_tiger_text,
    LockupExpiryResult: _lockup_text,
    IndustryComparisonResult: _industry_text,
    Ticker: _default_text,
}
