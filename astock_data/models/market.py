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


class StockDataResult(ResultBase):
    ticker: Ticker
    bars: list[OHLCVBar]
    period: str = "day"


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
