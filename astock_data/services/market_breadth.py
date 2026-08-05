from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from astock_data.clients.eastmoney import EastmoneyClient
from astock_data.clients.sina import SinaClient
from astock_data.clients.tencent import TencentClient
from astock_data.errors import DataSourceError, MarketValidationError
from astock_data.models import (
    BoardItem,
    IndexSnapshot,
    LimitDownItem,
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
_BOARD_SKIP_WARNING = "board_ladders skipped because no current limit-up stock set was available"
_SUPPORTED_KLINE_PREFIXES = ("0", "3", "4", "6", "8", "9")
_DEFAULT_LOOKBACK_DAYS = 20
_FAST_CLIST_PAGE_SIZE = 6000
_FAST_SINA_PAGE_SIZE = 80
_FAST_SINA_MAX_PAGES = 20
_MIN_LIMIT_THRESHOLD = 4.8


@dataclass(frozen=True)
class _LimitRowsResult:
    """Rows plus per-side completeness needed to avoid fabricated zero counts."""

    rows: list[dict]
    source: str | None
    limit_up_available: bool
    limit_down_available: bool


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def _local_today() -> dt.date:
    return dt.datetime.now().astimezone().date()


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
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _row_code(row: Mapping[str, Any]) -> str:
    return str(row.get("f12") or row.get("code") or "").strip()


def _row_name(row: Mapping[str, Any]) -> str:
    return str(row.get("f14") or row.get("name") or "").strip()


def _row_change_pct(row: Mapping[str, Any]) -> float | None:
    return _to_float(row.get("f3") if "f3" in row else row.get("change_pct"))


def _row_close(row: Mapping[str, Any]) -> float | None:
    return _to_float(row.get("f2") if "f2" in row else row.get("close"))


def _row_amount(row: Mapping[str, Any]) -> float | None:
    return _to_float(row.get("f6") if "f6" in row else row.get("amount"))


def _validate_limit_rows(rows: list[dict], source: str) -> None:
    """Reject rows that cannot support a factual per-direction limit count."""

    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise DataSourceError(f"{source} row {index} is not an object")
        code = _row_code(row)
        if not code:
            raise DataSourceError(f"{source} row {index} is missing a stock code")
        if len(code) != 6 or not code.isdigit():
            raise DataSourceError(f"{source} row {index} has an invalid stock code")
        if _row_change_pct(row) is None:
            raise DataSourceError(
                f"{source} row {index} has an invalid change percentage"
            )


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
        name=str(row.get("f58") or row.get("name") or fallback_name),
        price=_to_float(row.get("f43") if "f43" in row else row.get("price")),
        change=_to_float(
            row.get("f169")
            if row.get("f169") not in (None, "", "-")
            else row.get("f60") if "f60" in row else row.get("change")
        ),
        change_pct=_to_float(
            row.get("f170") if "f170" in row else row.get("change_pct")
        ),
    )


def _fetch_indices(eastmoney: EastmoneyClient) -> list[IndexSnapshot]:
    indices: list[IndexSnapshot] = []
    for key, name, secid in _INDEX_SECIDS:
        row = eastmoney.index_snapshot(secid)
        if not row:
            raise DataSourceError(f"Eastmoney index source returned no row for {secid}")
        indices.append(_index_snapshot(key, name, row))
    return indices


def _snapshots_from_mapping(rows: Mapping[str, Mapping[str, Any]]) -> list[IndexSnapshot]:
    indices: list[IndexSnapshot] = []
    for key, fallback_name, _ in _INDEX_SECIDS:
        row = rows.get(key)
        if row is not None:
            indices.append(_index_snapshot(key, fallback_name, row))
    return indices


def _fallback_warning(capability: str, failed: str, fallback: str, exc: Exception) -> str:
    return f"{capability} source {failed} failed ({exc}); fallback used {fallback}"


def _failure_warning(capability: str, source: str, exc: Exception) -> str:
    return f"{capability} source {source} failed ({exc})"


def _fetch_indices_with_fallbacks(
    eastmoney: EastmoneyClient,
    tencent: TencentClient,
    sina: SinaClient,
    warnings: list[str],
) -> tuple[list[IndexSnapshot], str | None]:
    # 腾讯/新浪优先，东财push2被封概率最高放最后。
    failures: list[tuple[str, Exception]] = []

    for source, fetch in (
        ("tencent", tencent.index_snapshots),
        ("sina", sina.index_snapshots),
    ):
        try:
            indices = _snapshots_from_mapping(fetch())
            if len(indices) == len(_INDEX_SECIDS):
                for failed, exc in failures:
                    warnings.append(_fallback_warning("indices", failed, source, exc))
                return indices, source
            raise DataSourceError(f"{source} index source returned incomplete rows")
        except Exception as exc:
            failures.append((source, exc))

    # 东财作为最后兜底
    try:
        indices = _fetch_indices(eastmoney)
        if len(indices) == len(_INDEX_SECIDS):
            for failed, exc in failures:
                warnings.append(_fallback_warning("indices", failed, "eastmoney", exc))
            return indices, "eastmoney"
        raise DataSourceError("Eastmoney index source returned incomplete rows")
    except Exception as exc:
        failures.append(("eastmoney", exc))

    for source, exc in failures:
        warnings.append(_failure_warning("indices", source, exc))
    return [], None


def _fetch_limit_rows_with_fallbacks(
    eastmoney: EastmoneyClient,
    sina: SinaClient,
    warnings: list[str],
) -> _LimitRowsResult:
    # 新浪优先，东财push2被封概率最高放最后。
    failures: list[tuple[str, Exception]] = []

    try:
        rows = sina.market_all()
        if rows:
            _validate_limit_rows(rows, "Sina market pagination")
            return _LimitRowsResult(rows, "sina", True, True)
        raise DataSourceError("Sina market pagination returned no rows")
    except Exception as exc:
        failures.append(("sina", exc))

    # 东财作为最后兜底
    try:
        rows = eastmoney.clist_all(fields="f12,f14,f2,f3,f6,f8")
        if rows:
            _validate_limit_rows(rows, "Eastmoney clist")
            for failed, exc in failures:
                warnings.append(_fallback_warning("limit_stats", failed, "eastmoney", exc))
            return _LimitRowsResult(rows, "eastmoney", True, True)
        raise DataSourceError("Eastmoney clist returned no rows")
    except Exception as exc:
        failures.append(("eastmoney", exc))

    for source, exc in failures:
        warnings.append(_failure_warning("limit_stats", source, exc))
    return _LimitRowsResult([], None, False, False)


def _sina_extreme_rows(
    sina: SinaClient,
    *,
    ascending: bool,
    warnings: list[str],
) -> tuple[list[dict], bool]:
    """Fetch one sorted extreme at a time until rows leave every limit band."""

    rows: list[dict] = []
    direction = "losers" if ascending else "gainers"
    predicate = _is_limit_down if ascending else _is_limit_up
    try:
        for page in range(1, _FAST_SINA_MAX_PAGES + 1):
            page_rows = sina.market_page(
                page=page,
                page_size=_FAST_SINA_PAGE_SIZE,
                sort_field="changepercent",
                ascending=ascending,
            )
            if not page_rows:
                if page == 1:
                    warnings.append(
                        _failure_warning(
                            f"limit_stats {direction}",
                            "sina",
                            DataSourceError("first extreme page returned no rows"),
                        )
                    )
                    return [], False
                return rows, True
            _validate_limit_rows(page_rows, f"Sina {direction} page {page}")
            rows.extend(row for row in page_rows if predicate(row))
            last_pct = _row_change_pct(page_rows[-1])
            if ascending:
                outside_threshold = last_pct > -_MIN_LIMIT_THRESHOLD
            else:
                outside_threshold = last_pct < _MIN_LIMIT_THRESHOLD
            if outside_threshold or len(page_rows) < _FAST_SINA_PAGE_SIZE:
                return rows, True
        warnings.append(
            f"fast Sina {direction} pagination reached {_FAST_SINA_MAX_PAGES} pages"
        )
        return rows, False
    except Exception as exc:  # noqa: BLE001 - the opposite extreme remains usable
        warnings.append(_failure_warning(f"limit_stats {direction}", "sina", exc))
        return rows, False


def _fetch_fast_limit_rows(
    eastmoney: EastmoneyClient,
    sina: SinaClient,
    warnings: list[str],
) -> _LimitRowsResult:
    """Prefer one complete clist response, then bounded Sina extremes."""

    try:
        rows, total = eastmoney.clist(
            page=1,
            page_size=_FAST_CLIST_PAGE_SIZE,
            fields="f12,f14,f2,f3,f6,f8",
        )
        if rows and total == len(rows):
            _validate_limit_rows(rows, "Eastmoney clist")
            return _LimitRowsResult(rows, "eastmoney.clist", True, True)
        if rows:
            raise DataSourceError(
                f"Eastmoney clist returned partial rows ({len(rows)}/{total})"
            )
        raise DataSourceError("Eastmoney clist returned no rows")
    except Exception as exc:  # noqa: BLE001 - bounded Sina extremes are the fallback
        warnings.append(
            _fallback_warning("limit_stats", "eastmoney.clist", "sina.extremes", exc)
        )

    gainers, gainers_succeeded = _sina_extreme_rows(
        sina,
        ascending=False,
        warnings=warnings,
    )
    losers, losers_succeeded = _sina_extreme_rows(
        sina,
        ascending=True,
        warnings=warnings,
    )
    if not gainers_succeeded and not losers_succeeded:
        return _LimitRowsResult([], None, False, False)

    by_code: dict[str, dict] = {}
    for row in [*gainers, *losers]:
        code = _row_code(row)
        if code:
            by_code[code] = row
    warnings.append(
        "limit_stats used bounded Sina changepercent extremes; full-market rows were not scanned"
    )
    return _LimitRowsResult(
        list(by_code.values()),
        "sina.extremes",
        gainers_succeeded,
        losers_succeeded,
    )


def _count_limits(result: _LimitRowsResult) -> LimitStats:
    if result.limit_up_available and result.limit_down_available:
        status = "available"
    elif result.limit_up_available or result.limit_down_available:
        status = "partial"
    else:
        status = "unavailable"
    return LimitStats(
        limit_up_count=(
            sum(1 for row in result.rows if _is_limit_up(row))
            if result.limit_up_available
            else None
        ),
        limit_down_count=(
            sum(1 for row in result.rows if _is_limit_down(row))
            if result.limit_down_available
            else None
        ),
        status=status,
    )


def _verify_snapshot_date(
    sina: SinaClient,
    target: dt.date,
    warnings: list[str],
) -> tuple[str | None, str]:
    """Match every requested session to the latest vendor daily snapshot."""

    today = _local_today()
    if target > today:
        warnings.append(
            f"market breadth target {target.isoformat()} is in the future"
        )
        return None, "future-date"
    try:
        rows = sina.index_kline("sh000001", datalen=1)
        snapshot_date = str(rows[-1].get("date") or "") if rows else ""
    except Exception as exc:  # noqa: BLE001 - unavailable verification is explicit
        warnings.append(f"market breadth snapshot date verification failed: {exc}")
        return None, "unavailable"

    if snapshot_date != target.isoformat():
        warnings.append(
            "market breadth snapshot date "
            f"{snapshot_date or 'unknown'} does not match target {target.isoformat()}"
        )
        return snapshot_date or None, "mismatch"
    return snapshot_date, "verified"


def _unavailable_snapshot_result(
    target: dt.date,
    *,
    fast: bool,
    warnings: list[str],
    snapshot_date: str | None,
    snapshot_date_status: str,
) -> MarketBreadthResult:
    """Return a structured absence instead of relabeling a live snapshot."""

    warnings.append(
        "market breadth unavailable because the requested session could not be "
        "matched to the current snapshot"
    )
    return MarketBreadthResult(
        source="unavailable",
        retrieved_at=_now(),
        status="unavailable",
        date=target.isoformat(),
        indices=[],
        limit_stats=LimitStats(
            limit_up_count=None,
            limit_down_count=None,
            status="unavailable",
        ),
        board_ladders={},
        limit_down_rows=[],
        description="Market breadth is unavailable for an unverified target session.",
        warnings=warnings,
        raw={
            "sources": {
                "indices": None,
                "limit_stats": None,
                "board_ladders": None,
            },
            "limit_row_count": 0,
            "market_amount": None,
            "fast": fast,
            "snapshot_date": snapshot_date,
            "snapshot_date_status": snapshot_date_status,
        },
    )


def _verified_market_amount(
    rows: list[dict],
    row_source: str | None,
    sina: SinaClient,
    target: dt.date,
    warnings: list[str],
) -> dict[str, Any] | None:
    amounts = [
        amount
        for row in rows
        if (amount := _row_amount(row)) is not None and amount > 0
    ]
    if not amounts:
        return None

    try:
        index_rows = sina.index_kline("sh000001", datalen=1)
        snapshot_date = str(index_rows[-1].get("date") or "") if index_rows else ""
    except Exception as exc:  # noqa: BLE001 - optional verified snapshot
        warnings.append(f"market amount snapshot date verification failed: {exc}")
        return None

    if snapshot_date != target.isoformat():
        warnings.append(
            "market amount snapshot date "
            f"{snapshot_date or 'unknown'} does not match target {target.isoformat()}"
        )
        return None

    source = {
        "sina": "sina.market_all",
        "eastmoney": "eastmoney.clist_all",
    }.get(row_source, str(row_source or "unknown"))
    return {
        "amount": sum(amounts),
        "date": snapshot_date,
        "row_count": len(amounts),
        "source": source,
    }


def _collect_limit_down_rows(rows: list[dict]) -> list[LimitDownItem]:
    """Collect individual limit-down stocks (not just the count)."""
    items: list[LimitDownItem] = []
    for row in rows:
        if not _is_limit_down(row):
            continue
        items.append(
            LimitDownItem(
                code=_row_code(row),
                name=_row_name(row),
                close=_row_close(row),
                change_pct=_row_change_pct(row),
            )
        )
    return items


def _has_limit_up_rows(rows: list[dict]) -> bool:
    return any(_is_limit_up(row) for row in rows)


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
    hot_reasons: Mapping[str, str] | None = None,
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
                reason=hot_reasons.get(code) if hot_reasons else None,
            )
        )
    return {key: sorted(value, key=lambda item: item.code) for key, value in sorted(ladders.items(), reverse=True)}


def get_market_breadth(
    date: str = "",
    fast: bool = False,
    *,
    eastmoney: EastmoneyClient | None = None,
    tencent: TencentClient | None = None,
    sina: SinaClient | None = None,
    stock_data_func: Callable[..., StockDataResult] = get_stock_data,
) -> MarketBreadthResult:
    target = _target_date(date)
    client = eastmoney or EastmoneyClient(timeout=3.0, max_retries=0)
    tencent_client = tencent or TencentClient()
    sina_client = sina or SinaClient()
    warnings: list[str] = []

    snapshot_date, snapshot_date_status = _verify_snapshot_date(
        sina_client,
        target,
        warnings,
    )
    if snapshot_date_status in {"future-date", "unavailable", "mismatch"}:
        return _unavailable_snapshot_result(
            target,
            fast=fast,
            warnings=warnings,
            snapshot_date=snapshot_date,
            snapshot_date_status=snapshot_date_status,
        )

    indices, index_source = _fetch_indices_with_fallbacks(
        client, tencent_client, sina_client, warnings
    )
    limit_rows = (
        _fetch_fast_limit_rows(client, sina_client, warnings)
        if fast
        else _fetch_limit_rows_with_fallbacks(client, sina_client, warnings)
    )
    rows = limit_rows.rows
    row_source = limit_rows.source
    limit_stats = _count_limits(limit_rows)
    if index_source is None and limit_stats.status == "unavailable":
        raise DataSourceError("All market breadth index and full-market quote sources failed")

    if fast:
        market_amount = None
        warnings.append(
            "fast mode skipped the date-verified full-market amount scan"
        )
    else:
        market_amount = _verified_market_amount(
            rows,
            row_source,
            sina_client,
            target,
            warnings,
        )

    hot_reasons: Mapping[str, str] | None = None
    try:
        from astock_data.services.signals_a import get_hot_stocks as _get_hot_stocks

        hot_result = _get_hot_stocks(target.isoformat())
        hot_reasons = {
            item.code: item.reason
            for item in hot_result.items
            if item.reason
        }
    except Exception as exc:  # noqa: BROAD_EXCEPT_OK - reason enrichment is best-effort
        warnings.append(f"hot_stocks reason enrichment skipped: {exc}")

    if limit_rows.limit_up_available and rows and _has_limit_up_rows(rows):
        board_ladders = _derive_board_ladders(
            rows,
            target,
            stock_data_func,
            warnings,
            hot_reasons=hot_reasons,
        )
        if board_ladders:
            warnings.append(_DERIVED_WARNING)
            board_source = "derived.kline.threshold"
        else:
            warnings.append(_BOARD_SKIP_WARNING)
            board_source = None
    else:
        warnings.append(_BOARD_SKIP_WARNING)
        board_ladders = {}
        board_source = None

    status = (
        "available"
        if index_source is not None and limit_stats.status == "available"
        else "partial"
    )
    return MarketBreadthResult(
        source="+".join(
            dict.fromkeys(
                source
                for source in (
                    index_source,
                    row_source,
                    "derived" if board_source else None,
                )
                if source
            )
        ),
        retrieved_at=_now(),
        status=status,
        date=target.isoformat(),
        indices=indices,
        limit_stats=limit_stats,
        limit_down_rows=(
            _collect_limit_down_rows(rows)
            if limit_rows.limit_down_available
            else []
        ),
        board_ladders=board_ladders,
        description="Market breadth snapshot with fixed-index quotes, limit counts, and derived board ladders.",
        warnings=warnings,
        raw={
            "sources": {
                "indices": index_source,
                "limit_stats": row_source,
                "board_ladders": board_source,
            },
            "limit_row_count": len(rows),
            "market_amount": market_amount,
            "fast": fast,
            "snapshot_date": snapshot_date,
            "snapshot_date_status": snapshot_date_status,
        },
    )


__all__ = ["get_market_breadth"]
