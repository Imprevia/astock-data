"""Unit tests for :mod:`astock_data.clients.tdx` (TdxClient).

All tests use a FAKE mootdx-like object injected via ``TdxClient(client=...)``;
no live TCP connection is ever opened.
"""

from __future__ import annotations

import pandas as pd
import pytest

from astock_data.clients.tdx import TdxClient

pytestmark = pytest.mark.unit


class FakeMootdx:
    """Minimal mootdx-like double returning pandas DataFrames.

    Mirrors the real ``mootdx.quotes.Quotes`` instance surface used by
    :class:`TdxClient`: ``stocks`` / ``bars`` / ``F10`` / ``finance``.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def stocks(self, market=1):
        self.calls.append(("stocks", (market,), {}))
        # market 0 = SZ (incl. ChiNext 3xxx + Beijing 8xxx bundled in),
        # market 1 = SH main (6xxx) + STAR (688xxx).
        if market == 0:
            return pd.DataFrame(
                [
                    {"code": "000001", "name": " 平安银行 "},  # whitespace
                    {"code": "835185", "name": "　长虹能源"},  # Beijing + full-width
                    {"code": "300001", "name": "特锐德"},
                    {"code": "2abcdef", "name": "should-be-filtered"},  # bad code
                    {"code": "9", "name": "too-short"},
                ]
            )
        if market == 1:
            return pd.DataFrame(
                [
                    {"code": "688017", "name": "绿的谐波"},
                    {"code": "600000", "name": "浦发银行"},
                    {"code": "510300", "name": "ETF-should-be-filtered"},  # 5xxxxx
                ]
            )
        return pd.DataFrame()

    def bars(self, symbol="000001", frequency=9, start=0, offset=100, **kwargs):
        self.calls.append(("bars", (symbol,), {"category": kwargs.get("category"), "offset": offset}))
        # mootdx returns a DF indexed by 'datetime' PLUS a 'datetime' column and
        # split year/month/day/hour/minute columns plus 'amount'. Tests assert
        # these are all dropped / collapsed correctly.
        return pd.DataFrame(
            [
                {
                    "datetime": "2026-06-16",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.5,
                    "close": 10.8,
                    "volume": 12345,
                    "amount": 99999.0,
                    "year": 2026,
                    "month": 6,
                    "day": 16,
                    "hour": 15,
                    "minute": 0,
                },
                {
                    "datetime": "2026-06-17",
                    "open": 10.8,
                    "high": 11.5,
                    "low": 10.6,
                    "close": 11.2,
                    "volume": 9876,
                    "amount": 55555.0,
                    "year": 2026,
                    "month": 6,
                    "day": 17,
                    "hour": 15,
                    "minute": 0,
                },
            ]
        )

    def F10(self, symbol="", name=""):
        self.calls.append(("F10", (symbol,), {"name": name}))
        return (
            "【1.公司简介】\n某公司简介内容\n"
            "【2.股东研究】\n十大股东信息\n"
            "【3.股本结构】\n股本结构详情"
        )

    def finance(self, symbol="000001", **kwargs):
        self.calls.append(("finance", (symbol,), {}))
        return pd.DataFrame(
            [
                {
                    "liutongguben": 1.9e9,
                    "guben": 2.0e9,
                    "jingzichan": 3.0e10,
                    "meigujingzichan": 15.0,
                    "meigushouyi": 1.2,
                    "unknown_extra": "keep-in-raw",
                }
            ]
        )


# ---------------------------------------------------------------------------
# stocks / name map
# ---------------------------------------------------------------------------


def test_build_name_map_includes_beijing_and_filters_invalid():
    """Beijing ``835185`` must appear alongside ``688017``/``000001`` and
    invalid codes (5xxxxx ETF, malformed) must be filtered out."""
    fake = FakeMootdx()
    client = TdxClient(client=fake)

    name_to_code, code_to_name = client.build_name_map()

    assert "688017" in code_to_name
    assert "000001" in code_to_name
    # THE bug fix: Beijing Exchange 8xxxxx must be present.
    assert "835185" in code_to_name
    assert "835185" in name_to_code.values()
    # Invalid / unsupported codes filtered out.
    assert "510300" not in code_to_name
    assert "2abcdef" not in code_to_name
    assert "9" not in code_to_name


def test_stock_names_whitespace_stripped():
    """Leading/trailing whitespace and full-width 　 must be collapsed."""
    fake = FakeMootdx()
    client = TdxClient(client=fake)

    stocks = client.stocks()
    by_code = {s["code"]: s["name"] for s in stocks}

    # " 平安银行 " -> "平安银行"
    assert by_code["000001"] == "平安银行"
    # "　长虹能源" (full-width space) -> "长虹能源"
    assert by_code["835185"] == "长虹能源"


# ---------------------------------------------------------------------------
# daily_bars normalization
# ---------------------------------------------------------------------------


def test_daily_bars_normalizes_to_ohlcv():
    """daily_bars must emit rows with exactly date/open/high/low/close/volume,
    dropping amount and the redundant split datetime columns."""
    fake = FakeMootdx()
    client = TdxClient(client=fake)

    rows = client.daily_bars("688017", offset=800)

    assert len(rows) == 2
    expected_keys = {"date", "open", "high", "low", "close", "volume"}
    for row in rows:
        assert set(row.keys()) == expected_keys

    first = rows[0]
    assert first["date"] == "2026-06-16"
    assert first["open"] == 10.0
    assert first["high"] == 11.0
    assert first["low"] == 9.5
    assert first["close"] == 10.8
    assert first["volume"] == 12345
    # amount dropped
    assert "amount" not in first


def test_daily_bars_passes_category_and_offset():
    fake = FakeMootdx()
    client = TdxClient(client=fake)
    client.daily_bars("000001", offset=100)

    bars_calls = [c for c in fake.calls if c[0] == "bars"]
    assert bars_calls, "bars() must be invoked on the underlying client"
    _, _, kwargs = bars_calls[0]
    assert kwargs["category"] == 4  # daily
    assert kwargs["offset"] == 100


@pytest.mark.parametrize(
    "period,category",
    [
        ("day", 4),
        ("week", 5),
        ("month", 6),
        ("1min", 8),
        ("5min", 0),
        ("15min", 1),
        ("30min", 2),
        ("60min", 3),
    ],
)
def test_bars_period_maps_to_mootdx_category(period, category):
    fake = FakeMootdx()
    client = TdxClient(client=fake)

    client.bars("000001", period=period, offset=123)

    bars_calls = [c for c in fake.calls if c[0] == "bars"]
    assert bars_calls[-1][2]["category"] == category
    assert bars_calls[-1][2]["offset"] == 123


def test_bars_invalid_period_raises_value_error():
    with pytest.raises(ValueError, match="Unsupported K-line period"):
        TdxClient(client=FakeMootdx()).bars("000001", period="2min")


# ---------------------------------------------------------------------------
# f10 shareholders
# ---------------------------------------------------------------------------


def test_f10_shareholders_returns_content_and_sections():
    fake = FakeMootdx()
    client = TdxClient(client=fake)

    result = client.f10_shareholders("688017")

    assert isinstance(result["content"], str)
    assert "股东研究" in result["content"]
    sections = result["sections"]
    assert isinstance(sections, dict)
    assert "股东研究" in sections
    assert "十大股东信息" in sections["股东研究"]


def test_f10_shareholders_passes_name_kwarg():
    fake = FakeMootdx()
    client = TdxClient(client=fake)
    client.f10_shareholders("000001")

    f10_calls = [c for c in fake.calls if c[0] == "F10"]
    assert f10_calls
    _, _, kwargs = f10_calls[0]
    assert kwargs["name"] == "股东研究"


# ---------------------------------------------------------------------------
# financial snapshot
# ---------------------------------------------------------------------------


def test_financial_snapshot_maps_fields_and_keeps_raw():
    fake = FakeMootdx()
    client = TdxClient(client=fake)

    snap = client.financial_snapshot("000001")

    assert snap["code"] == "000001"
    # mapped best-effort fields
    assert snap["float_shares"] == 1.9e9
    assert snap["eps"] == 1.2
    assert snap["nav_per_share"] == 15.0
    # raw payload preserved (incl. unmapped keys)
    assert snap["_raw"]["unknown_extra"] == "keep-in-raw"
    assert snap["_raw"]["liutongguben"] == 1.9e9


# ---------------------------------------------------------------------------
# constructor injection — no Quotes.factory ever called
# ---------------------------------------------------------------------------


def test_constructor_injection_does_not_call_factory(monkeypatch):
    """Passing ``client=`` must short-circuit the lazy singleton so the real
    ``Quotes.factory`` is never invoked."""

    def _factory_boom(*a, **kw):
        raise AssertionError("Quotes.factory must NOT be called when client= is injected")

    # Patch the deferred import target so even accidental lazy init fails loudly.
    import sys
    import types

    fake_quotes_mod = types.ModuleType("mootdx.quotes")

    class _FakeQuotes:  # pragma: no cover - should never instantiate
        @staticmethod
        def factory(market="std"):
            return _factory_boom()

    fake_quotes_mod.Quotes = _FakeQuotes  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mootdx.quotes", fake_quotes_mod)

    fake = FakeMootdx()
    client = TdxClient(client=fake)

    # Exercise every code path that could lazily build the real client.
    client.stocks()
    client.daily_bars("000001")
    client.financial_snapshot("000001")
    client.f10_shareholders("000001")

    assert fake.calls, "injected fake must have been used"
    # Sanity: the methods we expect were routed to the fake.
    used = {c[0] for c in fake.calls}
    assert {"stocks", "bars", "finance", "F10"} <= used


def test_empty_bars_returns_empty_list():
    fake = FakeMootdx()
    fake.bars = lambda **kw: pd.DataFrame()  # mootdx can return empty DF
    client = TdxClient(client=fake)

    assert client.daily_bars("000001") == []
