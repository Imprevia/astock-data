from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, field_validator

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


class MarketBreadthResult(ResultBase):
    date: str
    indices: list[IndexSnapshot]
    limit_stats: LimitStats
    board_ladders: dict[int, list[BoardItem]]
    description: str | None = None
