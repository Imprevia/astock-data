from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .base import ResultBase


class NewsItem(BaseModel):
    title: str
    content: str | None = None
    time: datetime | None = None
    source: str | None = None
    url: str | None = None


class NewsResult(ResultBase):
    items: list[NewsItem]


class GlobalNewsResult(ResultBase):
    items: list[NewsItem]
