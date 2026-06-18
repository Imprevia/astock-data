from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import Any

from astock_data.clients.eastmoney import EastmoneyClient
from astock_data.errors import MarketValidationError
from astock_data.models import (
    BoardItem,
    IndexSnapshot,
    LimitStats,
    MarketBreadthResult,
    StockDataResult,
)
from astock_data.services.market_data import get_stock_data

_INDEX_SECIDS: tuple[tuple[str, str, str], ...] = (
    ("sh", "上证指数", "1.000001"),
    ("sz", "深证成指", "0.399001"),
    ("cyb", "创业板指", "0.399006"),
    ("kc50", "科创50", "1.000688"),
    ("hs300", "沪深300", "1.000300"),
    ("zz500", "中证500", "1.000905"),
)
_DERIVED_WARNING = "board_ladders are derived from K-line threshold rules and may differ from vendor terminal口径"
_SUPPORTED_KLINE_PREFIXES = ("0", "3", "6", "8")
_DEFAULT_LOOKBACK_DAYS = 20


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def _target_date(date: str) -> dt.date:
    if not date or not date.strip():
        return dt.date.today()
    value = date.strip()
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise MarketValidationError(
            f"Invalid date format: {date!r}. Expected 'YYYY-MM-DD'."
        ) from exc
    if parsed.isoformat() != value:
        raise MarketValidationError(
            f"Invalid date format: {date!r}. Expected 'YYYY-MM-DD'."
        )
    return parsed


def _to_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_code(row: Mapping[str, Any]) -> str:
    return str(row.get("f12") or row.get("code") or "").strip()


def _row_name(row: Mapping[str, Any]) -> str:
    return str(row.get("f14") or row.get("name") or "").strip()


def _row_change_pct(row: Mapping[str, Any]) -> float | None:
    return _to_float(row.get("f3") if "f3" in row else row.get("change_pct"))


def _row_close(row: Mapping[str, Any]) -> float | None:
    return _to_float(row.get("f2") if "f2" in row else row.get("close"))


def _threshold(code: str, name: str) -> float:
    upper_name = name.upper()
    if "ST" in upper_name:
        return 4.8
    if code.startswith(("300", "301", "688")):
        return 19.5
    if code.startswith(("8", "92", "43")):
        return 29.5
    return 9.8


def _is_limit_up(row: Mapping[str, Any]) -> bool:
    code = _row_code(row)
    pct = _row_change_pct(row)
    return pct is not None and pct >= _threshold(code, _row_name(row))


def _is_limit_down(row: Mapping[str, Any]) -> bool:
    code = _row_code(row)
    pct = _row_change_pct(row)
    return pct is not None and pct <= -_threshold(code, _row_name(row))


def _index_snapshot(key: str, fallback_name: str, row: Mapping[str, Any]) -> IndexSnapshot:
    return IndexSnapshot(
        key=key,
        name=str(row.get("f58") or fallback_name),
        price=_to_float(row.get("f43")),
        change=_to_float(row.get("f169") if row.get("f169") not in (None, "", "-") else row.get("f60")),
        change_pct=_to_float(row.get("f170")),
    )


def _fetch_indices(eastmoney: EastmoneyClient) -> list[IndexSnapshot]:
    indices: list[IndexSnapshot] = []
    for key, name, secid in _INDEX_SECIDS:
        indices.append(_index_snapshot(key, name, eastmoney.index_snapshot(secid)))
    return indices


def _count_limits(rows: list[dict]) -> LimitStats:
    return LimitStats(
        limit_up_count=sum(1 for row in rows if _is_limit_up(row)),
        limit_down_count=sum(1 for row in rows if _is_limit_down(row)),
    )


def _is_bar_limit_up(previous_close: float, current_close: float, code: str, name: str) -> bool:
    if previous_close <= 0:
        return False
    pct = (current_close - previous_close) / previous_close * 100
    return pct >= _threshold(code, name)


def _board_count(bars: StockDataResult, target: dt.date, code: str, name: str) -> int:
    dated = sorted(
        (dt.date.fromisoformat(bar.date[:10]), bar.close)
        for bar in bars.bars
        if bar.date and bar.date[:10] <= target.isoformat()
    )
    count = 0
    for index in range(len(dated) - 1, 0, -1):
        current_date, current_close = dated[index]
        previous_close = dated[index - 1][1]
        if current_date > target:
            continue
        if count == 0 and current_date != target:
            break
        if not _is_bar_limit_up(previous_close, current_close, code, name):
            break
        count += 1
    return count


def _derive_board_ladders(
    rows: list[dict],
    target: dt.date,
    stock_data_func: Callable[..., StockDataResult],
    warnings: list[str],
    *,
    lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
) -> dict[int, list[BoardItem]]:
    ladders: dict[int, list[BoardItem]] = defaultdict(list)
    start = target - dt.timedelta(days=lookback_days)
    for row in rows:
        if not _is_limit_up(row):
            continue
        code = _row_code(row)
        name = _row_name(row)
        if not code.startswith(_SUPPORTED_KLINE_PREFIXES):
            warnings.append(f"Skipped board derivation for unsupported ticker prefix: {code}")
            continue
        try:
            bars = stock_data_func(code, start.isoformat(), target.isoformat())
        except Exception as exc:
            warnings.append(f"Skipped board derivation for {code}: {exc}")
            continue
        boards = _board_count(bars, target, code, name)
        if boards <= 0:
            continue
        ladders[boards].append(
            BoardItem(
                code=code,
                name=name,
                boards=boards,
                close=_row_close(row),
                change_pct=_row_change_pct(row),
            )
        )
    return {key: sorted(value, key=lambda item: item.code) for key, value in sorted(ladders.items(), reverse=True)}


def get_market_breadth(
    date: str = "",
    *,
    eastmoney: EastmoneyClient | None = None,
    stock_data_func: Callable[..., StockDataResult] = get_stock_data,
) -> MarketBreadthResult:
    target = _target_date(date)
    client = eastmoney or EastmoneyClient()
    warnings = [_DERIVED_WARNING]
    rows = client.clist_all(fields="f12,f14,f2,f3,f6,f8")
    return MarketBreadthResult(
        source="eastmoney+derived",
        retrieved_at=_now(),
        date=target.isoformat(),
        indices=_fetch_indices(client),
        limit_stats=_count_limits(rows),
        board_ladders=_derive_board_ladders(rows, target, stock_data_func, warnings),
        description="Market breadth snapshot with fixed-index quotes, limit counts, and derived board ladders.",
        warnings=warnings,
        raw={
            "sources": {
                "indices": "eastmoney.push2.stock.get",
                "limit_stats": "eastmoney.push2.clist.get",
                "board_ladders": "derived.kline.threshold",
            },
            "limit_row_count": len(rows),
        },
    )


__all__ = ["get_market_breadth"]
