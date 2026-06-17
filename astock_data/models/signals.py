from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field

from .base import ResultBase


class ShareholderResult(ResultBase):
    content: str
    sections: dict[str, Any] | None = None


class ProfitForecastResult(ResultBase):
    rows: list[dict[str, Any]]
    forward_pe: float | None = None
    peg: float | None = None
    warnings: list[str] = Field(default_factory=list)


class HotStockItem(BaseModel):
    code: str
    name: str
    reason: str | None = None
    zhangfu: float | None = None
    huanshou: float | None = None
    chengjiaoe: float | None = None
    ddejingliang: float | None = None


class HotStocksResult(ResultBase):
    date: dt.date
    items: list[HotStockItem]
    theme_frequency: dict[str, int]


class NorthboundFlowResult(ResultBase):
    realtime: list[dict[str, Any]]
    history: list[dict[str, Any]] | None = None
    signal: str | None = None


class ConceptBlock(BaseModel):
    name: str
    ratio: float | None = None
    describe: str | None = None


class ConceptBlocksResult(ResultBase):
    concepts: list[ConceptBlock]
    industries: list[ConceptBlock]
    regions: list[ConceptBlock]
    concept_tags: list[str]


class FundFlowRow(BaseModel):
    time: dt.datetime | dt.date | str | None = None
    main_net_inflow: float | None = None
    super_large_net_inflow: float | None = None
    large_net_inflow: float | None = None
    medium_net_inflow: float | None = None
    small_net_inflow: float | None = None
    raw: dict[str, Any] | None = None


class FundFlowResult(ResultBase):
    minute: list[FundFlowRow]
    daily: list[FundFlowRow] | None = None
    signal: str | None = None


class DragonTigerEvent(BaseModel):
    date: dt.date | None = None
    reason: str | None = None
    close: float | None = None
    change_pct: float | None = None
    net_buy: float | None = None
    amount: float | None = None
    raw: dict[str, Any] | None = None


class DragonTigerSeat(BaseModel):
    seat_name: str | None = None
    buy_amount: float | None = None
    sell_amount: float | None = None
    net_amount: float | None = None
    raw: dict[str, Any] | None = None


class DragonTigerResult(ResultBase):
    events: list[DragonTigerEvent]
    buy_seats: list[DragonTigerSeat]
    sell_seats: list[DragonTigerSeat]
    institution_flow: dict[str, Any] | None = None


class LockupRecord(BaseModel):
    date: dt.date | None = None
    holder: str | None = None
    shares: float | None = None
    market_value_yi: float | None = None
    ratio: float | None = None
    raw: dict[str, Any] | None = None


class LockupExpiryResult(ResultBase):
    history: list[LockupRecord]
    upcoming: list[LockupRecord]


class IndustryRow(BaseModel):
    code: str | None = None
    name: str
    industry: str | None = None
    price: float | None = None
    change_pct: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    market_cap_yi: float | None = None
    raw: dict[str, Any] | None = None


class IndustryComparisonResult(ResultBase):
    rows: list[IndustryRow]
    target_industry: str | None = None
