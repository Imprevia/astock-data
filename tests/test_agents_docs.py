from __future__ import annotations

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
