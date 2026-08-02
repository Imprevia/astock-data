"""Unit tests for ``astock_data.services.news``.

All offline: vendor clients and the CLS session are replaced with fakes.
No live network, no mootdx, no LLM imports.
"""

from __future__ import annotations

import datetime as dt

import pytest

from astock_data.services.news import (
    _dedupe_and_limit,
    _filter_by_date,
    _parse_date,
    _to_news_item,
    get_global_news,
    get_news,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeEastmoney:
    """Stand-in for :class:`EastmoneyClient` exposing the news helpers."""

    def __init__(
        self,
        *,
        search_rows: list[dict] | None = None,
        fast_rows: list[dict] | None = None,
        fast_pages: list[tuple[list[dict], str]] | None = None,
        search_error: Exception | None = None,
        fast_error: Exception | None = None,
    ) -> None:
        self._search_rows = search_rows if search_rows is not None else []
        self._fast_rows = fast_rows if fast_rows is not None else []
        self._fast_pages = list(fast_pages or [])
        self._search_error = search_error
        self._fast_error = fast_error
        self.search_calls: list[str] = []
        self.fast_calls: list[int] = []
        self.fast_page_calls: list[tuple[int, str]] = []

    def search_news(self, code: str, page_size: int = 20) -> list[dict]:
        self.search_calls.append(code)
        if self._search_error is not None:
            raise self._search_error
        return list(self._search_rows)

    def fast_news(self, limit: int = 20) -> list[dict]:
        self.fast_calls.append(limit)
        if self._fast_error is not None:
            raise self._fast_error
        return list(self._fast_rows)

    def fast_news_page(
        self,
        limit: int = 20,
        sort_end: str = "",
    ) -> tuple[list[dict], str]:
        self.fast_page_calls.append((limit, sort_end))
        if self._fast_error is not None:
            raise self._fast_error
        if self._fast_pages:
            rows, cursor = self._fast_pages.pop(0)
            return list(rows), cursor
        return list(self._fast_rows), ""


class FakeSina:
    """Stand-in for :class:`SinaClient.news`."""

    def __init__(
        self,
        rows: list[dict] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._rows = rows if rows is not None else []
        self._error = error
        self.calls: list[str] = []

    def news(self, code: str, page_size: int = 20) -> list[dict]:
        self.calls.append(code)
        if self._error is not None:
            raise self._error
        return list(self._rows)


class FakeClsSession:
    """Fake ``requests.Session`` returning a canned CLS JSON payload."""

    def __init__(self, payload: dict | Exception) -> None:
        self._payload = payload
        self.calls: list[tuple] = []

    def get(self, url, params=None, headers=None, timeout=None):  # noqa: D401
        self.calls.append((url, params, headers, timeout))
        if isinstance(self._payload, Exception):
            raise self._payload
        return _FakeResponse(self._payload)


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeCache:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload
        self.writes: list[tuple[str, str, str, dict]] = []

    def read(self, kind: str, ticker: str, trade_date: str) -> dict | None:
        return self.payload

    def write(
        self,
        kind: str,
        ticker: str,
        trade_date: str,
        payload: dict,
    ) -> None:
        self.writes.append((kind, ticker, trade_date, payload))


# ---------------------------------------------------------------------------
# get_news — fallback behavior
# ---------------------------------------------------------------------------


class TestGetNewsFallback:
    def test_falls_back_to_sina_when_eastmoney_empty(self) -> None:
        em = FakeEastmoney(search_rows=[])  # Eastmoney yields nothing
        sina = FakeSina(
            rows=[
                {
                    "title": "Sina headline",
                    "content": "",
                    "time": "2026-06-10 09:30",
                    "source": "新浪财经",
                    "url": "https://sina.example/a",
                }
            ]
        )

        result = get_news(
            "688017",
            "2026-06-01",
            "2026-06-30",
            eastmoney=em,
            sina=sina,
        )

        assert em.search_calls == ["688017"]
        assert sina.calls == ["688017"]
        assert result.source == "sina"
        assert result.ticker == "688017"
        assert len(result.items) == 1
        item = result.items[0]
        assert item.title == "Sina headline"
        assert item.source == "新浪财经"
        assert item.url == "https://sina.example/a"
        assert isinstance(result.retrieved_at, dt.datetime)

    def test_falls_back_to_sina_when_eastmoney_errors(self) -> None:
        em = FakeEastmoney(search_error=RuntimeError("boom"))
        sina = FakeSina(
            rows=[
                {
                    "title": "Fallback after error",
                    "content": "",
                    "time": "2026-06-10 09:30",
                    "source": "新浪财经",
                    "url": "https://sina.example/b",
                }
            ]
        )

        result = get_news(
            "688017", "2026-06-01", "2026-06-30", eastmoney=em, sina=sina
        )

        assert result.source == "sina"
        assert len(result.items) == 1

    def test_uses_eastmoney_when_it_returns_rows(self) -> None:
        em = FakeEastmoney(
            search_rows=[
                {
                    "title": "EM headline",
                    "content": "snippet",
                    "time": "2026-06-10 10:00",
                    "source": "东方财富",
                    "url": "https://em.example/a",
                }
            ]
        )
        sina = FakeSina()

        result = get_news(
            "688017", "2026-06-01", "2026-06-30", eastmoney=em, sina=sina
        )

        assert result.source == "eastmoney"
        assert sina.calls == []  # Sina never consulted when EM succeeds
        assert len(result.items) == 1


# ---------------------------------------------------------------------------
# get_news — date filtering
# ---------------------------------------------------------------------------


class TestGetNewsDateFilter:
    def test_filters_items_outside_window(self) -> None:
        em = FakeEastmoney(
            search_rows=[
                {
                    "title": "in-window",
                    "content": "",
                    "time": "2026-06-10 10:00",
                    "source": "东方财富",
                    "url": "u1",
                },
                {
                    "title": "too-early",
                    "content": "",
                    "time": "2026-05-01 10:00",
                    "source": "东方财富",
                    "url": "u2",
                },
                {
                    "title": "too-late",
                    "content": "",
                    "time": "2026-07-01 10:00",
                    "source": "东方财富",
                    "url": "u3",
                },
            ]
        )

        result = get_news(
            "688017", "2026-06-01", "2026-06-30", eastmoney=em
        )

        titles = [i.title for i in result.items]
        assert titles == ["in-window"]

    def test_keeps_unparseable_time_items(self) -> None:
        em = FakeEastmoney(
            search_rows=[
                {
                    "title": "good",
                    "content": "",
                    "time": "2026-06-10 10:00",
                    "source": "东方财富",
                    "url": "u1",
                },
                {
                    "title": "garbage-date",
                    "content": "",
                    "time": "not a date",
                    "source": "东方财富",
                    "url": "u2",
                },
                {
                    "title": "empty-date",
                    "content": "",
                    "time": "",
                    "source": "东方财富",
                    "url": "u3",
                },
            ]
        )

        result = get_news(
            "688017", "2026-06-01", "2026-06-30", eastmoney=em
        )

        titles = sorted(i.title for i in result.items)
        # The parseable-in-window item plus the two unparseable ones are kept.
        assert titles == ["empty-date", "garbage-date", "good"]

    def test_window_boundaries_are_inclusive(self) -> None:
        em = FakeEastmoney(
            search_rows=[
                {
                    "title": "start-edge",
                    "time": "2026-06-01 00:00",
                    "url": "u1",
                },
                {
                    "title": "end-edge",
                    "time": "2026-06-30 23:59",
                    "url": "u2",
                },
            ]
        )

        result = get_news(
            "688017", "2026-06-01", "2026-06-30", eastmoney=em
        )

        titles = sorted(i.title for i in result.items)
        assert titles == ["end-edge", "start-edge"]


# ---------------------------------------------------------------------------
# get_news — item/result shape
# ---------------------------------------------------------------------------


class TestGetNewsShape:
    def test_result_carries_source_and_retrieved_at(self) -> None:
        em = FakeEastmoney(
            search_rows=[
                {"title": "t", "time": "2026-06-10", "url": "u"}
            ]
        )
        result = get_news("000001", "2026-06-01", "2026-06-30", eastmoney=em)
        assert result.source == "eastmoney"
        assert isinstance(result.retrieved_at, dt.datetime)
        assert result.ticker == "000001"

    def test_items_have_all_fields(self) -> None:
        em = FakeEastmoney(
            search_rows=[
                {
                    "title": "T",
                    "content": "C",
                    "time": "2026-06-10 09:00",
                    "source": "S",
                    "url": "U",
                }
            ]
        )
        result = get_news("000001", "2026-06-01", "2026-06-30", eastmoney=em)
        item = result.items[0]
        assert item.title == "T"
        assert item.content == "C"
        assert item.source == "S"
        assert item.url == "U"
        assert item.time == dt.datetime(2026, 6, 10, 9, 0)


# ---------------------------------------------------------------------------
# get_global_news — dedupe + merge
# ---------------------------------------------------------------------------


class TestGetGlobalNews:
    @staticmethod
    def _timestamp(value: str) -> int:
        return int(dt.datetime.strptime(value, "%Y-%m-%d %H:%M").timestamp())

    def _cls_payload(self, items: list[dict]) -> dict:
        return {"data": {"roll_data": items}}

    def test_dedupes_duplicate_titles_case_insensitive(self) -> None:
        cls = FakeClsSession(
            self._cls_payload(
                [
                    {
                        "title": "Fed cuts rates",
                        "content": "c1",
                        "ctime": self._timestamp("2026-06-10 10:00"),
                    },
                    {
                        "title": "  fed cuts rates  ",  # stripped dup
                        "content": "c2",
                        "ctime": self._timestamp("2026-06-10 10:01"),
                    },
                ]
            )
        )
        em = FakeEastmoney(fast_rows=[])

        result = get_global_news(
            "2026-06-10", look_back_days=7, limit=10, eastmoney=em, cls_session=cls
        )

        assert len(result.items) == 1
        assert result.items[0].title == "Fed cuts rates"

    def test_merges_cls_and_eastmoney_then_dedupes(self) -> None:
        cls = FakeClsSession(
            self._cls_payload(
                [{"title": "CLS only", "content": "x", "ctime": self._timestamp("2026-06-10 09:00")}]
            )
        )
        em = FakeEastmoney(
            fast_rows=[
                {
                    "title": "Shared headline",
                    "content": "from EM",
                    "time": "2026-06-10 10:00",
                    "source": "Eastmoney Global",
                },
            ]
        )

        result = get_global_news(
            "2026-06-10", limit=10, eastmoney=em, cls_session=cls
        )

        titles = [i.title for i in result.items]
        assert "CLS only" in titles
        assert "Shared headline" in titles
        assert result.source == "cls+eastmoney"

    def test_dedupe_across_sources_strips_and_lowercases(self) -> None:
        cls = FakeClsSession(
            self._cls_payload(
                [{"title": "  Same Story  ", "content": "cls", "ctime": self._timestamp("2026-06-10 09:00")}]
            )
        )
        em = FakeEastmoney(
            fast_rows=[
                {
                    "title": "same story",
                    "content": "em",
                    "time": "2026-06-10 10:00",
                    "source": "Eastmoney Global",
                }
            ]
        )

        result = get_global_news(
            "2026-06-10", limit=10, eastmoney=em, cls_session=cls
        )

        assert len(result.items) == 1

    def test_respects_limit_after_dedupe(self) -> None:
        rows = [
            {
                "title": f"headline {i}",
                "content": "c",
                "ctime": self._timestamp("2026-06-10 09:00") + i,
            }
            for i in range(8)
        ]
        cls = FakeClsSession(self._cls_payload(rows))
        em = FakeEastmoney(fast_rows=[])

        result = get_global_news(
            "2026-06-10", limit=3, eastmoney=em, cls_session=cls
        )

        assert len(result.items) == 3

    def test_cls_failure_degrades_to_eastmoney_only(self) -> None:
        cls = FakeClsSession(RuntimeError("cls down"))
        em = FakeEastmoney(
            fast_rows=[
                {
                    "title": "EM survives",
                    "content": "c",
                    "time": "2026-06-10 10:00",
                    "source": "Eastmoney Global",
                }
            ]
        )

        result = get_global_news(
            "2026-06-10", limit=10, eastmoney=em, cls_session=cls
        )

        titles = [i.title for i in result.items]
        assert titles == ["EM survives"]
        assert result.source == "cls+eastmoney"

    def test_cls_converts_ctime_to_time_string(self) -> None:
        cls = FakeClsSession(
            self._cls_payload(
                [{"title": "ts", "content": "c", "ctime": self._timestamp("2026-06-10 09:00")}]
            )
        )
        em = FakeEastmoney(fast_rows=[])

        result = get_global_news(
            "2026-06-10", limit=10, eastmoney=em, cls_session=cls
        )

        item = result.items[0]
        assert item.time is not None
        assert item.source == "CLS Wire"

    def test_global_result_shape(self) -> None:
        cls = FakeClsSession(
            self._cls_payload(
                [{"title": "x", "content": "c", "ctime": self._timestamp("2026-06-10 09:00")}]
            )
        )
        em = FakeEastmoney(fast_rows=[])
        result = get_global_news(
            "2026-06-10", limit=10, eastmoney=em, cls_session=cls
        )
        assert result.source == "cls+eastmoney"
        assert isinstance(result.retrieved_at, dt.datetime)
        assert all(hasattr(i, "title") for i in result.items)

    def test_historical_request_paginates_until_target_window(self) -> None:
        em = FakeEastmoney(
            fast_pages=[
                (
                    [
                        {
                            "title": "too new",
                            "time": "2026-08-02 10:00",
                            "source": "Eastmoney Global",
                        }
                    ],
                    "cursor-1",
                ),
                (
                    [
                        {
                            "title": "target day",
                            "time": "2026-07-31 15:00",
                            "source": "Eastmoney Global",
                        },
                        {
                            "title": "too old",
                            "time": "2026-07-30 23:59",
                            "source": "Eastmoney Global",
                        },
                    ],
                    "cursor-2",
                ),
            ]
        )

        result = get_global_news(
            "2026-07-31",
            look_back_days=1,
            limit=15,
            eastmoney=em,
            cls_session=FakeClsSession({"data": {"roll_data": []}}),
        )

        assert [item.title for item in result.items] == ["target day"]
        assert em.fast_page_calls == [(100, ""), (100, "cursor-1")]

    def test_historical_request_drops_out_of_window_live_rows(self) -> None:
        em = FakeEastmoney(
            fast_rows=[
                {
                    "title": "wrong day",
                    "time": "2026-08-02 10:00",
                    "source": "Eastmoney Global",
                }
            ]
        )

        result = get_global_news(
            "2026-07-31",
            look_back_days=1,
            limit=15,
            eastmoney=em,
            cls_session=FakeClsSession({"data": {"roll_data": []}}),
        )

        assert result.items == []
        assert any("requested news window" in warning for warning in result.warnings)

    def test_legacy_wrong_date_cache_is_ignored_and_replaced(self) -> None:
        cache = FakeCache(
            {
                "items": [
                    {
                        "title": "polluted cache",
                        "time": "2026-08-02 10:00",
                        "source": "Eastmoney Global",
                    }
                ]
            }
        )
        em = FakeEastmoney(
            fast_rows=[
                {
                    "title": "correct historical item",
                    "time": "2026-07-31 10:00",
                    "source": "Eastmoney Global",
                }
            ]
        )

        result = get_global_news(
            "2026-07-31",
            look_back_days=1,
            limit=15,
            eastmoney=em,
            cls_session=FakeClsSession({"data": {"roll_data": []}}),
            cache=cache,  # type: ignore[arg-type]
        )

        assert [item.title for item in result.items] == ["correct historical item"]
        assert cache.writes[-1][3]["window_end"] == "2026-07-31"

    def test_valid_window_cache_reads_iso_datetime(self) -> None:
        cache = FakeCache(
            {
                "items": [
                    {
                        "title": "cached historical item",
                        "time": "2026-07-31T10:00:00",
                        "source": "Eastmoney Global",
                    }
                ],
                "window_start": "2026-07-31",
                "window_end": "2026-07-31",
                "complete": True,
                "limit": 15,
                "warnings": [],
            }
        )
        em = FakeEastmoney(fast_error=AssertionError("network must not be called"))

        result = get_global_news(
            "2026-07-31",
            look_back_days=1,
            limit=15,
            eastmoney=em,
            cache=cache,  # type: ignore[arg-type]
        )

        assert [item.title for item in result.items] == ["cached historical item"]
        assert em.fast_page_calls == []


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_parse_date_valid(self) -> None:
        assert _parse_date("2026-06-10 09:30") == dt.date(2026, 6, 10)
        assert _parse_date("2026-06-10") == dt.date(2026, 6, 10)

    def test_parse_date_invalid_returns_none(self) -> None:
        assert _parse_date("not a date") is None
        assert _parse_date("") is None
        assert _parse_date(None) is None  # type: ignore[arg-type]

    def test_to_news_item_handles_missing_fields(self) -> None:
        item = _to_news_item({"title": "t"})
        assert item.title == "t"
        assert item.content is None
        assert item.source is None
        assert item.url is None
        assert item.time is None

    def test_filter_by_date_keeps_none_time(self) -> None:
        items = [
            _to_news_item({"title": "a", "time": "2026-06-10"}),
            _to_news_item({"title": "b", "time": "garbage"}),
        ]
        kept = _filter_by_date(items, dt.date(2026, 6, 1), dt.date(2026, 6, 30))
        titles = sorted(i.title for i in kept)
        assert titles == ["a", "b"]

    def test_dedupe_preserves_order(self) -> None:
        items = [
            _to_news_item({"title": "first"}),
            _to_news_item({"title": "second"}),
            _to_news_item({"title": "FIRST"}),  # dup of first
        ]
        kept = _dedupe_and_limit(items, limit=10)
        assert [i.title for i in kept] == ["first", "second"]
