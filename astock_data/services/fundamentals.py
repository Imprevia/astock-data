from __future__ import annotations

import datetime as dt
import io
from collections.abc import Mapping
from typing import Any

import pandas as pd

from astock_data.cache import SQLiteStructuredCache
from astock_data.clients.eastmoney import (
    PUSH2_STOCK_GET_PATH,
    EastmoneyClient,
)
from astock_data.clients.sina import SinaClient
from astock_data.clients.tencent import TencentClient
from astock_data.clients.tdx import TdxClient
from astock_data.config import AStockSettings, get_settings
from astock_data.errors import DataSourceError
from astock_data.models import FinancialRow, FinancialStatementResult, FundamentalsResult, Quote
from astock_data.resolver import resolve_ticker

__all__ = [
    "get_balance_sheet",
    "get_cashflow",
    "get_fundamentals",
    "get_income_statement",
]


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _trade_date(curr_date: str | None) -> str:
    if curr_date:
        return curr_date
    return _now_utc().date().isoformat()


def _to_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _build_cache(
    settings: AStockSettings | None,
    cache: SQLiteStructuredCache | None,
) -> SQLiteStructuredCache:
    if cache is not None:
        return cache
    cfg = settings if settings is not None else get_settings()
    return SQLiteStructuredCache(base_dir=cfg.cache_dir, ttl=dt.timedelta(hours=cfg.structured_cache_ttl_hours))


def _pick_first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _quote_from_tencent(payload: Mapping[str, Any]) -> Quote:
    return Quote(
        price=payload.get("price"),
        pe_ttm=payload.get("pe_ttm"),
        pe_static=payload.get("pe_static"),
        pb=payload.get("pb"),
        market_cap_yi=payload.get("mcap_yi"),
        float_market_cap_yi=payload.get("float_mcap_yi"),
        turnover_pct=payload.get("turnover_pct"),
        change_pct=payload.get("change_pct"),
        limit_up=payload.get("limit_up"),
        limit_down=payload.get("limit_down"),
    )


def _normalize_tdx_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(snapshot)
    raw = normalized.pop("_raw", {})
    if isinstance(raw, Mapping):
        normalized["raw"] = dict(raw)
    return normalized


def _normalize_eastmoney_snapshot(payload: Mapping[str, Any], code: str) -> dict[str, Any]:
    data: Mapping[str, Any] | None = None
    if isinstance(payload.get("data"), Mapping):
        data = payload["data"]
    elif isinstance(payload.get("data"), list):
        items = [item for item in payload["data"] if isinstance(item, Mapping)]
        if items:
            data = items[0]
    elif isinstance(payload, Mapping):
        data = payload
    if not data:
        return {"code": code}

    def _shares_value() -> Any:
        return _pick_first(
            data,
            "f84",
            "f85",
            "f116",
            "f117",
            "total_shares",
            "float_shares",
            "totalShare",
            "floatShare",
        )

    listing_date = _pick_first(data, "f26", "f58", "listDate", "上市日期")
    industry = _pick_first(data, "f100", "f127", "industry", "行业")
    name = _pick_first(data, "f14", "name", "证券简称")
    return {
        "code": code,
        "name": name,
        "industry": industry,
        "listing_date": listing_date,
        "shares": _shares_value(),
        "raw": dict(data),
    }


def _fetch_consensus_forecast(code: str, ths_session: Any | None) -> dict[str, Any] | None:
    if ths_session is None:
        return None
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    response = ths_session.get(url, timeout=15)
    html = getattr(response, "text", None)
    if html is None:
        content = getattr(response, "content", b"")
        html = content.decode("utf-8", errors="ignore")
    tables = pd.read_html(io.StringIO(html))
    if not tables:
        return None
    rows: list[dict[str, Any]] = []
    for table in tables:
        if table.empty:
            continue
        rows.extend(table.where(pd.notna(table), None).to_dict(orient="records"))
    if not rows:
        return None
    return {"source": "ths", "rows": rows[:8]}


def _statement_from_rows(
    ticker: str,
    name: str | None,
    statement_type: str,
    freq: str,
    rows: list[dict[str, Any]],
    retrieved_at: dt.datetime,
) -> FinancialStatementResult:
    return FinancialStatementResult(
        source="sina",
        retrieved_at=retrieved_at,
        ticker=ticker,
        name=name,
        statement_type=statement_type,  # type: ignore[arg-type]
        freq=freq,
        rows=[FinancialRow(report_date=row["report_date"], fields=row["fields"]) for row in rows],
    )


def _get_statement(
    ticker: str,
    report_type: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
    *,
    settings: AStockSettings | None = None,
    sina: SinaClient | None = None,
    cache: SQLiteStructuredCache | None = None,
) -> FinancialStatementResult:
    resolved = resolve_ticker(ticker)
    code = resolved.code
    trade_date = _trade_date(curr_date)
    cache_obj = _build_cache(settings, cache)

    cache_kind = f"{report_type}:{freq}"
    cached = cache_obj.read(cache_kind, code, trade_date)
    if cached:
        rows = [
            {"report_date": row["report_date"], "fields": row["fields"]}
            for row in cached.get("rows", [])
            if isinstance(row, Mapping)
        ]
        return _statement_from_rows(
            ticker=code,
            name=resolved.name,
            statement_type=report_type,
            freq=freq,
            rows=rows,
            retrieved_at=dt.datetime.fromisoformat(cached["retrieved_at"]),
        )

    client = sina if sina is not None else SinaClient()
    raw_rows = client.financial_report(code, report_type, freq)
    threshold = _to_date(curr_date) if curr_date else _now_utc().date()
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        report_date = _to_date(row.get("report_date"))
        if report_date is None or report_date > threshold:
            continue
        if freq == "annual" and report_date.month != 12:
            continue
        fields = row.get("fields") if isinstance(row.get("fields"), Mapping) else {}
        rows.append({"report_date": report_date, "fields": dict(fields)})
        if len(rows) >= 8:
            break

    result = _statement_from_rows(
        ticker=code,
        name=resolved.name,
        statement_type=report_type,
        freq=freq,
        rows=rows,
        retrieved_at=_now_utc(),
    )
    cache_obj.write(
        cache_kind,
        code,
        trade_date,
        {
            "retrieved_at": result.retrieved_at.isoformat(),
            "rows": [
                {"report_date": row.report_date.isoformat(), "fields": row.fields}
                for row in result.rows
            ],
        },
    )
    return result


def get_balance_sheet(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
    *,
    settings: AStockSettings | None = None,
    sina: SinaClient | None = None,
    cache: SQLiteStructuredCache | None = None,
) -> FinancialStatementResult:
    return _get_statement(
        ticker,
        "balance",
        freq,
        curr_date,
        settings=settings,
        sina=sina,
        cache=cache,
    )


def get_cashflow(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
    *,
    settings: AStockSettings | None = None,
    sina: SinaClient | None = None,
    cache: SQLiteStructuredCache | None = None,
) -> FinancialStatementResult:
    return _get_statement(
        ticker,
        "cashflow",
        freq,
        curr_date,
        settings=settings,
        sina=sina,
        cache=cache,
    )


def get_income_statement(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
    *,
    settings: AStockSettings | None = None,
    sina: SinaClient | None = None,
    cache: SQLiteStructuredCache | None = None,
) -> FinancialStatementResult:
    return _get_statement(
        ticker,
        "income",
        freq,
        curr_date,
        settings=settings,
        sina=sina,
        cache=cache,
    )


def get_fundamentals(
    ticker: str,
    curr_date: str | None = None,
    *,
    settings: AStockSettings | None = None,
    tdx: TdxClient | None = None,
    tencent: TencentClient | None = None,
    eastmoney: EastmoneyClient | None = None,
    ths_session: Any | None = None,
    cache: SQLiteStructuredCache | None = None,
) -> FundamentalsResult:
    resolved = resolve_ticker(ticker)
    code = resolved.code
    trade_date = _trade_date(curr_date)
    cache_obj = _build_cache(settings, cache)

    cached = cache_obj.read("fundamentals", code, trade_date)
    if cached:
        quote_data = cached.get("quote") or {}
        result = FundamentalsResult(
            source="composite",
            retrieved_at=dt.datetime.fromisoformat(cached["retrieved_at"]),
            ticker=code,
            name=cached.get("name") or resolved.name,
            quote=Quote(**quote_data),
            snapshot=cached.get("snapshot"),
            consensus_forecast=cached.get("consensus_forecast"),
            raw=None,
            warnings=list(cached.get("warnings", [])),
        )
        return result

    warnings: list[str] = []
    quote = Quote()
    snapshot: dict[str, Any] = {}
    consensus_forecast: dict[str, Any] | None = None
    name = resolved.name

    quote_payload: dict[str, Any] = {}
    try:
        client = tencent if tencent is not None else TencentClient()
        quote_map = client.quote([code])
        quote_payload = quote_map.get(code, {}) if isinstance(quote_map, Mapping) else {}
        if isinstance(quote_payload, Mapping):
            quote = _quote_from_tencent(quote_payload)
            name = quote_payload.get("name") or name
        else:
            quote_payload = {}
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Tencent quote unavailable: {exc}")

    tdx_payload: dict[str, Any] = {}
    try:
        client = tdx if tdx is not None else TdxClient()
        tdx_payload = client.financial_snapshot(code)
        if isinstance(tdx_payload, Mapping):
            snapshot.update(_normalize_tdx_snapshot(tdx_payload))
            name = tdx_payload.get("name") or name
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Tdx financial snapshot unavailable: {exc}")

    eastmoney_payload: dict[str, Any] = {}
    try:
        client = eastmoney if eastmoney is not None else EastmoneyClient(settings=settings)
        secid = f"{'1' if code.startswith('6') else '0'}.{code}"
        eastmoney_payload = client.push2(
            PUSH2_STOCK_GET_PATH,
            {
                "secid": secid,
                "fields": "f12,f14,f26,f58,f84,f100,f127",
                "ut": "7eea3edcaed734bea9cbfc24409ed989",
            },
        )
        if isinstance(eastmoney_payload, Mapping):
            em_snapshot = _normalize_eastmoney_snapshot(eastmoney_payload, code)
            snapshot.update({k: v for k, v in em_snapshot.items() if k != "raw" and v is not None})
            snapshot.setdefault("eastmoney", em_snapshot)
            name = em_snapshot.get("name") or name
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Eastmoney stock info unavailable: {exc}")

    try:
        consensus_forecast = _fetch_consensus_forecast(code, ths_session)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"THS EPS forecast unavailable: {exc}")

    required_success = any([quote_payload, tdx_payload, eastmoney_payload])
    if not required_success:
        raise DataSourceError(f"All fundamentals sources failed for {code}: {'; '.join(warnings) if warnings else 'no data'}")

    result = FundamentalsResult(
        source="composite",
        retrieved_at=_now_utc(),
        ticker=code,
        name=name,
        quote=quote,
        snapshot={**snapshot, "tencent": dict(quote_payload) if isinstance(quote_payload, Mapping) else {}, "eastmoney": snapshot.get("eastmoney")},
        consensus_forecast=consensus_forecast,
        raw=None,
        warnings=warnings,
    )
    cache_obj.write(
        "fundamentals",
        code,
        trade_date,
        {
            "retrieved_at": result.retrieved_at.isoformat(),
            "ticker": result.ticker,
            "name": result.name,
            "quote": result.quote.model_dump(mode="json"),
            "snapshot": result.snapshot,
            "consensus_forecast": result.consensus_forecast,
            "warnings": result.warnings,
        },
    )
    return result
