from __future__ import annotations

import csv
import datetime as dt
from collections import Counter
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from astock_data.config import get_settings
from astock_data.errors import DataSourceError
from astock_data.models.signals import (
    HotStockItem,
    HotStocksResult,
    NorthboundFlowResult,
    ProfitForecastResult,
    ShareholderResult,
)
from astock_data.resolver import normalize_ticker, resolve_ticker

_THS_EPS_URL = "https://basic.10jqka.com.cn/new/{code}/worth.html"
_THS_HOT_URL = (
    "http://zx.10jqka.com.cn/event/api/getharden/"
    "date/{date}/orderby/date/orderway/desc/charset/GBK/"
)
_THS_HSGT_URL = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) astock-data/0.1.0"
_NORTHBOUND_CSV = "northbound_daily.csv"


def _now() -> dt.datetime:
    return dt.datetime.now()


def _session_get(session: Any, url: str, *, headers: dict[str, str], timeout: float) -> Any:
    response = session.get(url, headers=headers, timeout=timeout)
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    return response


def _json(response: Any) -> dict[str, Any]:
    data = response.json()
    return data if isinstance(data, dict) else {}


def _text(response: Any) -> str:
    if hasattr(response, "text"):
        return str(response.text)
    content = getattr(response, "content", b"")
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="ignore")
    return str(content)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text in {"--", "-", "nan", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int:
    parsed = _to_float(value)
    return int(parsed) if parsed is not None else 0


def _cache_dir(cache: Any, settings: Any) -> Path:
    if cache is not None:
        candidate = getattr(cache, "base_dir", cache)
    else:
        candidate = settings.cache_dir
    return Path(candidate).expanduser().resolve()


def _northbound_cache_path(cache: Any, settings: Any) -> Path:
    base_dir = _cache_dir(cache, settings)
    base_dir.mkdir(parents=True, exist_ok=True)
    path = (base_dir / _NORTHBOUND_CSV).resolve()
    if path.parent != base_dir:
        raise DataSourceError("unsafe northbound cache path")
    return path


def _load_northbound_history(path: Path, limit: int = 20) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            hgt = _to_float(row.get("hgt"))
            sgt = _to_float(row.get("sgt"))
            rows.append(
                {
                    "date": row.get("date"),
                    "hgt": hgt,
                    "sgt": sgt,
                    "total": (hgt or 0.0) + (sgt or 0.0),
                }
            )
    return rows[-limit:]


def _save_northbound_snapshot(path: Path, date_str: str, hgt: float, sgt: float) -> None:
    existing: dict[str, tuple[float, float]] = {}
    if path.exists():
        for row in _load_northbound_history(path, limit=10_000):
            date_key = row.get("date")
            if date_key:
                existing[str(date_key)] = (float(row.get("hgt") or 0.0), float(row.get("sgt") or 0.0))
    existing[date_str] = (hgt, sgt)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "hgt", "sgt"])
        for date_key in sorted(existing):
            writer.writerow([date_key, f"{existing[date_key][0]:.2f}", f"{existing[date_key][1]:.2f}"])


def get_insider_transactions(ticker: str, *, tdx: Any = None, settings: Any = None) -> ShareholderResult:
    resolved = resolve_ticker(ticker)
    if tdx is None:
        from astock_data.clients.tdx import TdxClient

        tdx = TdxClient()
    payload = tdx.f10_shareholders(resolved.code)
    return ShareholderResult(
        ticker=resolved.code,
        name=resolved.name,
        content=str(payload.get("content") or ""),
        sections=payload.get("sections"),
        source="mootdx F10",
        retrieved_at=_now(),
    )


def _read_ths_eps_table(html: str) -> pd.DataFrame:
    frames = pd.read_html(StringIO(html))
    if not frames:
        return pd.DataFrame()
    best = max(frames, key=lambda frame: frame.shape[1])
    return best.fillna("")


def _forecast_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        values = list(row)
        if len(values) < 5:
            continue
        fy_number = _to_float(values[0])
        fy = str(int(fy_number)) if fy_number is not None and fy_number.is_integer() else str(values[0]).strip()
        if not fy or fy.lower() == "nan":
            continue
        rows.append(
            {
                "fy": fy,
                "analysts": _to_int(values[1]),
                "min": _to_float(values[2]),
                "avg": _to_float(values[3]),
                "max": _to_float(values[4]),
            }
        )
    return rows


def get_profit_forecast(
    ticker: str,
    curr_date: str | None = None,
    *,
    tencent: Any = None,
    ths_session: Any = None,
    settings: Any = None,
) -> ProfitForecastResult:
    resolved = resolve_ticker(ticker)
    settings = settings or get_settings()
    session = ths_session or requests.Session()
    response = _session_get(
        session,
        _THS_EPS_URL.format(code=resolved.code),
        headers={"User-Agent": getattr(settings, "user_agent", _USER_AGENT)},
        timeout=float(getattr(settings, "request_timeout", 15.0)),
    )
    rows = _forecast_rows(_read_ths_eps_table(_text(response)))
    warnings = [
        f"low analyst coverage for FY{row['fy']} (<3 analysts)"
        for row in rows
        if int(row.get("analysts") or 0) < 3
    ]

    if tencent is None:
        from astock_data.clients.tencent import TencentClient

        tencent = TencentClient(timeout=float(getattr(settings, "request_timeout", 15.0)))
    quote = tencent.quote([resolved.code]).get(resolved.code, {})
    price = _to_float(quote.get("price"))
    forward_pe = None
    peg = None
    rows_with_eps = [row for row in rows if _to_float(row.get("avg")) and _to_float(row.get("avg")) > 0]
    if price and rows_with_eps:
        current_eps = float(rows_with_eps[0]["avg"])
        forward_pe = price / current_eps
        if len(rows_with_eps) >= 2:
            next_eps = float(rows_with_eps[1]["avg"])
            growth = next_eps / current_eps - 1
            if growth > 0:
                peg = forward_pe / (growth * 100)

    return ProfitForecastResult(
        ticker=resolved.code,
        name=resolved.name,
        rows=rows,
        forward_pe=forward_pe,
        peg=peg,
        warnings=warnings,
        raw={"curr_date": curr_date, "price": price, "pe_ttm": quote.get("pe_ttm")},
        source="ths+tencent",
        retrieved_at=_now(),
    )


def get_hot_stocks(
    curr_date: str = "",
    *,
    ths_session: Any = None,
    settings: Any = None,
) -> HotStocksResult:
    settings = settings or get_settings()
    date_str = curr_date.strip() if curr_date and curr_date.strip() else _now().strftime("%Y-%m-%d")
    result_date = dt.date.fromisoformat(date_str)
    session = ths_session or requests.Session()
    response = _session_get(
        session,
        _THS_HOT_URL.format(date=date_str),
        headers={"User-Agent": getattr(settings, "user_agent", _USER_AGENT)},
        timeout=float(getattr(settings, "request_timeout", 15.0)),
    )
    data = _json(response)
    rows = data.get("data") if str(data.get("errocode", 0)) == "0" else []
    items: list[HotStockItem] = []
    themes: Counter[str] = Counter()
    for row in rows or []:
        reason = str(row.get("reason") or "")
        for theme in [part.strip() for part in reason.split("+") if part.strip()]:
            themes[theme] += 1
        items.append(
            HotStockItem(
                code=normalize_ticker(str(row.get("code") or "")),
                name=str(row.get("name") or ""),
                reason=reason or None,
                zhangfu=_to_float(row.get("zhangfu")),
                huanshou=_to_float(row.get("huanshou")),
                chengjiaoe=_to_float(row.get("chengjiaoe")),
                ddejingliang=_to_float(row.get("ddejingliang")),
            )
        )
    return HotStocksResult(
        date=result_date,
        items=items,
        theme_frequency=dict(themes.most_common(15)),
        source="ths",
        retrieved_at=_now(),
    )


def get_northbound_flow(
    curr_date: str,
    include_history: bool = False,
    *,
    ths_session: Any = None,
    cache: Any = None,
    settings: Any = None,
) -> NorthboundFlowResult:
    settings = settings or get_settings()
    date_str = curr_date.strip() if curr_date and curr_date.strip() else _now().strftime("%Y-%m-%d")
    session = ths_session or requests.Session()
    response = _session_get(
        session,
        _THS_HSGT_URL,
        headers={"User-Agent": getattr(settings, "user_agent", _USER_AGENT), "Referer": "https://data.hexin.cn/"},
        timeout=float(getattr(settings, "request_timeout", 15.0)),
    )
    data = _json(response)
    times = list(data.get("time") or [])
    hgt = list(data.get("hgt") or [])
    sgt = list(data.get("sgt") or [])
    realtime: list[dict[str, Any]] = []
    for index, item_time in enumerate(times):
        hgt_value = _to_float(hgt[index] if index < len(hgt) else None)
        sgt_value = _to_float(sgt[index] if index < len(sgt) else None)
        realtime.append(
            {
                "time": item_time,
                "hgt": hgt_value,
                "sgt": sgt_value,
                "total": (hgt_value or 0.0) + (sgt_value or 0.0),
            }
        )

    total = realtime[-1]["total"] if realtime else 0.0
    if total > 0:
        signal = "INFLOW"
    elif total < 0:
        signal = "OUTFLOW"
    else:
        signal = "neutral"

    path = _northbound_cache_path(cache, settings)
    if realtime:
        _save_northbound_snapshot(
            path,
            date_str,
            float(realtime[-1].get("hgt") or 0.0),
            float(realtime[-1].get("sgt") or 0.0),
        )
    history = _load_northbound_history(path) if include_history else None
    return NorthboundFlowResult(
        realtime=realtime,
        history=history,
        signal=signal,
        source="ths+hsgt",
        retrieved_at=_now(),
    )


__all__ = [
    "get_insider_transactions",
    "get_profit_forecast",
    "get_hot_stocks",
    "get_northbound_flow",
]
