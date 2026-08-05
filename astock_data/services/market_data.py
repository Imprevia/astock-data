from __future__ import annotations

import datetime as dt
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError
from stockstats import StockDataFrame as Sdf

from astock_data.cache import CsvKlineCache
from astock_data.clients.eastmoney import EastmoneyClient
from astock_data.clients.sina import SinaClient
from astock_data.clients.tdx import TdxClient
from astock_data.clients.tencent import TencentClient
from astock_data.config import AStockSettings, get_settings
from astock_data.errors import DataSourceError, MarketValidationError
from astock_data.market import validate_date_range
from astock_data.models import (
    EtfDailyResult,
    IndexKlineResult,
    IndicatorPoint,
    IndicatorResult,
    KlineBar,
    OHLCVBar,
    OrderBookChange,
    OrderBookResult,
    OrderBookSnapshot,
    StockAmountResult,
    StockDataResult,
    Ticker,
)
from astock_data.resolver import resolve_ticker


_VALID_PERIODS = {"day", "week", "month", "1min", "5min", "15min", "30min", "60min"}
_MINUTE_PERIODS = {"1min", "5min", "15min", "30min", "60min"}
_SINA_PERIODS = {"day", "week", "month", "5min", "15min", "30min", "60min"}

# 东财push2his被封概率高，用低重试配置快速触发降级到新浪/腾讯。
# 懒加载避免模块导入时创建session（影响测试mock）。
_fast_em_client: EastmoneyClient | None = None


def _get_fast_em_client() -> EastmoneyClient:
    global _fast_em_client
    if _fast_em_client is None:
        _fast_em_client = EastmoneyClient(timeout=5.0, max_retries=1)
    return _fast_em_client

_INDEX_KLINE_SECIDS = {
    "sh": "1.000001",
    "szci": "0.399106",
    "cyb": "0.399006",
    "hs300": "1.000300",
}

_INDEX_TO_SINA_SYMBOL = {
    "sh": "sh000001",
    "szci": "sz399001",
    "cyb": "sz399006",
    "hs300": "sh000300",
}


_SUPPORTED_INDICATORS = {
    "close_50_sma",
    "close_200_sma",
    "close_10_ema",
    "macd",
    "macds",
    "macdh",
    "rsi",
    "boll",
    "boll_ub",
    "boll_lb",
    "atr",
    "vwma",
    "mfi",
}


def _now_utc() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def _to_bar(row: dict[str, Any]) -> OHLCVBar:
    date_value = row.get("date")
    if isinstance(date_value, dt.datetime):
        date_value = date_value.isoformat(timespec="minutes")
    elif isinstance(date_value, dt.date):
        date_value = date_value.isoformat()
    elif isinstance(date_value, str):
        date_value = date_value[:16] if len(date_value) > 10 else date_value
    return OHLCVBar(
        date=str(date_value),
        open=float(row.get("open", 0.0)),
        high=float(row.get("high", 0.0)),
        low=float(row.get("low", 0.0)),
        close=float(row.get("close", 0.0)),
        volume=float(row.get("volume", 0.0)),
    )


def _to_kline_bar(row: dict[str, Any]) -> KlineBar:
    return KlineBar(
        date=str(row.get("date", "")),
        open=row.get("open"),
        high=row.get("high"),
        low=row.get("low"),
        close=row.get("close"),
        volume=row.get("volume"),
        amount=row.get("amount"),
        change_pct=row.get("change_pct"),
        turnover_pct=row.get("turnover_pct"),
    )


def get_index_kline(key: str, days: int = 10) -> IndexKlineResult:
    """指数日K线（含成交额 amount）。key: sh/szci/cyb/hs300。"""
    from astock_data.clients import eastmoney as _em

    bars: list[KlineBar] = []
    warnings: list[str] = []
    secid = _INDEX_KLINE_SECIDS.get(key)
    if not secid:
        warnings.append(f"未知的指数key: {key!r}，支持: {', '.join(sorted(_INDEX_KLINE_SECIDS))}")
    else:
        try:
            rows = _em.fetch_kline(secid, days=days, client=_get_fast_em_client())
            bars = [_to_kline_bar(row) for row in rows]
        except Exception as exc:  # noqa: BLE001 - upstream errors degrade to empty result
            bars = []
            warnings.append(f"获取指数K线失败(key={key}): {type(exc).__name__}: {exc}")
        if not bars:
            try:
                sina_rows = SinaClient().index_kline(
                    _INDEX_TO_SINA_SYMBOL[key],
                    datalen=days,
                )
                if sina_rows:
                    bars = [
                        _to_kline_bar(
                            {
                                **row,
                                "volume": None,
                                "amount": row.get("volume"),
                            }
                        )
                        for row in sina_rows
                    ]
                    warnings.append(
                        f"东财 push2his 不可用，已降级到新浪获取指数K线（有效行数 {len(bars)}/{days}）"
                    )
            except Exception as sina_exc:  # noqa: BLE001 - fallback errors are reported as warnings
                warnings.append(f"新浪 fallback 失败: {type(sina_exc).__name__}: {sina_exc}")
        if not bars:
            try:
                tdx_rows = TdxClient().index_bars(key, days=days)
                if tdx_rows:
                    bars = [_to_kline_bar(row) for row in tdx_rows]
                    warnings.append(f"东财 push2his 不可用，已降级到 mootdx 获取指数K线（有效行数 {len(bars)}/{days}）")
            except Exception as tdx_exc:  # noqa: BLE001 - fallback errors are reported as warnings
                warnings.append(f"mootdx fallback 也失败: {type(tdx_exc).__name__}: {tdx_exc}")
    return IndexKlineResult(source="eastmoney", retrieved_at=_now_utc(), key=key, bars=bars, warnings=warnings)


def get_stock_amount(ticker: str, days: int = 10) -> StockAmountResult:
    """个股近 days 日 K 线（含成交额）。"""
    from astock_data.clients import eastmoney as _em

    resolved = resolve_ticker(ticker)
    bars: list[KlineBar] = []
    warnings: list[str] = []
    source = "eastmoney"
    secid = f"1.{resolved.code}" if str(resolved.code).startswith("6") else f"0.{resolved.code}"
    try:
        rows = _em.fetch_kline(secid, days=days, client=_get_fast_em_client())
        bars = [_to_kline_bar(row) for row in rows]
        if not bars:
            raise DataSourceError("Eastmoney push2his returned no stock amount bars")
    except Exception as exc:  # noqa: BLE001 - upstream errors trigger fallback
        warnings.append(f"获取个股成交额失败(ticker={ticker}): {type(exc).__name__}: {exc}")
        try:
            settings = get_settings()
            quote = TencentClient(
                timeout=settings.request_timeout,
                settings=settings,
            ).quote([resolved.code])
            quote_row = quote.get(resolved.code, {})
            amount_wan = quote_row.get("amount_wan")
            if amount_wan is None:
                raise ValueError("Tencent quote did not include stock amount")
            vendor_timestamp = str(quote_row.get("vendor_timestamp") or "")
            if len(vendor_timestamp) < 8 or not vendor_timestamp[:8].isdigit():
                raise ValueError("Tencent quote did not include a valid vendor date")
            quote_date = dt.datetime.strptime(
                vendor_timestamp[:8], "%Y%m%d"
            ).date().isoformat()
            bars = [
                KlineBar(
                    date=quote_date,
                    open=quote_row.get("open"),
                    high=quote_row.get("high"),
                    low=quote_row.get("low"),
                    close=quote_row.get("price"),
                    volume=quote_row.get("volume"),
                    amount=float(amount_wan) * 10_000,
                    change_pct=quote_row.get("change_pct"),
                    turnover_pct=quote_row.get("turnover_pct"),
                )
            ]
            source = "tencent"
            warnings.append(
                "used matching-date Tencent quote K-line metrics "
                "because Eastmoney push2his was unavailable"
            )
        except Exception as tencent_exc:  # noqa: BLE001 - fallback errors degrade to empty result
            warnings.append(
                "腾讯个股成交额降级失败"
                f"(ticker={ticker}): {type(tencent_exc).__name__}: {tencent_exc}"
            )
    return StockAmountResult(
        source=source,
        retrieved_at=_now_utc(),
        ticker=resolved,
        name=resolved.name,
        bars=bars,
        warnings=warnings,
    )


def _validate_order_book_sampling(samples: int, interval_seconds: float) -> None:
    if isinstance(samples, bool) or not isinstance(samples, int) or not 1 <= samples <= 60:
        raise MarketValidationError("samples must be an integer between 1 and 60")
    if (
        isinstance(interval_seconds, bool)
        or not isinstance(interval_seconds, (int, float))
        or not 1 <= interval_seconds <= 60
    ):
        raise MarketValidationError("interval_seconds must be between 1 and 60")
    planned_wait = (samples - 1) * float(interval_seconds)
    if planned_wait > 300:
        raise MarketValidationError(
            "planned order-book sampling wait must not exceed 300 seconds"
        )


def _depth_by_price(snapshot: OrderBookSnapshot, side: str) -> dict[float, float]:
    levels = snapshot.bids if side == "bid" else snapshot.asks
    depth: dict[float, float] = {}
    for level in levels:
        depth[level.price] = depth.get(level.price, 0.0) + level.volume_lots
    return depth


def _compare_order_book_snapshots(
    previous: OrderBookSnapshot,
    current: OrderBookSnapshot,
) -> list[OrderBookChange]:
    """Compare visible depth only at matching side and price coordinates."""

    changes: list[OrderBookChange] = []
    for side in ("bid", "ask"):
        previous_depth = _depth_by_price(previous, side)
        current_depth = _depth_by_price(current, side)
        for price in sorted(previous_depth.keys() | current_depth.keys()):
            previous_volume = previous_depth.get(price)
            current_volume = current_depth.get(price)
            if previous_volume is None:
                event = "entered-view"
                delta_volume = current_volume or 0.0
            elif current_volume is None:
                event = "left-view"
                delta_volume = -previous_volume
            else:
                delta_volume = current_volume - previous_volume
                if delta_volume == 0:
                    continue
                event = "depth-increase" if delta_volume > 0 else "depth-decrease"
            changes.append(
                OrderBookChange(
                    side=side,
                    price=price,
                    previous_volume_lots=previous_volume,
                    current_volume_lots=current_volume,
                    delta_volume_lots=delta_volume,
                    event=event,
                    attribution="unattributed",
                    from_vendor_timestamp=previous.vendor_timestamp,
                    to_vendor_timestamp=current.vendor_timestamp,
                )
            )
    return changes


def get_order_book(
    ticker: str,
    samples: int = 1,
    interval_seconds: float = 1.0,
    *,
    tencent: TencentClient | None = None,
    sleep: Callable[[float], None] | None = None,
) -> OrderBookResult:
    """Collect bounded Tencent five-level snapshots and visible-depth changes."""

    # Validate the complete wait budget before resolver or vendor access.
    _validate_order_book_sampling(samples, interval_seconds)
    resolved = resolve_ticker(ticker)
    client = tencent or TencentClient()
    sleep_fn = sleep or time.sleep
    snapshots: list[OrderBookSnapshot] = []
    changes: list[OrderBookChange] = []
    warnings: list[str] = []
    comparison_snapshot: OrderBookSnapshot | None = None
    resolved_with_name = resolved

    for sample_index in range(samples):
        try:
            row = client.order_book(resolved.code)
        except DataSourceError as exc:
            warnings.append(
                f"Tencent order-book sample {sample_index + 1} failed: {exc}"
            )
        else:
            if not row:
                warnings.append(
                    f"Tencent order-book sample {sample_index + 1} returned no usable snapshot"
                )
            else:
                try:
                    snapshot = OrderBookSnapshot.model_validate(row)
                except ValidationError as exc:
                    warnings.append(
                        "Tencent order-book sample "
                        f"{sample_index + 1} was invalid: {exc.errors()[0]['msg']}"
                    )
                else:
                    snapshots.append(snapshot)
                    if row.get("name") and not resolved.name:
                        resolved_with_name = resolved.model_copy(update={"name": row["name"]})
                    if comparison_snapshot is not None:
                        if snapshot.vendor_timestamp == comparison_snapshot.vendor_timestamp:
                            warnings.append(
                                "duplicate Tencent vendor timestamp; dynamic comparison skipped"
                            )
                        elif snapshot.vendor_timestamp < comparison_snapshot.vendor_timestamp:
                            warnings.append(
                                "non-increasing Tencent vendor timestamp; dynamic comparison skipped"
                            )
                        else:
                            changes.extend(
                                _compare_order_book_snapshots(
                                    comparison_snapshot,
                                    snapshot,
                                )
                            )
                            comparison_snapshot = snapshot
                    else:
                        comparison_snapshot = snapshot

        if sample_index < samples - 1:
            sleep_fn(float(interval_seconds))

    if not snapshots:
        warning_context = "; ".join(warnings) or "no vendor response details"
        raise DataSourceError(
            "Tencent order-book sampling returned no usable snapshots "
            f"for ticker={resolved.code}: {warning_context}"
        )

    return OrderBookResult(
        source="tencent",
        retrieved_at=_now_utc(),
        ticker=resolved_with_name,
        name=resolved_with_name.name,
        samples_requested=samples,
        interval_seconds=float(interval_seconds),
        exact_cancellation_available=False,
        snapshots=snapshots,
        changes=changes,
        warnings=warnings,
    )


def _bars_to_frame(bars: list[OHLCVBar]) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "date": bar.date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
    )
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").reset_index(drop=True)
    return frame


def _filter_bars(bars: list[OHLCVBar], *, start_date: str, end_date: str) -> list[OHLCVBar]:
    start = dt.date.fromisoformat(start_date)
    end = dt.date.fromisoformat(end_date)
    filtered = [bar for bar in bars if start <= dt.date.fromisoformat(bar.date[:10]) <= end]
    filtered.sort(key=lambda item: item.date)
    return filtered


def _default_cache(settings: AStockSettings) -> CsvKlineCache:
    return CsvKlineCache(Path(settings.cache_dir) / "kline", ttl=dt.timedelta(hours=settings.kline_cache_ttl_hours))


def _load_cached_bars(cache: CsvKlineCache | None, code: str, *, period: str) -> list[OHLCVBar] | None:
    if cache is None:
        return None
    return cache.read(code, period=period)


def _fetch_tdx_bars(tdx: TdxClient, code: str, period: str) -> list[dict[str, Any]]:
    rows = tdx.bars(code, period=period)
    if not rows:
        return []
    return rows


def _fetch_sina_bars(sina: SinaClient, code: str, start_date: str, end_date: str, period: str) -> list[dict[str, Any]]:
    if period in _MINUTE_PERIODS:
        start_date = f"{start_date} 00:00:00"
        end_date = f"{end_date} 23:59:59"
    return sina.kline(code, start_date=start_date, end_date=end_date, period=period) or []


def _validate_period(period: str) -> str:
    if period not in _VALID_PERIODS:
        supported = ", ".join(sorted(_VALID_PERIODS))
        raise MarketValidationError(f"Unsupported period: {period!r}. Supported periods: {supported}")
    return period


def _prefer_tdx(period: str) -> bool:
    return False


def _prefer_sina(period: str) -> bool:
    return period in _VALID_PERIODS


def _load_ohlcv(
    code: str,
    start_date: str,
    end_date: str,
    period: str,
    *,
    cache: CsvKlineCache | None,
    tdx: TdxClient,
    sina: SinaClient,
    now: dt.datetime,
) -> tuple[list[OHLCVBar], str]:
    cached = _load_cached_bars(cache, code, period=period)
    if cached is not None:
        return _filter_bars(cached, start_date=start_date, end_date=end_date), "cache"

    bars: list[OHLCVBar] = []
    source = "mootdx"
    if _prefer_sina(period):
        try:
            bars = [_to_bar(row) for row in _fetch_sina_bars(sina, code, start_date, end_date, period)]
            source = "sina"
        except Exception:
            bars = []
        if not bars:
            try:
                bars = [_to_bar(row) for row in _fetch_tdx_bars(tdx, code, period)]
                source = "mootdx"
            except Exception:
                bars = []
    else:
        try:
            bars = [_to_bar(row) for row in _fetch_tdx_bars(tdx, code, period)]
        except Exception:
            bars = []
        if not bars and period in _SINA_PERIODS:
            bars = [_to_bar(row) for row in _fetch_sina_bars(sina, code, start_date, end_date, period)]
            source = "sina"

    bars = _filter_bars(bars, start_date=start_date, end_date=end_date)
    if cache is not None and bars:
        cache.write(code, bars, period=period, created_at=now)
    return bars, source


def _indicator_description(indicator: str) -> str:
    descriptions = {
        "close_50_sma": "50日简单移动平均",
        "close_200_sma": "200日简单移动平均",
        "close_10_ema": "10日指数移动平均",
        "macd": "MACD 指标",
        "macds": "MACD signal 线",
        "macdh": "MACD 柱状图",
        "rsi": "相对强弱指标",
        "boll": "布林带中轨",
        "boll_ub": "布林带上轨",
        "boll_lb": "布林带下轨",
        "atr": "平均真实波幅",
        "vwma": "成交量加权移动平均",
        "mfi": "资金流量指标",
    }
    return descriptions.get(indicator, indicator)


def _indicator_series(frame: pd.DataFrame, indicator: str) -> pd.Series:
    stock_frame = Sdf.retype(frame.copy())
    if indicator == "close_50_sma":
        return stock_frame["close_50_sma"]
    if indicator == "close_200_sma":
        return stock_frame["close_200_sma"]
    if indicator == "close_10_ema":
        return stock_frame["close_10_ema"]
    if indicator == "macd":
        return stock_frame["macd"]
    if indicator == "macds":
        return stock_frame["macds"]
    if indicator == "macdh":
        return stock_frame["macdh"]
    if indicator == "rsi":
        return stock_frame["rsi_14"]
    if indicator == "boll":
        return stock_frame["boll"]
    if indicator == "boll_ub":
        return stock_frame["boll_ub"]
    if indicator == "boll_lb":
        return stock_frame["boll_lb"]
    if indicator == "atr":
        return stock_frame["atr"]
    if indicator == "vwma":
        return stock_frame["vwma"]
    if indicator == "mfi":
        return stock_frame["mfi"]
    raise ValueError(indicator)


def _indicator_points(frame: pd.DataFrame, indicator: str) -> list[IndicatorPoint]:
    if frame.empty:
        return []
    series = _indicator_series(frame, indicator)
    points: list[IndicatorPoint] = []
    for date_value, raw_value in zip(frame["date"], series, strict=False):
        if pd.isna(raw_value):
            value: float | str = "N/A"
        else:
            value = float(raw_value)
        points.append(IndicatorPoint(date=pd.Timestamp(date_value).date().isoformat(), value=value))
    return points


def get_stock_data(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    period: str = "day",
    settings: AStockSettings | None = None,
    cache: CsvKlineCache | None = None,
    tdx: TdxClient | None = None,
    sina: SinaClient | None = None,
) -> StockDataResult:
    settings = settings or get_settings()
    period = _validate_period(period)
    validate_date_range(start_date, end_date)
    ticker = resolve_ticker(symbol)
    tdx = tdx or TdxClient()
    sina = sina or SinaClient()
    cache = cache or _default_cache(settings)
    now = _now_utc()

    bars, source = _load_ohlcv(
        ticker.code,
        start_date,
        end_date,
        period,
        cache=cache,
        tdx=tdx,
        sina=sina,
        now=now,
    )

    return StockDataResult(
        source=source,
        retrieved_at=now,
        ticker=ticker,
        name=ticker.name,
        bars=bars,
        period=period,
    )


def get_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
    *,
    settings: AStockSettings | None = None,
    tdx: TdxClient | None = None,
    sina: SinaClient | None = None,
) -> IndicatorResult:
    if indicator not in _SUPPORTED_INDICATORS:
        supported = ", ".join(sorted(_SUPPORTED_INDICATORS))
        raise MarketValidationError(
            f"Unsupported indicator: {indicator!r}. Supported indicators: {supported}"
        )
    settings = settings or get_settings()
    ticker = resolve_ticker(symbol)
    tdx = tdx or TdxClient()
    sina = sina or SinaClient()
    cache = _default_cache(settings)

    curr = dt.date.fromisoformat(curr_date)
    start = curr - dt.timedelta(days=max(look_back_days - 1, 0))
    now = _now_utc()
    bars, source = _load_ohlcv(
        ticker.code,
        start.isoformat(),
        curr.isoformat(),
        "day",
        cache=cache,
        tdx=tdx,
        sina=sina,
        now=now,
    )
    frame = _bars_to_frame(bars)
    points = _indicator_points(frame, indicator)
    return IndicatorResult(
        source="cache" if source == "cache" else "stockstats",
        retrieved_at=now,
        ticker=ticker.code,
        name=ticker.name,
        indicator=indicator,
        points=points,
        description=_indicator_description(indicator),
    )


# ---------------------------------------------------------------------------
# ETF daily K-line (daily-review step-2 ETF-strength dimension, akshare-free)
# ---------------------------------------------------------------------------

# Industry ETFs used by daily-review step-2 (sector_strength ETF_MAP).
# Mapping is code-only; the secid prefix is derived from the leading digit.
_INDUSTRY_ETF_CODES: frozenset[str] = frozenset(
    {
        "512480", "159995", "512010", "512170", "512290", "159928", "515170",
        "512690", "516160", "515790", "159790", "512800", "512880", "512070",
        "512660", "512810", "515000", "512330", "512200", "516950", "515220",
        "512400", "515210", "159611", "159767", "516110", "516270",
        "515230", "512720", "512980", "515880", "562500", "515260",
        "518880", "159869",
        "516020", "159825",
    }
)


def _etf_secid(code: str) -> str | None:
    """ETF 6-digit code → Eastmoney secid (``1.512480`` for SH, ``0.159995`` for SZ)."""
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    if len(digits) != 6 or digits not in _INDUSTRY_ETF_CODES:
        return None
    # 沪市 ETF 以 5 开头；深市 ETF 以 1 开头（159xxx）。
    prefix = "1" if digits.startswith("5") else "0"
    return f"{prefix}.{digits}"


def _etf_sina_symbol(code: str) -> str | None:
    """ETF 6-digit code → Sina symbol (``sh512480`` for SH, ``sz159995`` for SZ)."""
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    if len(digits) != 6 or digits not in _INDUSTRY_ETF_CODES:
        return None
    prefix = "sh" if digits.startswith("5") else "sz"
    return f"{prefix}{digits}"


def get_etf_daily(
    codes: list[str],
    days: int = 10,
) -> EtfDailyResult:
    """一批行业 ETF 的近 N 日日 K 线（含成交额），替代 akshare ``fund_etf_fund_daily_em``。

    降级链为新浪历史 K 线 → 东财 push2his。新浪响应不提供成交额时，
    ``amount`` 保持为空，不以成交量代替。
    """
    from astock_data.clients import eastmoney as _em

    warnings: list[str] = []
    bars_by_code: dict[str, list[KlineBar]] = {}
    sina_client: SinaClient | None = None
    sina_used = False
    eastmoney_used = False

    for code in codes:
        sina_symbol = _etf_sina_symbol(code)
        if sina_symbol is None:
            bars_by_code[code] = []
            warnings.append(f"未支持的ETF代码（不在行业ETF映射内）: {code}")
            continue

        try:
            if sina_client is None:
                sina_client = SinaClient()
            sina_rows = sina_client.index_kline(sina_symbol, datalen=days)
            if sina_rows:
                selected_rows = sina_rows[-days:] if days > 0 else []
                bars_by_code[code] = [_to_kline_bar(row) for row in selected_rows]
                sina_used = True
                continue
        except Exception as exc:  # noqa: BLE001 - upstream failure triggers fallback
            warnings.append(f"ETF {code} Sina K线拉取失败：{type(exc).__name__}: {exc}")

        secid = _etf_secid(code)
        try:
            rows = _em.fetch_kline(secid, days=days, client=_get_fast_em_client())
            selected_rows = rows[-days:] if days > 0 else []
            bars_by_code[code] = [_to_kline_bar(row) for row in selected_rows]
            eastmoney_used = bool(selected_rows) or eastmoney_used
        except Exception as exc:  # noqa: BLE001 - per-ETF failure degrades to empty
            bars_by_code[code] = []
            warnings.append(f"ETF {code} Eastmoney K线拉取失败：{type(exc).__name__}: {exc}")

    if sina_used:
        warnings.append("新浪K线作为ETF数据主源")
    if eastmoney_used:
        warnings.append("部分ETF已降级到东方财富K线")
    return EtfDailyResult(bars_by_code=bars_by_code, warnings=warnings)
