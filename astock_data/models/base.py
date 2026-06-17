from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ResultMeta(BaseModel):
    source: str
    retrieved_at: datetime
    ticker: str | None = None
    name: str | None = None


class ResultBase(ResultMeta):
    raw: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class Ticker(BaseModel):
    code: str
    market: Literal["sh", "sz", "bj"]
    name: str | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not re.fullmatch(r"^[0368]\d{5}$", value):
            raise ValueError("code must be a 6-digit A-share ticker")
        return value
