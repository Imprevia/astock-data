from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import docs_contract_core
from tests.test_docs_contract import PLAN_FIELDS, _check, _run, _seed_repo, _valid_plan, _write

pytestmark = pytest.mark.unit

ZERO_OID = "0" * 40


def _push_result(
    repo: Path,
    local_oid: str,
    remote_oid: str,
) -> subprocess.CompletedProcess[str]:
    result = _run(
        repo,
        (
            "python",
            "scripts/check_docs_contract.py",
            "--mode",
            "push",
            "--local-oid",
            local_oid,
            "--remote-oid",
            remote_oid,
            "--remote-name",
            "origin",
            "--remote-ref",
            "refs/heads/feature",
        ),
    )
    return result


def _push_check(repo: Path, local_oid: str, remote_oid: str) -> int:
    return _push_result(repo, local_oid, remote_oid).returncode


def _feature_commit(repo: Path) -> tuple[str, str]:
    baseline = _run(repo, ("git", "rev-parse", "HEAD")).stdout.strip()
    _run(repo, ("git", "update-ref", "refs/remotes/origin/master", baseline))
    _run(repo, ("git", "switch", "-c", "feature"))
    _write(repo, "astock_data/module.py", "VALUE = 2\n")
    _run(repo, ("git", "add", "astock_data/module.py"))
    _run(repo, ("git", "commit", "-m", "code-only"))
    feature = _run(repo, ("git", "rev-parse", "HEAD")).stdout.strip()
    _run(repo, ("git", "switch", "master"))
    return baseline, feature


def _marked_then_unmarked_commits(repo: Path) -> tuple[str, str]:
    baseline = _run(repo, ("git", "rev-parse", "HEAD")).stdout.strip()
    _run(repo, ("git", "update-ref", "refs/remotes/origin/master", baseline))
    _run(repo, ("git", "switch", "-c", "feature"))
    first = "\n".join(f"FIRST_{index} = {index}" for index in range(24))
    _write(repo, "astock_data/module.py", f"{first}\n")
    _run(repo, ("git", "add", "astock_data/module.py"))
    _run(repo, ("git", "commit", "-m", "[no-docs] fixture [skip-plan]"))
    second = "\n".join(f"SECOND_{index} = {index}" for index in range(24))
    _write(repo, "astock_data/module.py", f"{second}\n")
    _run(repo, ("git", "add", "astock_data/module.py"))
    _run(repo, ("git", "commit", "-m", "unmarked"))
    tip = _run(repo, ("git", "rev-parse", "HEAD")).stdout.strip()
    return baseline, tip


def test_active_plan_rejects_empty_field_body(tmp_path: Path) -> None:
    # Given: every heading exists but Status has no body.
    repo = _seed_repo(tmp_path)
    plan = repo / "docs" / "exec-plans" / "active" / "work.md"
    content = _valid_plan().replace("## Status\n\nvalue", "## Status\n")
    plan.write_text(content, encoding="utf-8")
    # When: structural validation runs.
    result = _check(repo, "full")
    # Then: the empty machine field is rejected.
    assert result.returncode == 1


def test_untracked_counter_streams_without_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a large untracked file and read_bytes disabled.
    path = tmp_path / "large.bin"
    path.write_bytes(b"x" * (1024 * 1024))

    def reject_read_bytes(_path: Path) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", reject_read_bytes)
    # When: the conservative line counter reads the file.
    count = docs_contract_core.count_untracked_lines(path)
    # Then: size alone reaches the non-small threshold.
    assert count >= 20


def test_untracked_counter_is_conservative_on_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an untracked path that cannot be opened.
    path = tmp_path / "blocked.bin"
    path.write_bytes(b"x")

    def reject_open(_path: Path, _mode: str) -> None:
        raise OSError

    monkeypatch.setattr(Path, "open", reject_open)
    # When: the conservative line counter handles the boundary failure.
    count = docs_contract_core.count_untracked_lines(path)
    # Then: the plan-gate threshold is returned.
    assert count >= 20


def test_push_checks_non_current_ref_update(tmp_path: Path) -> None:
    # Given: a code-only feature commit while master is checked out.
    repo = _seed_repo(tmp_path)
    baseline, feature = _feature_commit(repo)
    # When: the explicit feature update range is checked.
    returncode = _push_check(repo, feature, baseline)
    # Then: Gate 1 sees the non-current ref change.
    assert returncode == 1


def test_new_branch_checks_only_commits_missing_from_remote(tmp_path: Path) -> None:
    # Given: remote master owns the baseline and feature adds code only.
    repo = _seed_repo(tmp_path)
    _, feature = _feature_commit(repo)
    # When: the feature is checked as a new remote branch.
    returncode = _push_check(repo, feature, ZERO_OID)
    # Then: baseline docs do not hide the new code-only commit.
    assert returncode == 1


def test_push_missing_remote_object_returns_actionable_failure(tmp_path: Path) -> None:
    # Given: the pushed local commit exists but its advertised remote object does not.
    repo = _seed_repo(tmp_path)
    _, feature = _feature_commit(repo)
    missing_oid = "f" * 40
    # When: the explicit push range is checked.
    result = _push_result(repo, feature, missing_oid)
    # Then: the failure is stable, actionable, and contains no Python traceback.
    assert result.returncode == 1
    assert "[push-missing-remote-object]" in result.stderr
    assert "origin" in result.stderr
    assert "refs/heads/feature" in result.stderr
    assert "Traceback" not in result.stderr


def test_push_markers_do_not_escape_their_commit(tmp_path: Path) -> None:
    # Given: a marked violating commit followed by an unmarked violating commit.
    repo = _seed_repo(tmp_path)
    baseline, tip = _marked_then_unmarked_commits(repo)
    # When: the complete push range is checked.
    returncode = _push_check(repo, tip, baseline)
    # Then: markers from the first commit do not exempt the second.
    assert returncode == 1


def test_full_markers_do_not_escape_their_commit(tmp_path: Path) -> None:
    # Given: the same two commits are ahead of the configured upstream.
    repo = _seed_repo(tmp_path)
    _, _tip = _marked_then_unmarked_commits(repo)
    _run(repo, ("git", "remote", "add", "origin", "."))
    _run(repo, ("git", "config", "branch.feature.remote", "origin"))
    _run(repo, ("git", "config", "branch.feature.merge", "refs/heads/master"))
    # When: full mode selects and checks the committed range.
    selection = docs_contract_core.full_selection(repo)
    result = _check(repo, "full")
    # Then: commit gate units remain separate and markers cannot leak.
    assert len(selection.gates) == 2
    assert result.returncode == 1


def test_plan_field_fixture_covers_all_required_fields() -> None:
    # Given: the structural plan fixture.
    # When: level-two headings are parsed.
    headings = tuple(
        line.removeprefix("## ") for line in _valid_plan().splitlines() if line.startswith("## ")
    )
    # Then: all machine-consumed fields are represented.
    assert headings == PLAN_FIELDS
