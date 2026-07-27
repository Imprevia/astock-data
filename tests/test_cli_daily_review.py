"""契约测试：daily-review 所需的 CLI 子命令。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal
from unittest import mock

import pytest
from typer.testing import CliRunner

from astock_data import cli as cli_module
from astock_data.cli import app

pytestmark = pytest.mark.unit

runner = CliRunner()


@dataclass(frozen=True, slots=True)
class FakeResult:
    """为 CLI 输出提供最小的 Pydantic 结果替身。"""

    payload: dict[str, str]

    def model_dump(self, *, mode: Literal["json"]) -> dict[str, str]:
        """返回可直接编码为 JSON 的结构化结果。"""
        return self.payload


def test_index_kline_command_forwards_key_and_days_as_json() -> None:
    # Given: 指数 K 线命令的独特参数与结构化 API 返回值
    fake = FakeResult({"command": "index-kline", "key": "cyb", "days": "17"})
    with mock.patch.object(cli_module.api, "get_index_kline", return_value=fake) as patched:
        # When: 通过 CLI 调用指数 K 线命令
        result = runner.invoke(app, ["index-kline", "cyb", "--days", "17"])

    # Then: 命令已注册、参数精确转发且 stdout 是机器可解析 JSON
    assert result.exit_code == 0, result.stderr or result.output
    patched.assert_called_once_with("cyb", days=17)
    assert json.loads(result.output) == fake.payload


def test_stock_amount_command_forwards_ticker_and_days_as_json() -> None:
    # Given: 个股成交额命令的独特参数与结构化 API 返回值
    fake = FakeResult({"command": "stock-amount", "ticker": "000858", "days": "23"})
    with mock.patch.object(cli_module.api, "get_stock_amount", return_value=fake) as patched:
        # When: 通过 CLI 调用个股成交额命令
        result = runner.invoke(app, ["stock-amount", "000858", "--days", "23"])

    # Then: 命令已注册、参数精确转发且 stdout 是机器可解析 JSON
    assert result.exit_code == 0, result.stderr or result.output
    patched.assert_called_once_with("000858", days=23)
    assert json.loads(result.output) == fake.payload


def test_sector_fund_flow_command_forwards_date_and_days_as_json() -> None:
    # Given: 板块资金流命令的独特日期窗口与结构化 API 返回值
    fake = FakeResult({"command": "sector-fund-flow", "date": "2026-07-20", "days": "9"})
    with mock.patch.object(cli_module.api, "get_sector_fund_flow", return_value=fake) as patched:
        # When: 通过 CLI 调用板块资金流命令
        result = runner.invoke(
            app,
            ["sector-fund-flow", "--curr-date", "2026-07-20", "--days", "9"],
        )

    # Then: 命令已注册、参数精确转发且 stdout 是机器可解析 JSON
    assert result.exit_code == 0, result.stderr or result.output
    patched.assert_called_once_with("2026-07-20", days=9)
    assert json.loads(result.output) == fake.payload


def test_sector_strength_command_forwards_date_as_json() -> None:
    # Given: 板块强度命令的独特日期与结构化 API 返回值
    fake = FakeResult({"command": "sector-strength", "date": "2026-07-18"})
    with mock.patch.object(cli_module.api, "get_sector_strength", return_value=fake) as patched:
        # When: 通过 CLI 调用板块强度命令
        result = runner.invoke(app, ["sector-strength", "--curr-date", "2026-07-18"])

    # Then: 命令已注册、日期精确转发且 stdout 是机器可解析 JSON
    assert result.exit_code == 0, result.stderr or result.output
    patched.assert_called_once_with("2026-07-18")
    assert json.loads(result.output) == fake.payload


def test_sector_fund_flow_history_command_forwards_repeated_codes_date_and_days() -> None:
    # Given: 重复板块代码、独特日期窗口与结构化 API 返回值
    fake = FakeResult({"command": "sector-fund-flow-history", "codes": "BK0447,BK0912", "days": "11"})
    with mock.patch.object(
        cli_module.api,
        "get_sector_fund_flow_history",
        return_value=fake,
    ) as patched:
        # When: 通过 CLI 调用板块资金流历史命令
        result = runner.invoke(
            app,
            [
                "sector-fund-flow-history",
                "BK0447",
                "BK0912",
                "--curr-date",
                "2026-07-17",
                "--days",
                "11",
            ],
        )

    # Then: 重复位置参数保持顺序、其他参数精确转发且 stdout 是 JSON
    assert result.exit_code == 0, result.stderr or result.output
    patched.assert_called_once_with(["BK0447", "BK0912"], "2026-07-17", 11)
    assert json.loads(result.output) == fake.payload


def test_etf_daily_command_forwards_repeated_codes_and_days_as_json() -> None:
    # Given: 重复 ETF 代码、独特天数与结构化 API 返回值
    fake = FakeResult({"command": "etf-daily", "codes": "512100,515000", "days": "13"})
    with mock.patch.object(cli_module.api, "get_etf_daily", return_value=fake) as patched:
        # When: 通过 CLI 调用 ETF 日线命令
        result = runner.invoke(
            app,
            ["etf-daily", "512100", "515000", "--days", "13"],
        )

    # Then: 重复位置参数保持顺序、天数精确转发且 stdout 是 JSON
    assert result.exit_code == 0, result.stderr or result.output
    patched.assert_called_once_with(["512100", "515000"], days=13)
    assert json.loads(result.output) == fake.payload


@pytest.mark.parametrize(
    "case",
    [
        ("index-kline", ["cyb"], "get_index_kline"),
        ("stock-amount", ["000858"], "get_stock_amount"),
        ("sector-fund-flow", [], "get_sector_fund_flow"),
        (
            "sector-fund-flow-history",
            ["BK0447"],
            "get_sector_fund_flow_history",
        ),
        ("etf-daily", ["512100"], "get_etf_daily"),
    ],
)
@pytest.mark.parametrize("days", ["0", "366"])
def test_days_option_rejects_values_outside_practical_range_before_api_call(
    case: tuple[str, list[str], str],
    days: str,
) -> None:
    # Given: 一个超出 1..365 实用范围的天数
    command, arguments, api_name = case
    with mock.patch.object(cli_module.api, api_name) as patched:
        # When: 通过 CLI 调用任一带 --days 的 daily-review 命令
        result = runner.invoke(app, [command, *arguments, "--days", days])

    # Then: Typer 在进入 API 前以既有参数错误状态拒绝输入
    assert result.exit_code != 0
    patched.assert_not_called()


@pytest.mark.parametrize(
    ("command", "codes", "api_name"),
    [
        ("etf-daily", [f"{code:06d}" for code in range(51)], "get_etf_daily"),
        (
            "sector-fund-flow-history",
            [f"BK{code:04d}" for code in range(51)],
            "get_sector_fund_flow_history",
        ),
    ],
)
def test_code_list_rejects_more_than_fifty_raw_codes_before_api_call(
    command: str,
    codes: list[str],
    api_name: str,
) -> None:
    # Given: 51 个格式有效的原始代码
    with mock.patch.object(cli_module.api, api_name) as patched:
        # When: 通过多代码 CLI 命令提交列表
        result = runner.invoke(app, [command, *codes])

    # Then: CLI 以既有结构化错误状态拒绝并且 API 未调用
    assert result.exit_code != 0
    patched.assert_not_called()


@pytest.mark.parametrize(
    ("command", "invalid_code", "api_name"),
    [
        ("etf-daily", "51210X", "get_etf_daily"),
        ("sector-fund-flow-history", "BK447", "get_sector_fund_flow_history"),
    ],
)
def test_code_list_rejects_invalid_code_format_before_api_call(
    command: str,
    invalid_code: str,
    api_name: str,
) -> None:
    # Given: 一个不符合命令代码格式的值
    with mock.patch.object(cli_module.api, api_name) as patched:
        # When: 通过多代码 CLI 命令提交该值
        result = runner.invoke(app, [command, invalid_code])

    # Then: CLI 以既有结构化错误状态拒绝并且 API 未调用
    assert result.exit_code != 0
    patched.assert_not_called()


def test_etf_code_list_deduplicates_valid_codes_in_first_seen_order() -> None:
    # Given: 含重复项且顺序可观察的有效 ETF 代码列表
    fake = FakeResult({"command": "etf-daily"})
    with mock.patch.object(cli_module.api, "get_etf_daily", return_value=fake) as patched:
        # When: 通过 ETF 日线命令提交列表
        result = runner.invoke(app, ["etf-daily", "512100", "515000", "512100"])

    # Then: API 仅收到首见顺序的唯一代码
    assert result.exit_code == 0, result.stderr or result.output
    patched.assert_called_once_with(["512100", "515000"], days=10)


def test_sector_code_list_deduplicates_valid_codes_in_first_seen_order() -> None:
    # Given: 含重复项且顺序可观察的有效板块代码列表
    fake = FakeResult({"command": "sector-fund-flow-history"})
    with mock.patch.object(
        cli_module.api,
        "get_sector_fund_flow_history",
        return_value=fake,
    ) as patched:
        # When: 通过板块资金流历史命令提交列表
        result = runner.invoke(
            app,
            ["sector-fund-flow-history", "BK0447", "BK0912", "BK0447"],
        )

    # Then: API 仅收到首见顺序的唯一代码
    assert result.exit_code == 0, result.stderr or result.output
    patched.assert_called_once_with(["BK0447", "BK0912"], "", 5)
