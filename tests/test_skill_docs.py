from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = PROJECT_ROOT / "skills" / "astock-data" / "SKILL.md"
CLI_PATH = PROJECT_ROOT / "astock_data" / "cli.py"

RECIPE_COMMANDS = {
    "resolve",
    "kline",
    "fund-flow",
    "concepts",
    "dragon-tiger",
    "news",
    "balance-sheet",
}


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _cli_command_names() -> set[str]:
    tree = ast.parse(CLI_PATH.read_text(encoding="utf-8"))
    command_names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "command"
            for decorator in node.decorator_list
        ):
            command_names.add(node.name.replace("_", "-"))
    return command_names


def test_skill_doc_required_sections_present():
    content = _skill_text().lower()
    required_sections = [
        "triggers and keywords",
        "prerequisites",
        "mcp stdio",
        "fallback path, cli",
        "recipes",
        "error handling",
        "evidence and output guidance",
    ]
    missing = [section for section in required_sections if section not in content]
    assert not missing, f"missing skill sections: {missing}"


def test_skill_doc_has_at_least_six_recipes():
    recipe_headings = re.findall(r"^###\s+", _skill_text(), flags=re.MULTILINE)
    assert len(recipe_headings) >= 6


def test_skill_doc_is_data_query_only_no_advice_instructions():
    content = _skill_text().lower()
    forbidden_patterns = [
        r"recommend\s+(buy|sell|hold)",
        r"(buy|sell|hold)\s+recommendation",
        r"generate\s+(buy|sell|hold)\s+advice",
        r"投资建议",
        r"买入建议",
        r"卖出建议",
        r"持有建议",
    ]
    violations = [pattern for pattern in forbidden_patterns if re.search(pattern, content)]
    assert not violations, f"skill must stay data-query only: {violations}"
    assert "data-query only" in content


def test_skill_doc_references_real_cli_recipe_commands():
    assert RECIPE_COMMANDS <= _cli_command_names()

    content = _skill_text()
    missing = [
        command
        for command in RECIPE_COMMANDS
        if f"python -m astock_data.cli {command}" not in content
    ]
    assert not missing, f"recipe commands not documented: {missing}"


def test_skill_doc_lists_real_mcp_tools():
    content = _skill_text()
    expected_tools = {
        "resolve_ticker",
        "get_stock_data",
        "get_indicators",
        "get_market_breadth",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
        "get_news",
        "get_global_news",
        "get_insider_transactions",
        "get_profit_forecast",
        "get_hot_stocks",
        "get_northbound_flow",
        "get_concept_blocks",
        "get_fund_flow",
        "get_dragon_tiger_board",
        "get_lockup_expiry",
        "get_industry_comparison",
    }
    missing = [tool for tool in sorted(expected_tools) if f"`{tool}`" not in content]
    assert not missing, f"missing MCP tool names: {missing}"
