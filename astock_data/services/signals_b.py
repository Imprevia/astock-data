from __future__ import annotations

import datetime as dt
import json
import re
import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests

from astock_data.cache import SQLiteStructuredCache
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
from astock_data.models.signals import (
    SectorFundFlow,
    SectorFundFlowHistoryResult,
    SectorFundFlowResult,
    SectorStrengthResult,
    SectorStrengthRow,
)
from astock_data.resolver import resolve_ticker
from astock_data.services.signals_a import _USER_AGENT, _session_get


_EM_TO_THS_SECTOR_MAP: Mapping[str, str] = {
    # 东财细分行业 → 同花顺大行业（同花顺分类粒度较粗，一个THS行业覆盖多个EM细分）
    # 半导体产业链 → 881121 半导体
    "BK1036": "881121",  # 半导体
    "BK1326": "881121",  # 半导体设备
    "BK1331": "881121",  # 数字芯片设计
    "BK1011": "881121",  # 集成电路封测
    "BK1032": "881121",  # 集成电路制造
    "BK1035": "881121",  # 半导体材料
    "BK1332": "881121",  # 模拟芯片设计
    "BK1012": "881121",  # 分立器件
    # 电子/消费电子 → 881124 消费电子
    "BK1201": "881124",  # 电子
    "BK1037": "881124",  # 消费电子
    "BK1338": "881124",  # 消费电子零部件及组装
    "BK0459": "881124",  # 元件
    "BK1038": "881122",  # 光学光电子
    "BK1034": "881124",  # 被动元件
    "BK0474": "881124",  # 印制电路板
    "BK1722": "881172",  # 电子化学品Ⅲ
    # 通信 → 881129 通信设备
    "BK0448": "881129",  # 通信设备
    "BK1591": "881129",  # 通信网络设备及器件
    "BK1215": "881129",  # 通信
    # 有色金属 → 881168 工业金属 / 881169 贵金属
    "BK0478": "881168",  # 有色金属
    "BK1287": "881168",  # 工业金属
    "BK1141": "881168",  # 铜
    "BK1109": "881169",  # 贵金属
    "BK1074": "881169",  # 黄金
    "BK0482": "881170",  # 小金属（含稀土）
    # 电力 → 881145 电力
    "BK1200": "881145",  # 电力设备
}
_THS_INDUSTRY_KLINE_URL = "http://d.10jqka.com.cn/v6/line/bk_{code}/01/last.js"
_THS_JSONP_RE = re.compile(r"\((\{.*\})\)\s*;?\s*$", re.DOTALL)
_DATAAPI_BKZJ_URL = "https://data.eastmoney.com/dataapi/bkzj/getbkzj"


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


# ---------------------------------------------------------------------------
# Sector strength + history (daily-review step-2 「定方向」data sources)
# ---------------------------------------------------------------------------


def _structured_cache(settings: AStockSettings | None) -> SQLiteStructuredCache:
    cfg = settings or get_settings()
    return SQLiteStructuredCache(
        base_dir=Path(cfg.cache_dir),
        ttl=dt.timedelta(hours=cfg.structured_cache_ttl_hours),
    )


def _target_trade_date(curr_date: str) -> str:
    """Normalize a user-supplied date to ``YYYY-MM-DD`` (default: today)."""
    text = (curr_date or "").strip()
    if text:
        return dt.date.fromisoformat(text[:10]).isoformat()
    return dt.date.today().isoformat()


def _is_connection_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    text = str(exc).lower()
    return (
        "Connection" in name
        or "Timeout" in name
        or "connection" in text
        or "timeout" in text
    )


def _sector_strength_row(row: Mapping[str, Any]) -> SectorStrengthRow | None:
    code = str(row.get("f12") or "").strip()
    name = str(row.get("f14") or "").strip()
    if not code or not name:
        return None
    return SectorStrengthRow(
        code=code,
        name=name,
        change_pct=_float_or_none(row.get("f3")),
        amount=_float_or_none(row.get("f6")),
        main_net_inflow=_float_or_none(row.get("f62")),
        main_inflow_pct=_float_or_none(row.get("f184")),
        up_count=_int_or_none(row.get("f104")),
        down_count=_int_or_none(row.get("f105")),
    )


def _int_or_none(value: Any) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def get_sector_strength(
    curr_date: str = "",
    *,
    eastmoney: EastmoneyClient | None = None,
    settings: AStockSettings | None = None,
) -> SectorStrengthResult:
    """行业板块当日 6 维强度数据（成交额/主力净额/净占比/涨跌幅/上涨·下跌数）。

    一次调用东方财富 clist ``m:90+t:2``（与 daily-review 第二步原口径一致），
    取齐 ``f3/f6/f62/f184/f104/f105`` 全字段。封 IP / 断连时自动回退到本地
    ``SQLiteStructuredCache`` 最近一次成功快照（最多回退 3 天），并以
    ``cache_source`` 字段标注。

    板块代码（如 ``BK0447``）非 A 股 ticker，因此不经 ``resolve_ticker``；
    数据层只对板块码做格式校验。
    """
    from astock_data.clients import eastmoney as _em

    client = _eastmoney_client(eastmoney, settings)
    target_date = _target_trade_date(curr_date)
    warnings: list[str] = []
    cache_source: str | None = None
    cache = _structured_cache(settings)
    hour_key = f"{target_date}-{dt.datetime.now().hour:02d}"

    raw_rows: list[dict[str, Any]] | None = None
    try:
        payload = client.push2(
            PUSH2_CLIST_PATH,
            {
                "pn": "1",
                "pz": "100",
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fid": "f3",
                "fs": "m:90+t:2",
                "fields": "f12,f14,f3,f6,f62,f184,f104,f105",
            },
        )
        raw_rows = _diff_rows(payload)
        try:
            cache.write_general(
                "sector_strength",
                hour_key,
                target_date,
                {"rows": raw_rows},
            )
        except Exception:  # noqa: BLE001 - cache write failure must not break the call
            pass
    except Exception as exc:  # noqa: BLE001 - upstream errors trigger cache fallback
        reason = "断连/超时" if _is_connection_error(exc) else type(exc).__name__
        warnings.append(f"⚠️ 行业数据接口失败({reason})，尝试缓存回退：{exc}")
        cached = None
        try:
            cached = cache.read_latest("sector_strength", hour_key, target_date, max_fallback_days=3)
        except Exception:  # noqa: BLE001 - cache read failure degrades to empty
            cached = None
        if cached is None:
            warnings.append("❌ 无可用缓存，行业强度维度降级为空。请联网后重试以生成缓存。")
            return SectorStrengthResult(date=target_date, rows=[], cache_source=None, warnings=warnings)
        payload_cache, actual_date = cached
        raw_rows = payload_cache.get("rows") if isinstance(payload_cache, dict) else []
        cache_source = actual_date
        if actual_date != target_date:
            warnings.append(f"⚠️ 使用 {actual_date} 的缓存数据，非当日")

    rows = [row for row in (_sector_strength_row(r) for r in raw_rows) if row is not None]
    # 去重：同名板块（去后缀 Ⅱ/Ⅲ… 后）保留主力净额绝对值最大的一条。
    seen: dict[str, SectorStrengthRow] = {}
    for row in rows:
        base = _strip_sector_suffix(row.name)
        prev = seen.get(base)
        if prev is None or _abs_or_zero(row.main_net_inflow) > _abs_or_zero(prev.main_net_inflow):
            seen[base] = row
    rows = list(seen.values())

    return SectorStrengthResult(
        date=target_date,
        rows=rows,
        cache_source=cache_source,
        warnings=warnings,
    )


_SECTOR_SUFFIX_RE = re.compile(r"[ⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+$")


def _strip_sector_suffix(name: str) -> str:
    return _SECTOR_SUFFIX_RE.sub("", name).strip()


def _abs_or_zero(value: float | None) -> float:
    return abs(value) if value is not None else 0.0


def _em_to_ths_code(code: str) -> str | None:
    return _EM_TO_THS_SECTOR_MAP.get(code.upper())


def _fetch_dataapi_sector_fund_flow(
    codes: list[str],
    days: int = 5,
    settings: AStockSettings | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch real cumulative sector fund flow from Eastmoney dataapi in one request."""
    cfg = settings or get_settings()
    headers = {
        "User-Agent": getattr(cfg, "user_agent", _USER_AGENT),
        "Referer": "https://data.eastmoney.com/bkzj/hy.html",
    }
    key = {1: "f62", 5: "f164", 10: "f165"}.get(days, "f164")

    try:
        with requests.Session() as session:
            response = session.get(
                _DATAAPI_BKZJ_URL,
                params={"key": key, "code": "m:90+t:2"},
                headers=headers,
                timeout=float(getattr(cfg, "request_timeout", 15.0)),
            )
            response.raise_for_status()
    except requests.RequestException:
        return {}

    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return {}

    data = payload.get("data")
    if not isinstance(data, Mapping):
        return {}
    diff = data.get("diff")
    if not isinstance(diff, list):
        return {}

    inflow_by_code: dict[str, float] = {}
    for item in diff:
        if not isinstance(item, Mapping):
            continue
        bk_code = str(item.get("f12", "")).upper()
        raw_value = item.get(key)
        try:
            inflow_by_code[bk_code] = float(raw_value) if raw_value is not None else 0.0
        except (TypeError, ValueError):
            continue

    target_date = _target_trade_date("")
    result: dict[str, list[dict[str, Any]]] = {}
    for code in codes:
        upper_code = code.upper()
        if upper_code in inflow_by_code:
            result[code] = [
                {
                    "date": target_date,
                    "main_net_inflow": inflow_by_code[upper_code],
                }
            ]
    return result


def _fetch_ths_industry_kline(
    ths_code: str,
    days: int = 5,
    settings: AStockSettings | None = None,
) -> list[dict[str, Any]]:
    """Fetch THS industry daily bars as a fund-flow-history fallback."""
    cfg = settings or get_settings()
    headers = {
        "User-Agent": getattr(cfg, "user_agent", _USER_AGENT),
        "Referer": "https://d.10jqka.com.cn/",
    }
    with requests.Session() as session:
        response = _session_get(
            session,
            _THS_INDUSTRY_KLINE_URL.format(code=ths_code),
            headers=headers,
            timeout=float(getattr(cfg, "request_timeout", 15.0)),
        )

    match = _THS_JSONP_RE.search(str(response.text))
    if match is None:
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, Mapping):
        return []
    raw = payload.get("data")
    if not isinstance(raw, str):
        return []

    result: list[dict[str, Any]] = []
    previous_close: float | None = None
    for line in raw.split(";"):
        parts = line.split(",")
        if len(parts) < 7 or len(parts[0]) != 8 or not parts[0].isdigit():
            continue
        try:
            close = float(parts[4])
            amount = float(parts[6])
        except ValueError:
            continue
        date_raw = parts[0]
        pct_change = (
            round((close / previous_close - 1.0) * 100.0, 4)
            if previous_close not in (None, 0.0)
            else None
        )
        # 同花顺行业K线不含主力资金流；用 涨跌幅×成交额/100 作为资金流方向近似。
        # 涨为正流入，跌为负流出，量级与主力资金流同维度（元），下游可正常汇总。
        approx_inflow = (
            pct_change * amount / 100.0
            if pct_change is not None
            else None
        )
        result.append(
            {
                "date": f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}",
                "main_net_inflow": approx_inflow,
                "close": close,
                "amount": amount,
                "pct_change": pct_change,
            }
        )
        previous_close = close
    return result[-days:]


def get_sector_fund_flow_history(
    codes: list[str],
    curr_date: str = "",
    days: int = 5,
    *,
    eastmoney: EastmoneyClient | None = None,
    settings: AStockSettings | None = None,
) -> SectorFundFlowHistoryResult:
    """多板块近 N 日主力资金流历史（并发拉取 + 单板块缓存回退）。

    并发逻辑（``ThreadPoolExecutor(max_workers=8)``、任一失败即停止后续
    实时请求转缓存）从 daily-review ``sector_strength.py`` 移植到数据层。
    返回 ``SectorFundFlowHistoryResult``，其中 ``history_by_code`` 映射每个
    板块到 ``[{date, main_net_inflow(元)}, ...]``；拉取失败且无缓存的板块
    映射到空列表。

    板块代码不经 ``resolve_ticker``（非 A 股 ticker）。
    """
    from astock_data.clients import eastmoney as _em

    client = _eastmoney_client(eastmoney, settings)
    target_date = _target_trade_date(curr_date)
    cache = _structured_cache(settings)
    hour_key = f"{target_date}-{dt.datetime.now().hour:02d}"

    request_gate = threading.Lock()
    stop_event = threading.Event()
    ths_fallback_codes: set[str] = set()
    push2his_codes: set[str] = set()

    # dataapi 优先：一次请求获取全部行业数据，命中后不再逐个调 push2his。
    # push2his 被反爬封禁时 3 次重试耗时约 30 秒/行业，30 个行业串行等待就是 15 分钟。
    # dataapi 走 data.eastmoney.com（数据中心），与被封的 push2his 是不同服务器。
    try:
        dataapi_data = _fetch_dataapi_sector_fund_flow(codes, days=days, settings=settings)
    except Exception:  # noqa: BLE001 - dataapi failure degrades to push2his
        dataapi_data = {}
    dataapi_used = bool(dataapi_data)
    codes_not_in_dataapi = [c for c in codes if c not in dataapi_data]

    def pull_one(code: str) -> tuple[str, list[dict[str, Any]]]:
        # dataapi 已命中的直接返回
        if code in dataapi_data:
            return code, dataapi_data[code]

        secid = f"90.{code.lower()}"
        with request_gate:
            if stop_event.is_set():
                cached = _read_history_cache(cache, code, hour_key, target_date)
                return code, cached or []
            try:
                values = _em.fetch_sector_fund_flow_history(secid, days=days, client=client)
                push2his_codes.add(code)
                try:
                    cache.write_general(
                        "sector_history",
                        f"{code}:{hour_key}",
                        target_date,
                        {"values": values},
                    )
                except Exception:  # noqa: BLE001 - cache write failure is non-fatal
                    pass
                return code, values
            except Exception:  # noqa: BLE001 - push2his failure degrades to THS/cache
                ths_code = _em_to_ths_code(code)
                if ths_code is not None:
                    try:
                        ths_values = _fetch_ths_industry_kline(
                            ths_code,
                            days=days,
                            settings=settings,
                        )
                    except requests.RequestException:
                        ths_values = []
                    if ths_values:
                        ths_fallback_codes.add(code)
                        return code, ths_values
                stop_event.set()
                cached = _read_history_cache(cache, code, hour_key, target_date)
                return code, cached or []

    histories: dict[str, list[dict[str, Any]]] = {code: [] for code in codes}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(pull_one, code): code for code in codes}
        for future, code in futures.items():
            try:
                result_code, values = future.result(timeout=12)
                histories[result_code] = values
            except Exception:  # noqa: BLE001 - per-code failure degrades to empty
                stop_event.set()
                cached = _read_history_cache(cache, code, hour_key, target_date)
                histories[code] = cached or []
    warnings = []
    if dataapi_used:
        warnings.append(
            "Used dataapi/bkzj as primary source for sector fund-flow history "
            "(real main-net-inflow from data.eastmoney.com dataapi)."
        )
    if push2his_codes:
        warnings.append(
            f"push2his used for {len(push2his_codes)} sectors not covered by dataapi."
        )
    for code in codes:
        if code in ths_fallback_codes:
            warnings.append(
                f"{code}: push2his and dataapi unavailable; switched to THS industry daily K-line. "
                "Amount is provided instead of main net inflow."
            )

    return SectorFundFlowHistoryResult(
        date=target_date,
        days=days,
        history_by_code=histories,
        warnings=warnings,
    )


def _read_history_cache(
    cache: SQLiteStructuredCache,
    code: str,
    hour_key: str,
    target_date: str,
) -> list[dict[str, Any]] | None:
    """Return cached history values for one sector code, fallback up to 3 days."""
    try:
        cached = cache.read_latest(
            "sector_history",
            f"{code}:{hour_key}",
            target_date,
            max_fallback_days=3,
        )
    except Exception:  # noqa: BLE001 - cache read failure is non-fatal
        return None
    if cached is None:
        return None
    payload, _actual = cached
    values = payload.get("values") if isinstance(payload, dict) else None
    return values if isinstance(values, list) else None


__all__ = [
    "get_concept_blocks",
    "get_dragon_tiger_board",
    "get_fund_flow",
    "get_industry_comparison",
    "get_lockup_expiry",
    "get_sector_fund_flow",
    "get_sector_fund_flow_history",
    "get_sector_strength",
]



