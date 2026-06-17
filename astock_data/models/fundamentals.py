from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel

from .base import ResultBase


class Quote(BaseModel):
    price: float | None = None
    pe_ttm: float | None = None
    pe_static: float | None = None
    pb: float | None = None
    market_cap_yi: float | None = None
    float_market_cap_yi: float | None = None
    turnover_pct: float | None = None
    change_pct: float | None = None
    limit_up: float | None = None
    limit_down: float | None = None


class FundamentalsResult(ResultBase):
    quote: Quote
    snapshot: dict[str, Any] | None = None
    consensus_forecast: dict[str, Any] | None = None


class FinancialRow(BaseModel):
    report_date: dt.date
    fields: dict[str, Any]


class FinancialStatementResult(ResultBase):
    statement_type: Literal["balance", "income", "cashflow"]
    freq: str
    rows: list[FinancialRow]
