"""A 股市场交易日历与交易时段严格校验层。

本模块提供保守的、零外部依赖的中国 A 股交易日/交易时段判定，仅基于
硬编码的法定节假日规则 + 周末规则。不调用任何外部交易日历 API 或库。

设计取舍：节假日使用「范围近似」而非精确每年调休表 —— 调休安排每年由
国务院发布且常与周末挪动相关，精确表需要逐年维护并引入外部数据。
这里采用每个法定节假日的典型公历窗口（春节按农历近似固定窗口），
保守地把整个窗口判为非交易日。代价是极少数「调休补班」的周末会被
误判为非交易日（保守方向，宁可拒绝也不误放行）。
"""

from __future__ import annotations

import datetime as _dt
from typing import Union

from .errors import MarketValidationError

# ── 输入类型 ──────────────────────────────────────────────────────────
# 公开函数接受 str(YYYY-MM-DD) / date / datetime。
DateLike = Union[str, _dt.date, _dt.datetime]

# ── 交易时段（A 股集合竞价外的连续竞价时段）─────────────────────────
# 早盘 09:30-11:30，午盘 13:00-15:00；不含集合竞价（9:15-9:25）。
_MORNING_START = _dt.time(9, 30)
_MORNING_END = _dt.time(11, 30)
_AFTERNOON_START = _dt.time(13, 0)
_AFTERNOON_END = _dt.time(15, 0)

# ── 日期格式 ──────────────────────────────────────────────────────────
_DATE_FORMAT = "%Y-%m-%d"

# 查询日期允许的最早年份（避免明显无效的历史区间下限引发解析歧义）。
_MIN_YEAR = 1990

# 区间上限：约 2 年的未来（以天数为容差），超过即视为越界。
_MAX_FUTURE_DAYS = 731  # ~2 年


def _build_holiday_windows() -> tuple[tuple[int, int, int], ...]:
    """构造并返回法定节假日窗口表。

    每个条目 (month, start_day, end_day) 表示该月份内 [start_day, end_day]
    闭区间判为假期。春节采用公历近似窗口（实际农历春节落在 1/21-2/20 之间，
    取较宽窗口覆盖绝大多数年份；调休补班日因属周末被保守判为非交易日）。

    保守策略：宁可把可能的交易日判成非交易日，也不会把任何确定非交易日
    判成交易日。对 strict=True 场景，极少数调休补班周末会被拒绝，
    符合「宁可校验失败也不放行可疑输入」的目标。
    """
    # (month, start_day, end_day) 闭区间
    return (
        (1, 1, 3),      # 元旦（含前后调休余量）
        (2, 4, 10),     # 春节（公历近似窗口，覆盖 1/21-2/20 的多数年份）
        (4, 4, 6),      # 清明节（4/4-4/6）
        (5, 1, 5),      # 劳动节（5/1-5/5）
        (6, 9, 11),     # 端午节（近似，公历 6 月上中旬浮动）
        (9, 14, 16),    # 中秋节（近似，公历 9 月中旬浮动）
        (10, 1, 7),     # 国庆节（10/1-10/7）
    )


_HOLIDAYS: tuple[tuple[int, int, int], ...] = _build_holiday_windows()


# ── 内部工具：输入归一化 ──────────────────────────────────────────────
def _to_date(value: DateLike, *, field: str = "date") -> _dt.date:
    """把 str/date/datetime 归一化为 date。

    - date → 原样
    - datetime → 取 .date()
    - str → 严格 YYYY-MM-DD 解析（拒绝其它格式）
    解析失败抛 MarketValidationError 并附 actionable 提示。
    """
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        # 注意：datetime 是 date 的子类，上面已先匹配，这里只剩纯 date。
        return value
    if isinstance(value, str):
        s = value.strip()
        # 严格校验格式：不允许 'YYYY/MM-DD' 等变体。
        try:
            parsed = _dt.datetime.strptime(s, _DATE_FORMAT).date()
        except (ValueError, TypeError) as exc:
            raise MarketValidationError(
                f"Invalid {field} format: {value!r}. "
                f"Expected 'YYYY-MM-DD' (e.g. '2026-05-12')."
            ) from exc
        # strptime 会把 '2026-5-3' 也当合法（%d 允许单位数），再校验回写一致性
        # 以拒绝 '2026-13-01' 这类越界月/日（strptime 已会拒绝月份 13）。
        # strptime 已覆盖月份/日期越界；这里只做格式往返一致性兜底。
        if parsed.strftime(_DATE_FORMAT) != s:
            raise MarketValidationError(
                f"Invalid {field} format: {value!r}. "
                f"Expected 'YYYY-MM-DD' (e.g. '2026-05-12')."
            )
        return parsed
    raise MarketValidationError(
        f"Unsupported {field} type {type(value).__name__}: {value!r}. "
        f"Expected str 'YYYY-MM-DD', date, or datetime."
    )


def _to_time(value: DateLike) -> tuple[_dt.date, _dt.time | None]:
    """归一化 datetime 类输入用于交易时段判定。

    返回 (date, time_or_None)：纯 str/date 输入 time 为 None。
    """
    if isinstance(value, _dt.datetime):
        return value.date(), value.time().replace(microsecond=0)
    if isinstance(value, _dt.date):
        return value, None
    if isinstance(value, str):
        s = value.strip()
        # 允许 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM' 两种格式。
        try:
            parsed_dt = _dt.datetime.strptime(s, "%Y-%m-%d %H:%M")
            return parsed_dt.date(), parsed_dt.time()
        except ValueError:
            pass
        parsed_date = _to_time_date_only(s)
        return parsed_date, None
    raise MarketValidationError(
        f"Unsupported value type {type(value).__name__}: {value!r}. "
        f"Expected str, date, or datetime."
    )


def _to_time_date_only(s: str) -> _dt.date:
    try:
        parsed = _dt.datetime.strptime(s, _DATE_FORMAT).date()
    except (ValueError, TypeError) as exc:
        raise MarketValidationError(
            f"Invalid datetime format: {s!r}. "
            f"Expected 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'."
        ) from exc
    if parsed.strftime(_DATE_FORMAT) != s:
        raise MarketValidationError(
            f"Invalid datetime format: {s!r}. "
            f"Expected 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM'."
        )
    return parsed


def _is_in_holiday_window(d: _dt.date) -> bool:
    """判断 date 是否落入任一法定节假日窗口。"""
    for month, start_day, end_day in _HOLIDAYS:
        if d.month == month and start_day <= d.day <= end_day:
            return True
    return False


# ── 公开 API ──────────────────────────────────────────────────────────
def is_trading_day(date: DateLike) -> bool:
    """判断是否为 A 股交易日（保守规则）。

    规则：周一至周五 且 不落入硬编码法定节假日窗口 → True。
    周末或节假日 → False。无外部 API 调用。

    保守性：调休补班的周末会被判为 False（非交易日），宁可拒绝。
    """
    d = _to_date(date)
    if d.weekday() >= 5:  # 5=周六, 6=周日
        return False
    return not _is_in_holiday_window(d)


def is_trading_hours(dt_value: DateLike) -> bool:
    """判断给定时刻是否处于 A 股连续竞价交易时段。

    时段：09:30-11:30（含 09:30，不含 11:30）或 13:00-15:00
    （含 13:00，不含 15:00），且必须是交易日。

    输入仅含日期（无时间分量）时返回 False（无具体时刻无法判定）。
    """
    d, t = _to_time(dt_value)
    if t is None:
        # 无时间分量，无法判定是否在时段内 → 保守 False。
        return False
    if not is_trading_day(d):
        return False
    if _MORNING_START <= t < _MORNING_END:
        return True
    if _AFTERNOON_START <= t < _AFTERNOON_END:
        return True
    return False


def validate_date_range(start: DateLike, end: DateLike) -> None:
    """校验日期区间合法性，失败抛 MarketValidationError。

    校验项：
    - start/end 格式必须为合法 YYYY-MM-DD；
    - end 不得早于 start（区间倒置）；
    - end 不得超出当前日期约 2 年的未来（防止误输入远期年份）；
    - start 不得早于 1990 年（A 股两市最早成立年，防明显无效历史区间）。
    """
    start_date = _to_date(start, field="start")
    end_date = _to_date(end, field="end")

    if end_date < start_date:
        raise MarketValidationError(
            f"Invalid date range: end {end_date.isoformat()} is earlier "
            f"than start {start_date.isoformat()}."
        )

    today = _dt.date.today()
    if end_date > today + _dt.timedelta(days=_MAX_FUTURE_DAYS):
        raise MarketValidationError(
            f"Invalid date range: end {end_date.isoformat()} is more than "
            f"~{_MAX_FUTURE_DAYS} days in the future (today={today.isoformat()})."
        )
    if start_date.year < _MIN_YEAR:
        raise MarketValidationError(
            f"Invalid date range: start {start_date.isoformat()} is before "
            f"{_MIN_YEAR} (earliest supported A-share history year)."
        )


def validate_query_date(
    date_str: DateLike, *, strict: bool = True
) -> None:
    """校验查询日期。

    - 始终校验格式合法性；
    - strict=True 时，若非交易日则抛 MarketValidationError（含原因）；
    - strict=False 时跳过交易日判定（仅校验格式），用于允许查询非交易日
      （此时下游服务应自行回退到最近交易日）。
    """
    d = _to_date(date_str, field="query_date")

    if not strict:
        return

    if d.weekday() >= 5:
        raise MarketValidationError(
            f"{d.isoformat()} is not a trading day (weekend)."
        )
    if _is_in_holiday_window(d):
        raise MarketValidationError(
            f"{d.isoformat()} is not a trading day (falls in a CN public "
            f"holiday window)."
        )


def trading_day_before(date_str: DateLike) -> str:
    """返回给定日期之前（不含当日）的最近交易日，格式 YYYY-MM-DD。

    从给定日期的前一天起向前扫描，跳过周末与节假日窗口，
    返回首个交易日。给定日期本身是交易日时仍返回其前一个交易日。
    """
    d = _to_date(date_str, field="date_str")
    # 安全上限：最坏情况跨多个连续假期（国庆+周末），扫 30 天足够。
    for offset in range(1, 31):
        candidate = d - _dt.timedelta(days=offset)
        if candidate.weekday() < 5 and not _is_in_holiday_window(candidate):
            return candidate.strftime(_DATE_FORMAT)
    # 理论上不会走到（连续假期不可能超 30 天）。
    raise MarketValidationError(
        f"Could not find a trading day before {d.isoformat()} within 30 days."
    )


__all__ = [
    "is_trading_day",
    "is_trading_hours",
    "validate_date_range",
    "validate_query_date",
    "trading_day_before",
]
