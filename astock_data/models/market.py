from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .base import ResultBase, Ticker


class OHLCVBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    @field_validator("date", mode="before")
    @classmethod
    def _coerce_date(cls, value: object) -> str:
        if isinstance(value, dt.datetime):
            return value.isoformat(timespec="minutes")
        if isinstance(value, dt.date):
            return value.isoformat()
        return str(value)


class KlineBar(BaseModel):
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    amount: float | None = None

    @field_validator("date", mode="before")
    @classmethod
    def _coerce_date(cls, value: object) -> str:
        if isinstance(value, dt.datetime):
            return value.isoformat(timespec="minutes")
        if isinstance(value, dt.date):
            return value.isoformat()
        return str(value)


class StockDataResult(ResultBase):
    ticker: Ticker
    bars: list[OHLCVBar]
    period: str = "day"


class IndexKlineResult(ResultBase):
    key: str
    bars: list[KlineBar]


class StockAmountResult(ResultBase):
    ticker: Ticker
    bars: list[KlineBar]


class OrderBookLevel(BaseModel):
    position: int = Field(ge=1, le=5)
    price: float = Field(gt=0)
    volume_lots: float = Field(ge=0)


class OrderBookSnapshot(BaseModel):
    vendor_timestamp: str = Field(pattern=r"^\d{14}$")
    last_price: float | None = None
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    bid_depth_lots: float = Field(ge=0)
    ask_depth_lots: float = Field(ge=0)
    spread: float | None = None
    imbalance: float | None = Field(default=None, ge=-1, le=1)


class OrderBookChange(BaseModel):
    side: Literal["bid", "ask"]
    price: float = Field(gt=0)
    previous_volume_lots: float | None = Field(default=None, ge=0)
    current_volume_lots: float | None = Field(default=None, ge=0)
    delta_volume_lots: float
    event: Literal[
        "depth-increase",
        "depth-decrease",
        "entered-view",
        "left-view",
    ]
    attribution: Literal["unattributed"] = "unattributed"
    from_vendor_timestamp: str = Field(pattern=r"^\d{14}$")
    to_vendor_timestamp: str = Field(pattern=r"^\d{14}$")


class OrderBookResult(ResultBase):
    ticker: Ticker
    samples_requested: int = Field(ge=1, le=60)
    interval_seconds: float = Field(ge=1, le=60)
    exact_cancellation_available: bool = False
    snapshots: list[OrderBookSnapshot]
    changes: list[OrderBookChange]


class EtfDailyResult(BaseModel):
    """Daily K-line bars for a set of ETF codes (e.g. industry ETFs).

    ``bars_by_code`` maps each requested ETF code to its recent daily
    ``KlineBar`` list (oldest-first). Missing codes map to an empty list.
    Used by the daily-review step-2 ETF-strength dimension as the akshare-free
    replacement.
    """

    bars_by_code: dict[str, list[KlineBar]]
    warnings: list[str] = []


class IndicatorPoint(BaseModel):
    date: str
    value: float | str

    @field_validator("date", mode="before")
    @classmethod
    def _coerce_date(cls, value: object) -> str:
        if isinstance(value, dt.datetime):
            return value.isoformat(timespec="minutes")
        if isinstance(value, dt.date):
            return value.isoformat()
        return str(value)


class IndicatorResult(ResultBase):
    indicator: str
    points: list[IndicatorPoint]
    description: str | None = None


class IndexSnapshot(BaseModel):
    key: str
    name: str
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None


class LimitStats(BaseModel):
    limit_up_count: int
    limit_down_count: int


class BoardItem(BaseModel):
    code: str
    name: str
    boards: int
    reason: str | None = None
    close: float | None = None
    change_pct: float | None = None


class LimitDownItem(BaseModel):
    code: str
    name: str
    close: float | None = None
    change_pct: float | None = None


class MarketBreadthResult(ResultBase):
    date: str
    indices: list[IndexSnapshot]
    limit_stats: LimitStats
    board_ladders: dict[int, list[BoardItem]]
    limit_down_rows: list[LimitDownItem] = []
    description: str | None = None
