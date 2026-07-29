from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(repo: Path, command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _run_input(
    repo: Path,
    command: tuple[str, ...],
    stdin: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=stdin,
    )


def test_hooks_route_to_expected_contract_modes() -> None:
    # Given: the three repository hook entrypoints.
    pre_commit = PROJECT_ROOT / ".githooks" / "pre-commit"
    commit_msg = PROJECT_ROOT / ".githooks" / "commit-msg"
    pre_push = PROJECT_ROOT / ".githooks" / "pre-push"
    # When: their machine-consumed command tokens are read.
    commit_tokens = pre_commit.read_text(encoding="utf-8").split()
    message_tokens = commit_msg.read_text(encoding="utf-8").split()
    push_tokens = pre_push.read_text(encoding="utf-8").split()
    # Then: each hook routes to its required mode.
    assert commit_tokens[-2:] == ["--mode", "fast"]
    assert "staged" in message_tokens
    assert "push" in push_tokens


def test_installer_sets_repository_hooks_path(tmp_path: Path) -> None:
    # Given: a Git repository containing the installer and hooks.
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, ("git", "init", "--initial-branch=master"))
    scripts = repo / "scripts"
    scripts.mkdir()
    shutil.copy2(PROJECT_ROOT / "scripts" / "install_hooks.py", scripts)
    shutil.copytree(PROJECT_ROOT / ".githooks", repo / ".githooks")
    # When: the installer runs twice.
    first = _run(repo, (sys.executable, "scripts/install_hooks.py"))
    second = _run(repo, (sys.executable, "scripts/install_hooks.py"))
    configured = _run(repo, ("git", "config", "--get", "core.hooksPath"))
    # Then: both runs succeed and the local Git path is stable.
    assert (first.returncode, second.returncode) == (0, 0)
    assert configured.stdout.strip() == ".githooks"


def test_pre_commit_runs_message_independent_checks(tmp_path: Path) -> None:
    # Given: a staged code-only change in a seeded repository.
    from tests.test_docs_contract import _seed_repo, _write

    repo = _seed_repo(tmp_path)
    shutil.copytree(PROJECT_ROOT / ".githooks", repo / ".githooks")
    _write(repo, "astock_data/module.py", "VALUE = 2\n")
    _run(repo, ("git", "add", "astock_data/module.py"))
    # When: pre-commit runs before a commit message exists.
    result = _run(repo, ("sh", ".githooks/pre-commit"))
    # Then: only static and structural checks run.
    assert result.returncode == 0


def test_commit_msg_uses_the_message_argument(tmp_path: Path) -> None:
    # Given: a non-small staged docs change and a marked message file.
    from tests.test_docs_contract import _seed_repo, _write

    repo = _seed_repo(tmp_path)
    shutil.copytree(PROJECT_ROOT / ".githooks", repo / ".githooks")
    _write(repo, "docs/status.md", "\n".join(str(index) for index in range(24)))
    _write(repo, "docs/runbooks.md", "# changed\n")
    _write(repo, "message.txt", "[skip-plan] fixture\n")
    _run(repo, ("git", "add", "docs/status.md", "docs/runbooks.md"))
    # When: commit-msg receives the real message path.
    result = _run(repo, ("sh", ".githooks/commit-msg", "message.txt"))
    # Then: the staged gate consumes that marker.
    assert result.returncode == 0


def test_pre_push_checks_every_stdin_ref(tmp_path: Path) -> None:
    # Given: current master is clean and a non-current feature has code only.
    from tests.test_docs_contract import _run as run_git
    from tests.test_docs_contract import _seed_repo, _write

    repo = _seed_repo(tmp_path)
    shutil.copytree(PROJECT_ROOT / ".githooks", repo / ".githooks")
    baseline = run_git(repo, ("git", "rev-parse", "HEAD")).stdout.strip()
    run_git(repo, ("git", "switch", "-c", "feature"))
    _write(repo, "astock_data/module.py", "VALUE = 2\n")
    run_git(repo, ("git", "add", "astock_data/module.py"))
    run_git(repo, ("git", "commit", "-m", "code-only"))
    feature = run_git(repo, ("git", "rev-parse", "HEAD")).stdout.strip()
    run_git(repo, ("git", "switch", "master"))
    stdin = (
        f"refs/heads/old {'0' * 40} refs/heads/old {baseline}\n"
        f"refs/heads/master {baseline} refs/heads/master {baseline}\n"
        f"refs/heads/feature {feature} refs/heads/feature {baseline}\n"
    )
    # When: pre-push receives both ref updates.
    result = _run_input(repo, ("sh", ".githooks/pre-push", "origin", "unused"), stdin)
    # Then: failure from the non-current ref is not skipped.
    assert result.returncode == 1
