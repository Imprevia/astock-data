from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKER = PROJECT_ROOT / "scripts" / "check_docs_contract.py"
CORE = PROJECT_ROOT / "scripts" / "docs_contract_core.py"
REQUIRED_DOCS = (
    "AGENTS.md",
    "README.md",
    "docs/repository-guide.md",
    "docs/architecture.md",
    "docs/runbooks.md",
    "docs/lessons-learned.md",
    "docs/status.md",
    "docs/exec-plans/active/_index.md",
)
PLAN_FIELDS = (
    "Stage",
    "Status",
    "Acceptance",
    "Completion Evidence",
    "Remaining Gaps",
    "Next Step",
)


def _run(repo: Path, command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _write(repo: Path, relative: str, content: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _valid_plan() -> str:
    return "\n".join(f"## {field}\n\nvalue" for field in PLAN_FIELDS)


def _seed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, ("git", "init", "--initial-branch=master"))
    _run(repo, ("git", "config", "user.email", "tests@example.invalid"))
    _run(repo, ("git", "config", "user.name", "Contract Tests"))
    for relative in REQUIRED_DOCS:
        content = _valid_plan() if relative.endswith("_index.md") else "# fact\n"
        _write(repo, relative, content)
    _write(repo, "docs/exec-plans/active/work.md", _valid_plan())
    _write(repo, "docs/exec-plans/completed/.gitkeep", "")
    _write(repo, "astock_data/module.py", "VALUE = 1\n")
    target = repo / "scripts" / CHECKER.name
    target.parent.mkdir(parents=True)
    shutil.copy2(CHECKER, target)
    shutil.copy2(CORE, target.parent / CORE.name)
    _run(repo, ("git", "add", "."))
    _run(repo, ("git", "commit", "-m", "baseline"))
    return repo


def _check(
    repo: Path,
    mode: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = (sys.executable, "scripts/check_docs_contract.py", "--mode", mode)
    if env is None:
        return _run(repo, command)
    return subprocess.run(
        command,
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, **env},
    )


def test_required_document_paths_exist() -> None:
    # Given: the repository root.
    # When: required machine-consumed paths are resolved.
    paths = tuple(PROJECT_ROOT / relative for relative in REQUIRED_DOCS)
    # Then: every required path is a file.
    assert all(path.is_file() for path in paths)


def test_fast_uses_only_staged_changes(tmp_path: Path) -> None:
    # Given: an unstaged code change.
    repo = _seed_repo(tmp_path)
    _write(repo, "astock_data/module.py", "VALUE = 2\n")
    # When: the fast contract runs.
    result = _check(repo, "fast")
    # Then: the unstaged change is outside the selected set.
    assert result.returncode == 0


def test_full_without_upstream_uses_working_tree(tmp_path: Path) -> None:
    # Given: an unstaged code change without an upstream branch.
    repo = _seed_repo(tmp_path)
    _write(repo, "astock_data/module.py", "VALUE = 2\n")
    # When: the full contract runs.
    result = _check(repo, "full")
    # Then: Gate 1 rejects the selected code-only change.
    assert result.returncode == 1


def test_staged_gate_one_requires_docs_for_code(tmp_path: Path) -> None:
    # Given: only a code file is staged and the commit message has no marker.
    repo = _seed_repo(tmp_path)
    _write(repo, "astock_data/module.py", "VALUE = 2\n")
    _write(repo, "message.txt", "fixture\n")
    _run(repo, ("git", "add", "astock_data/module.py"))
    # When: the commit-message stage runs.
    result = _run(
        repo,
        (
            sys.executable,
            "scripts/check_docs_contract.py",
            "--mode",
            "staged",
            "--message-file",
            "message.txt",
        ),
    )
    # Then: Gate 1 fails.
    assert result.returncode == 1


def test_active_plan_requires_all_fields(tmp_path: Path) -> None:
    # Given: an active plan missing one structural field.
    repo = _seed_repo(tmp_path)
    plan = repo / "docs" / "exec-plans" / "active" / "work.md"
    plan.write_text("\n".join(_valid_plan().splitlines()[:-3]), encoding="utf-8")
    # When: the full contract runs.
    result = _check(repo, "full")
    # Then: structural validation fails.
    assert result.returncode == 1


def test_plan_gate_accepts_environment_escape(tmp_path: Path) -> None:
    # Given: a non-small docs change without an active-plan change.
    repo = _seed_repo(tmp_path)
    _write(repo, "docs/status.md", "\n".join(str(index) for index in range(24)))
    _write(repo, "docs/runbooks.md", "# changed\n")
    _run(repo, ("git", "add", "docs/status.md", "docs/runbooks.md"))
    # When: the plan escape hatch is enabled.
    result = _check(repo, "fast", {"SKIP_PLAN_GATE": "1"})
    # Then: only the plan gate is bypassed.
    assert result.returncode == 0


def test_contract_accepts_global_environment_escape(tmp_path: Path) -> None:
    # Given: a required document is absent.
    repo = _seed_repo(tmp_path)
    (repo / "docs" / "architecture.md").unlink()
    # When: the global escape hatch is enabled.
    result = _check(repo, "full", {"SKIP_DOCS_CONTRACT": "1"})
    # Then: the entire contract is bypassed.
    assert result.returncode == 0


def test_staged_mode_reads_explicit_commit_message_file(tmp_path: Path) -> None:
    # Given: a non-small docs change and an explicit commit message file.
    repo = _seed_repo(tmp_path)
    _write(repo, "docs/status.md", "\n".join(str(index) for index in range(24)))
    _write(repo, "docs/runbooks.md", "# changed\n")
    _write(repo, "message.txt", "[skip-plan] fixture\n")
    _run(repo, ("git", "add", "docs/status.md", "docs/runbooks.md"))
    # When: the staged gate receives that file explicitly.
    result = _run(
        repo,
        (
            sys.executable,
            "scripts/check_docs_contract.py",
            "--mode",
            "staged",
            "--message-file",
            "message.txt",
        ),
    )
    # Then: the plan marker bypasses the plan gate.
    assert result.returncode == 0
