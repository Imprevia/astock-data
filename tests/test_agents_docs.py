from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMPORTANT_DIRS = [
    PROJECT_ROOT,
    PROJECT_ROOT / "astock_data",
    PROJECT_ROOT / "astock_data" / "clients",
    PROJECT_ROOT / "astock_data" / "services",
    PROJECT_ROOT / "astock_data" / "models",
    PROJECT_ROOT / "astock_data" / "cache",
    PROJECT_ROOT / "astock_data" / "formatters",
    PROJECT_ROOT / "astock_data" / "mcp",
    PROJECT_ROOT / "examples",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / "tests" / "fixtures",
    PROJECT_ROOT / "tests" / "live",
]
FORBIDDEN_PHRASES = [
    "langchain",
    "langgraph",
    "openai",
    "anthropic",
    "streamlit",
    "fastapi",
    "skip tests",
    "绕过测试",
]


def _agents_path(directory: Path) -> Path:
    return directory / "AGENTS.md"


def _markdown_table_rows(content: str, header: str) -> list[list[str]]:
    lines = content.splitlines()
    header_index = next(index for index, line in enumerate(lines) if line.strip() == header)
    rows: list[list[str]] = []
    for line in lines[header_index + 2 :]:
        if not line.strip().startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def _readme() -> str:
    return (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")


def test_every_important_directory_has_agents_md():
    missing = [str(directory) for directory in IMPORTANT_DIRS if not _agents_path(directory).is_file()]
    assert not missing, f"missing AGENTS.md in: {missing}"


def test_agents_md_avoid_forbidden_phrases():
    violations: list[str] = []
    for directory in IMPORTANT_DIRS:
        content = _agents_path(directory).read_text(encoding="utf-8")
        lowered = content.lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase in lowered:
                violations.append(f"{_agents_path(directory)} contains {phrase!r}")
    assert not violations, "\n".join(violations)


def test_readme_cli_table_has_25_unique_commands():
    rows = _markdown_table_rows(_readme(), "| 子命令 | 对应 Python API |")
    commands = [re.sub(r"`", "", row[0]) for row in rows]

    assert len(commands) == 25
    assert len(set(commands)) == 25


def test_readme_data_source_contracts_are_structured():
    content = _readme()
    source_rows = _markdown_table_rows(content, "| 来源 | 协议 | 主要数据 |")
    source_by_name = {row[0]: row[2] for row in source_rows}
    fallback_rows = _markdown_table_rows(content, "| 接口 | 主源 | 降级1 | 降级2 | 降级3 |")
    fallback_by_endpoint = {row[0]: row[1:] for row in fallback_rows}

    assert "ETF日K主源" not in source_by_name["腾讯财经"]
    assert fallback_by_endpoint["etf-daily"] == ["新浪K线", "东财push2his", "—", "—"]
    assert fallback_by_endpoint["sector-fund-flow-history"] == [
        "东财push2his逐日资金",
        "东财f164当前五日累计",
        "同花顺行业日K",
        "SQLite缓存",
    ]
    assert fallback_by_endpoint["market-breadth 指数"] == [
        "腾讯",
        "新浪",
        "东财push2",
        "—",
    ]
    assert fallback_by_endpoint["market-breadth 涨跌停"] == [
        "新浪分页",
        "东财push2 clist",
        "—",
        "—",
    ]
