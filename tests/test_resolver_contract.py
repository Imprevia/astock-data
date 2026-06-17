import pytest

from astock_data.errors import (
    AmbiguousTickerError,
    InvalidTickerError,
    TickerResolutionError,
)
from astock_data.models.base import Ticker

resolver = pytest.importorskip(
    "astock_data.resolver", reason="Task 8 has not implemented astock_data.resolver yet"
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        ("688017", "688017"),
        ("SH688017", "688017"),
        ("688017.SH", "688017"),
        ("sz000001", "000001"),
        ("BJ835185", "835185"),
    ],
)
def test_normalize_ticker_accepts_common_a_share_forms(raw, expected_code):
    assert resolver.normalize_ticker(raw) == expected_code


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["../secret", ""])
def test_normalize_ticker_rejects_unsafe_or_empty_input(raw):
    with pytest.raises(InvalidTickerError):
        resolver.normalize_ticker(raw)


@pytest.mark.unit
def test_resolve_ticker_accepts_code_with_injected_name_map():
    """Contract: resolve_ticker accepts name_map=... and never fetches live mootdx in tests."""
    fake_name_map = {"科创信息": [Ticker(code="688017", market="sh", name="科创信息")]}

    result = resolver.resolve_ticker("688017", name_map=fake_name_map)

    assert result == Ticker(code="688017", market="sh")


@pytest.mark.unit
def test_resolve_ticker_accepts_exact_chinese_name_with_injected_name_map():
    """Contract: Chinese names resolve only through an injected fake name map here."""
    expected = Ticker(code="000001", market="sz", name="平安银行")
    fake_name_map = {"平安银行": [expected], "科创信息": [Ticker(code="688017", market="sh", name="科创信息")]}

    assert resolver.resolve_ticker("平安银行", name_map=fake_name_map) == expected


@pytest.mark.unit
def test_resolve_ticker_rejects_ambiguous_chinese_substring_with_injected_name_map():
    """Contract: substring matches that produce multiple candidates are ambiguous."""
    fake_name_map = {
        "平安银行": [Ticker(code="000001", market="sz", name="平安银行")],
        "中国平安": [Ticker(code="601318", market="sh", name="中国平安")],
    }

    with pytest.raises(AmbiguousTickerError):
        resolver.resolve_ticker("平安", name_map=fake_name_map)


@pytest.mark.unit
def test_resolve_ticker_rejects_unknown_chinese_name_with_injected_name_map():
    """Contract: unknown Chinese names fail with the resolver error taxonomy."""
    fake_name_map = {"平安银行": [Ticker(code="000001", market="sz", name="平安银行")]}

    with pytest.raises((InvalidTickerError, TickerResolutionError)):
        resolver.resolve_ticker("不存在股票", name_map=fake_name_map)


@pytest.mark.public_entrypoints
def test_public_services_have_single_common_resolver_entrypoint():
    """Guard rail: future dragon-tiger, lockup, and industry services route via resolve_ticker."""
    assert resolver.resolve_ticker is getattr(resolver, "resolve_ticker")
    assert callable(resolver.resolve_ticker)
