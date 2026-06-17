"""astock_data.market 严格市场校验层的单元测试。

覆盖：交易日判定、交易时段判定、区间校验（倒置/越界/格式）、查询日严格/宽松
模式、trading_day_before 跨周末/假期跳过、str/date/datetime 输入归一化、
错误类型与可操作提示信息。全部离线、零外部依赖。
"""

from __future__ import annotations

import datetime as dt

import pytest

from astock_data import market
from astock_data.errors import AStockDataError, MarketValidationError

pytestmark = pytest.mark.unit


# ── is_trading_day ────────────────────────────────────────────────────
class TestIsTradingDay:
    def test_weekday_is_trading_day(self):
        # 2026-05-12 是周二
        assert market.is_trading_day("2026-05-12") is True

    def test_saturday_is_not_trading_day(self):
        assert market.is_trading_day("2026-05-16") is False

    def test_sunday_is_not_trading_day(self):
        # 2026-05-17 是周日
        assert market.is_trading_day("2026-05-17") is False

    def test_national_day_holiday_is_not_trading_day(self):
        # 10/1 国庆窗口
        assert market.is_trading_day("2026-10-01") is False
        assert market.is_trading_day("2026-10-07") is False

    def test_spring_festival_holiday_is_not_trading_day(self):
        # 春节窗口 2/4-2/10
        assert market.is_trading_day("2026-02-05") is False

    def test_labor_day_holiday_is_not_trading_day(self):
        assert market.is_trading_day("2026-05-01") is False

    def test_accepts_date_object(self):
        assert market.is_trading_day(dt.date(2026, 5, 12)) is True
        assert market.is_trading_day(dt.date(2026, 5, 16)) is False

    def test_accepts_datetime_object(self):
        assert market.is_trading_day(dt.datetime(2026, 5, 12, 10, 0)) is True
        assert market.is_trading_day(dt.datetime(2026, 5, 16, 10, 0)) is False

    def test_invalid_format_raises(self):
        with pytest.raises(MarketValidationError):
            market.is_trading_day("2026/05/12")

    def test_bad_date_raises(self):
        with pytest.raises(MarketValidationError):
            market.is_trading_day("2026-13-40")

    def test_unsupported_type_raises(self):
        with pytest.raises(MarketValidationError):
            market.is_trading_day(20260512)  # type: ignore[arg-type]


# ── is_trading_hours ──────────────────────────────────────────────────
class TestIsTradingHours:
    def test_morning_session_in_range(self):
        # 09:30 含, 10:00, 11:00
        assert market.is_trading_hours(dt.datetime(2026, 5, 12, 9, 30)) is True
        assert market.is_trading_hours(dt.datetime(2026, 5, 12, 10, 0)) is True
        assert market.is_trading_hours(dt.datetime(2026, 5, 12, 11, 29)) is True

    def test_morning_end_excluded(self):
        # 11:30 不含
        assert market.is_trading_hours(dt.datetime(2026, 5, 12, 11, 30)) is False

    def test_lunch_break_excluded(self):
        # 12:00 午休
        assert market.is_trading_hours(dt.datetime(2026, 5, 12, 12, 0)) is False

    def test_afternoon_session_in_range(self):
        # 13:00 含, 14:00
        assert market.is_trading_hours(dt.datetime(2026, 5, 12, 13, 0)) is True
        assert market.is_trading_hours(dt.datetime(2026, 5, 12, 14, 59)) is True

    def test_afternoon_end_excluded(self):
        # 15:00 收市不含
        assert market.is_trading_hours(dt.datetime(2026, 5, 12, 15, 0)) is False

    def test_pre_market_excluded(self):
        assert market.is_trading_hours(dt.datetime(2026, 5, 12, 9, 0)) is False
        assert market.is_trading_hours(dt.datetime(2026, 5, 12, 9, 29)) is False

    def test_weekend_outside_hours(self):
        # 周六即使是交易时段也 False
        assert market.is_trading_hours(dt.datetime(2026, 5, 16, 10, 0)) is False

    def test_holiday_outside_hours(self):
        # 国庆即使时段内也 False
        assert market.is_trading_hours(dt.datetime(2026, 10, 1, 10, 0)) is False

    def test_accepts_datetime_string(self):
        assert market.is_trading_hours("2026-05-12 10:00") is True
        assert market.is_trading_hours("2026-05-12 12:00") is False

    def test_date_only_no_time_returns_false(self):
        # 纯日期无时间分量 → 保守 False
        assert market.is_trading_hours("2026-05-12") is False
        assert market.is_trading_hours(dt.date(2026, 5, 12)) is False


# ── validate_date_range ─────────────────────────────────────────────
class TestValidateDateRange:
    def test_valid_range_passes(self):
        # 不抛即通过
        market.validate_date_range("2026-01-01", "2026-05-12")

    def test_equal_dates_passes(self):
        market.validate_date_range("2026-05-12", "2026-05-12")

    def test_inverted_range_raises(self):
        with pytest.raises(MarketValidationError) as exc:
            market.validate_date_range("2026-05-12", "2026-01-01")
        assert "earlier" in str(exc.value)

    def test_invalid_start_format_raises(self):
        with pytest.raises(MarketValidationError):
            market.validate_date_range("2026/01/01", "2026-05-12")

    def test_invalid_end_format_raises(self):
        with pytest.raises(MarketValidationError):
            market.validate_date_range("2026-01-01", "not-a-date")

    def test_far_future_end_raises(self):
        today = dt.date.today()
        far_future = today + dt.timedelta(days=800)  # > ~2y
        with pytest.raises(MarketValidationError) as exc:
            market.validate_date_range(today.isoformat(), far_future.isoformat())
        assert "future" in str(exc.value)

    def test_just_under_two_years_end_passes(self):
        today = dt.date.today()
        near = today + dt.timedelta(days=700)  # < ~2y
        market.validate_date_range(today.isoformat(), near.isoformat())

    def test_pre_1990_start_raises(self):
        with pytest.raises(MarketValidationError) as exc:
            market.validate_date_range("1989-01-01", "2026-05-12")
        assert "1990" in str(exc.value)

    def test_accepts_date_objects(self):
        market.validate_date_range(dt.date(2026, 1, 1), dt.date(2026, 5, 12))

    def test_accepts_datetime_objects(self):
        market.validate_date_range(
            dt.datetime(2026, 1, 1, 9, 30), dt.datetime(2026, 5, 12, 15, 0)
        )


# ── validate_query_date ─────────────────────────────────────────────
class TestValidateQueryDate:
    def test_strict_trading_day_passes(self):
        market.validate_query_date("2026-05-12", strict=True)

    def test_strict_weekend_raises(self):
        with pytest.raises(MarketValidationError) as exc:
            market.validate_query_date("2026-05-16", strict=True)
        assert "weekend" in str(exc.value)

    def test_strict_holiday_raises(self):
        with pytest.raises(MarketValidationError) as exc:
            market.validate_query_date("2026-10-01", strict=True)
        assert "holiday" in str(exc.value)

    def test_strict_spring_festival_raises(self):
        with pytest.raises(MarketValidationError):
            market.validate_query_date("2026-02-05", strict=True)

    def test_non_strict_weekend_passes(self):
        # strict=False 跳过交易日判定
        market.validate_query_date("2026-05-16", strict=False)

    def test_non_strict_holiday_passes(self):
        market.validate_query_date("2026-10-01", strict=False)

    def test_invalid_format_always_raises_even_non_strict(self):
        # 格式校验不随 strict 切换
        with pytest.raises(MarketValidationError):
            market.validate_query_date("2026/10/01", strict=False)

    def test_default_strict_is_true(self):
        # 不传 strict 即默认严格
        with pytest.raises(MarketValidationError):
            market.validate_query_date("2026-10-01")


# ── trading_day_before ──────────────────────────────────────────────
class TestTradingDayBefore:
    def test_previous_weekday(self):
        # 2026-05-12 周二 → 前一交易日 2026-05-11 周一
        assert market.trading_day_before("2026-05-12") == "2026-05-11"

    def test_skips_weekend_from_monday(self):
        # 2026-05-11 周一 → 跳过周末 → 2026-05-08 周五
        assert market.trading_day_before("2026-05-11") == "2026-05-08"

    def test_skips_weekend_from_sunday(self):
        # 2026-05-17 周日（非交易日）→ 前一交易日仍是 2026-05-15 周五
        assert market.trading_day_before("2026-05-17") == "2026-05-15"

    def test_skips_national_day_holiday(self):
        # 2026-10-08 周四（国庆后首个工作日）→ 前一交易日应跳过 10/1-10/7 → 2026-09-30 周三
        assert market.trading_day_before("2026-10-08") == "2026-09-30"

    def test_returns_string_in_iso_format(self):
        result = market.trading_day_before("2026-05-12")
        assert isinstance(result, str)
        assert len(result) == 10
        assert result[4] == "-" and result[7] == "-"

    def test_accepts_date_object(self):
        assert market.trading_day_before(dt.date(2026, 5, 11)) == "2026-05-08"

    def test_accepts_datetime_object(self):
        assert (
            market.trading_day_before(dt.datetime(2026, 5, 11, 10, 0))
            == "2026-05-08"
        )

    def test_invalid_format_raises(self):
        with pytest.raises(MarketValidationError):
            market.trading_day_before("20260511")


# ── 错误类型层级 ────────────────────────────────────────────────────
class TestErrorTaxonomy:
    def test_market_validation_error_is_astock_error(self):
        assert issubclass(MarketValidationError, AStockDataError)

    def test_all_validators_raise_market_validation_error(self):
        # 确保所有校验失败都抛 MarketValidationError（非裸 ValueError）
        with pytest.raises(MarketValidationError):
            market.is_trading_day("bad")
        with pytest.raises(MarketValidationError):
            market.validate_date_range("2026-05-12", "2026-01-01")
        with pytest.raises(MarketValidationError):
            market.validate_query_date("2026-10-01")
        with pytest.raises(MarketValidationError):
            market.trading_day_before("bad")
