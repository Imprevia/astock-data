from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from astock_data.clients.eastmoney import (
    EastmoneyClient,
    PUSH2HIS_FFLOW_DAYKLINE_PATH,
    PUSH2_CLIST_PATH,
    PUSH2_FFLOW_KLINE_PATH,
)
from astock_data.config import AStockSettings, get_settings
from astock_data.models import (
    ConceptBlock,
    ConceptBlocksResult,
    DragonTigerEvent,
    DragonTigerResult,
    DragonTigerSeat,
    FundFlowResult,
    FundFlowRow,
    IndustryComparisonResult,
    IndustryRow,
    LockupExpiryResult,
    LockupRecord,
)
from astock_data.models.signals import SectorFundFlow, SectorFundFlowResult
from astock_data.resolver import resolve_ticker


def _now_utc() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def _eastmoney_client(
    eastmoney: EastmoneyClient | None,
    settings: AStockSettings | None,
) -> EastmoneyClient:
    if eastmoney is not None:
        return eastmoney
    return EastmoneyClient(settings=settings or get_settings())


def _secid(code: str) -> str:
    return f"1.{code}" if code.startswith("6") else f"0.{code}"


def _float_or_none(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_or_none(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _payload_klines(payload: Mapping[str, Any]) -> list[str]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    klines = data.get("klines")
    if not isinstance(klines, list):
        return []
    return [line for line in klines if isinstance(line, str)]


def _flow_row(line: str) -> FundFlowRow | None:
    parts = line.split(",")
    if len(parts) < 6:
        return None
    return FundFlowRow(
        time=parts[0],
        main_net_inflow=_float_or_none(parts[1]),
        small_net_inflow=_float_or_none(parts[2]),
        medium_net_inflow=_float_or_none(parts[3]),
        large_net_inflow=_float_or_none(parts[4]),
        super_large_net_inflow=_float_or_none(parts[5]),
        raw={"line": line},
    )


def _flow_rows(lines: list[str]) -> list[FundFlowRow]:
    rows: list[FundFlowRow] = []
    for line in lines:
        row = _flow_row(line)
        if row is not None:
            rows.append(row)
    return rows


def _fund_signal(rows: list[FundFlowRow]) -> str | None:
    for row in reversed(rows):
        value = row.main_net_inflow
        if value is None:
            continue
        if value > 0:
            return "INFLOW"
        if value < 0:
            return "OUTFLOW"
        return None
    return None


def _concept_block(row: Mapping[str, Any]) -> ConceptBlock | None:
    name = str(row.get("name") or row.get("f14") or "").strip()
    if not name:
        return None
    return ConceptBlock(
        name=name,
        ratio=_float_or_none(row.get("ratio") or row.get("change_pct") or row.get("f3")),
        describe=row.get("describe") or row.get("direction") or row.get("f128"),
    )


def _dragon_event(row: Mapping[str, Any]) -> DragonTigerEvent:
    return DragonTigerEvent(
        date=_date_or_none(row.get("TRADE_DATE")),
        reason=row.get("EXPLANATION") or row.get("BILLBOARD_EXPLANATION"),
        close=_float_or_none(row.get("CLOSE_PRICE") or row.get("CLOSE")),
        change_pct=_float_or_none(row.get("CHANGE_RATE") or row.get("CHANGE_PCT")),
        net_buy=_float_or_none(row.get("BILLBOARD_NET_AMT") or row.get("NET_BUY")),
        amount=_float_or_none(row.get("BILLBOARD_BUY_AMT") or row.get("DEAL_AMT") or row.get("AMOUNT")),
        raw=dict(row),
    )


def _dragon_seat(row: Mapping[str, Any]) -> DragonTigerSeat:
    return DragonTigerSeat(
        seat_name=row.get("OPERATEDEPT_NAME") or row.get("SEAT_NAME"),
        buy_amount=_float_or_none(row.get("BUY") or row.get("BUY_AMT")),
        sell_amount=_float_or_none(row.get("SELL") or row.get("SELL_AMT")),
        net_amount=_float_or_none(row.get("NET") or row.get("NET_AMT")),
        raw=dict(row),
    )


def _institution_flow(
    buy_rows: list[dict[str, Any]],
    sell_rows: list[dict[str, Any]],
) -> dict[str, float] | None:
    institution_buy = 0.0
    institution_sell = 0.0
    for row in buy_rows:
        if str(row.get("OPERATEDEPT_CODE", "")) == "0" or "机构" in str(row.get("OPERATEDEPT_NAME", "")):
            institution_buy += _float_or_none(row.get("BUY")) or 0.0
    for row in sell_rows:
        if str(row.get("OPERATEDEPT_CODE", "")) == "0" or "机构" in str(row.get("OPERATEDEPT_NAME", "")):
            institution_sell += _float_or_none(row.get("SELL")) or 0.0
    if institution_buy == 0 and institution_sell == 0:
        return None
    return {
        "buy_amount": institution_buy,
        "sell_amount": institution_sell,
        "net_amount": institution_buy - institution_sell,
    }


def _lockup_record(row: Mapping[str, Any]) -> LockupRecord:
    return LockupRecord(
        date=_date_or_none(row.get("FREE_DATE")),
        holder=row.get("HOLDER_NAME") or row.get("LIMITED_STOCK_TYPE"),
        shares=_float_or_none(row.get("FREE_SHARES_NUM") or row.get("FREE_SHARES")),
        market_value_yi=_float_or_none(row.get("FREE_MARKET_CAP") or row.get("FREE_MARKET_VALUE")),
        ratio=_float_or_none(row.get("FREE_RATIO")),
        raw=dict(row),
    )


def _diff_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return []
    diff = data.get("diff")
    if not isinstance(diff, list):
        return []
    return [row for row in diff if isinstance(row, dict)]


def _industry_row(row: Mapping[str, Any]) -> IndustryRow | None:
    name = str(row.get("f14") or "").strip()
    if not name:
        return None
    return IndustryRow(
        code=str(row.get("f12") or "") or None,
        name=name,
        industry=name,
        change_pct=_float_or_none(row.get("f3")),
        raw={
            **dict(row),
            "up_count": row.get("f104"),
            "down_count": row.get("f105"),
            "leader": row.get("f140"),
        },
    )


def get_concept_blocks(
    ticker: str,
    *,
    eastmoney: EastmoneyClient | None = None,
    settings: AStockSettings | None = None,
) -> ConceptBlocksResult:
    resolved = resolve_ticker(ticker)
    client = _eastmoney_client(eastmoney, settings)
    now = _now_utc()
    raw_blocks = client.concept_blocks(resolved.code)

    concepts: list[ConceptBlock] = []
    industries: list[ConceptBlock] = []
    regions: list[ConceptBlock] = []
    for raw in raw_blocks:
        block = _concept_block(raw)
        if block is None:
            continue
        name = block.name
        if "地域" in name or name.endswith("省") or name.endswith("市"):
            regions.append(block)
        elif "行业" in name or "申万" in name or "证监会" in name:
            industries.append(block)
        else:
            concepts.append(block)

    return ConceptBlocksResult(
        source="eastmoney slist",
        retrieved_at=now,
        ticker=resolved.code,
        name=resolved.name,
        concepts=concepts,
        industries=industries,
        regions=regions,
        concept_tags=[item.name for item in concepts],
        raw={"blocks": raw_blocks},
    )


def get_fund_flow(
    ticker: str,
    curr_date: str,
    include_history: bool = True,
    *,
    eastmoney: EastmoneyClient | None = None,
    settings: AStockSettings | None = None,
) -> FundFlowResult:
    resolved = resolve_ticker(ticker)
    client = _eastmoney_client(eastmoney, settings)
    secid = _secid(resolved.code)
    now = _now_utc()
    minute_payload = client.push2(
        PUSH2_FFLOW_KLINE_PATH,
        {
            "secid": secid,
            "klt": 1,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57",
        },
    )
    minute = _flow_rows(_payload_klines(minute_payload))

    daily: list[FundFlowRow] | None = None
    if include_history:
        history_payload = client.push2his(
            PUSH2HIS_FFLOW_DAYKLINE_PATH,
            {
                "secid": secid,
                "lmt": 20,
                "klt": 101,
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57",
            },
        )
        daily = _flow_rows(_payload_klines(history_payload))

    return FundFlowResult(
        source="eastmoney push2",
        retrieved_at=now,
        ticker=resolved.code,
        name=resolved.name,
        minute=minute,
        daily=daily,
        signal=_fund_signal(minute),
        raw={"curr_date": curr_date, "secid": secid},
    )


def get_sector_fund_flow(
    curr_date: str = "",
    days: int = 5,
) -> SectorFundFlowResult:
    """行业板块主力资金流：当日排行 + 近 N 日历史。"""
    from astock_data.clients import eastmoney as _em

    warnings: list[str] = []
    sectors: list[SectorFundFlow] = []

    try:
        rank_rows = _em.fetch_sector_fund_flow_rank()
    except Exception as exc:  # noqa: BLE001 - upstream errors degrade to warnings
        warnings.append(f"板块资金排行接口失败：{exc}")
        return SectorFundFlowResult(
            date=curr_date or dt.date.today().isoformat(),
            sectors=[],
            signal="",
            warnings=warnings,
        )

    if not rank_rows:
        warnings.append("板块资金排行数据为空（可能非交易日）。")
        return SectorFundFlowResult(
            date=curr_date or dt.date.today().isoformat(),
            sectors=[],
            signal="",
            warnings=warnings,
        )

    for row in rank_rows:
        code = str(row.get("code") or "")
        secid = f"90.{code.lower()}"
        try:
            history = _em.fetch_sector_fund_flow_history(secid, days=days)
        except Exception as exc:  # noqa: BLE001 - keep rank data even if history fails
            history = []
            warnings.append(f"{row.get('name', '?')} 历史资金拉取失败：{exc}")

        sectors.append(
            SectorFundFlow(
                name=str(row.get("name") or ""),
                code=code,
                main_net_inflow=_float_or_none(row.get("main_net_inflow")),
                change_pct=_float_or_none(row.get("change_pct")),
                history=history,
            )
        )

    top3 = "、".join(sector.name for sector in sectors[:3] if sector.name)
    signal = f"主力净流入Top3：{top3}" if top3 else ""
    date = curr_date or (
        sectors[0].history[-1]["date"] if sectors and sectors[0].history else dt.date.today().isoformat()
    )
    return SectorFundFlowResult(date=date, sectors=sectors, signal=signal, warnings=warnings)


def get_dragon_tiger_board(
    ticker: str,
    trade_date: str,
    look_back_days: int = 30,
    *,
    eastmoney: EastmoneyClient | None = None,
    settings: AStockSettings | None = None,
) -> DragonTigerResult:
    resolved = resolve_ticker(ticker)
    client = _eastmoney_client(eastmoney, settings)
    now = _now_utc()
    end_date = dt.date.fromisoformat(trade_date)
    start_date = end_date - dt.timedelta(days=look_back_days)
    filter_str = (
        f"(TRADE_DATE>='{start_date.isoformat()}')"
        f"(TRADE_DATE<='{trade_date}')"
        f"(SECURITY_CODE=\"{resolved.code}\")"
    )
    event_rows = client.datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=filter_str,
        page_size=50,
        sort_columns="TRADE_DATE",
        sort_types="-1",
    )
    latest_date = str(event_rows[0].get("TRADE_DATE", ""))[:10] if event_rows else trade_date
    seat_filter = f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{resolved.code}\")"
    buy_rows = client.datacenter(
        "RPT_BILLBOARD_DAILYDETAILSBUY",
        filter_str=seat_filter,
        page_size=10,
        sort_columns="BUY",
        sort_types="-1",
    )
    sell_rows = client.datacenter(
        "RPT_BILLBOARD_DAILYDETAILSSELL",
        filter_str=seat_filter,
        page_size=10,
        sort_columns="SELL",
        sort_types="-1",
    )
    return DragonTigerResult(
        source="eastmoney datacenter",
        retrieved_at=now,
        ticker=resolved.code,
        name=resolved.name,
        events=[_dragon_event(row) for row in event_rows],
        buy_seats=[_dragon_seat(row) for row in buy_rows],
        sell_seats=[_dragon_seat(row) for row in sell_rows],
        institution_flow=_institution_flow(buy_rows, sell_rows),
        raw={"event_filter": filter_str, "seat_filter": seat_filter},
    )


def get_lockup_expiry(
    ticker: str,
    trade_date: str,
    forward_days: int = 90,
    *,
    eastmoney: EastmoneyClient | None = None,
    settings: AStockSettings | None = None,
) -> LockupExpiryResult:
    resolved = resolve_ticker(ticker)
    client = _eastmoney_client(eastmoney, settings)
    now = _now_utc()
    history_filter = f"(SECURITY_CODE=\"{resolved.code}\")"
    history_rows = client.datacenter(
        "RPT_LIFT_STAGE",
        filter_str=history_filter,
        page_size=15,
        sort_columns="FREE_DATE",
        sort_types="-1",
    )
    end_date = dt.date.fromisoformat(trade_date) + dt.timedelta(days=forward_days)
    upcoming_filter = (
        f"(SECURITY_CODE=\"{resolved.code}\")"
        f"(FREE_DATE>='{trade_date}')"
        f"(FREE_DATE<='{end_date.isoformat()}')"
    )
    upcoming_rows = client.datacenter(
        "RPT_LIFT_STAGE",
        filter_str=upcoming_filter,
        page_size=20,
        sort_columns="FREE_DATE",
        sort_types="1",
    )
    return LockupExpiryResult(
        source="eastmoney datacenter",
        retrieved_at=now,
        ticker=resolved.code,
        name=resolved.name,
        history=[_lockup_record(row) for row in history_rows],
        upcoming=[_lockup_record(row) for row in upcoming_rows],
        raw={"history_filter": history_filter, "upcoming_filter": upcoming_filter},
    )


def get_industry_comparison(
    ticker: str,
    trade_date: str,
    top_n: int = 20,
    *,
    eastmoney: EastmoneyClient | None = None,
    settings: AStockSettings | None = None,
) -> IndustryComparisonResult:
    resolved = resolve_ticker(ticker)
    client = _eastmoney_client(eastmoney, settings)
    now = _now_utc()
    payload = client.push2(
        PUSH2_CLIST_PATH,
        {
            "pn": "1",
            "pz": str(max(top_n, 1)),
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fs": "m:90+t:2",
            "fields": "f12,f14,f3,f104,f105,f140",
        },
    )
    rows = [_industry_row(row) for row in _diff_rows(payload)]
    return IndustryComparisonResult(
        source="eastmoney push2",
        retrieved_at=now,
        ticker=resolved.code,
        name=resolved.name,
        rows=[row for row in rows if row is not None],
        target_industry=None,
        raw={"trade_date": trade_date},
    )


__all__ = [
    "get_concept_blocks",
    "get_dragon_tiger_board",
    "get_fund_flow",
    "get_industry_comparison",
    "get_lockup_expiry",
]
