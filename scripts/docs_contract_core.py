from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Sequence

NON_SMALL_LINES: Final = 20
STREAM_CHUNK_BYTES: Final = 64 * 1024
LARGE_UNTRACKED_BYTES: Final = 20 * 1024
ZERO_OID: Final = "0" * 40


@dataclass(frozen=True, slots=True)
class ChangeSet:
    paths: tuple[str, ...]
    changed_lines: int


@dataclass(frozen=True, slots=True)
class GateUnit:
    changes: ChangeSet
    message: str
    commit_oid: str | None = None


@dataclass(frozen=True, slots=True)
class SelectionIssue:
    category: str
    message: str


@dataclass(frozen=True, slots=True)
class Selection:
    changes: ChangeSet
    gates: tuple[GateUnit, ...]
    issues: tuple[SelectionIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class PushRange:
    local_oid: str
    remote_oid: str
    remote_name: str
    remote_ref: str


def _git(
    repo: Path,
    arguments: Sequence[str],
    required: bool,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *arguments),
        cwd=repo,
        check=required,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _paths(output: str) -> tuple[str, ...]:
    return tuple(sorted({line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()}))


def _numstat_lines(output: str) -> int:
    total = 0
    for row in output.splitlines():
        columns = row.split("\t", maxsplit=2)
        if len(columns) >= 2:
            additions = int(columns[0]) if columns[0].isdigit() else 0
            deletions = int(columns[1]) if columns[1].isdigit() else 0
            total += additions + deletions
    return total


def _diff_changes(repo: Path, arguments: tuple[str, ...]) -> ChangeSet:
    names = _git(repo, (*arguments, "--name-only", "--diff-filter=ACMRDTUXB"), True)
    stats = _git(repo, (*arguments, "--numstat"), True)
    return ChangeSet(paths=_paths(names.stdout), changed_lines=_numstat_lines(stats.stdout))


def _merge(changes: Sequence[ChangeSet]) -> ChangeSet:
    paths = set[str]()
    changed_lines = 0
    for change in changes:
        paths.update(change.paths)
        changed_lines += change.changed_lines
    return ChangeSet(paths=tuple(sorted(paths)), changed_lines=changed_lines)


def count_untracked_lines(path: Path) -> int:
    lines = 1
    bytes_seen = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(STREAM_CHUNK_BYTES):
                bytes_seen += len(chunk)
                lines += chunk.count(b"\n")
                if lines >= NON_SMALL_LINES or bytes_seen >= LARGE_UNTRACKED_BYTES:
                    return NON_SMALL_LINES
    except OSError:
        return NON_SMALL_LINES
    return lines


def staged_changes(repo: Path) -> ChangeSet:
    return _diff_changes(repo, ("diff", "--cached"))


def staged_selection(repo: Path, message: str) -> Selection:
    changes = staged_changes(repo)
    return Selection(changes=changes, gates=(GateUnit(changes=changes, message=message),))


def full_selection(repo: Path) -> Selection:
    upstream = _git(
        repo,
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"),
        False,
    )
    if upstream.returncode == 0 and upstream.stdout.strip():
        name = upstream.stdout.strip()
        commits = _paths(_git(repo, ("rev-list", "HEAD", f"^{name}"), True).stdout)
        return _commit_selection(repo, commits)

    tracked = _diff_changes(repo, ("diff", "HEAD"))
    untracked = _paths(_git(repo, ("ls-files", "--others", "--exclude-standard"), True).stdout)
    untracked_lines = sum(
        count_untracked_lines(repo / relative) for relative in untracked if (repo / relative).is_file()
    )
    changes = ChangeSet(
        paths=tuple(sorted(set(tracked.paths).union(untracked))),
        changed_lines=tracked.changed_lines + untracked_lines,
    )
    return Selection(changes=changes, gates=(GateUnit(changes=changes, message=""),))


def _commit_selection(repo: Path, commits: tuple[str, ...]) -> Selection:
    gates: list[GateUnit] = []
    for commit in commits:
        changes = _diff_changes(
            repo,
            ("diff-tree", "--root", "--no-commit-id", "-r", commit),
        )
        message = _git(repo, ("show", "-s", "--format=%B", commit), True).stdout
        gates.append(GateUnit(changes=changes, message=message, commit_oid=commit))
    return Selection(changes=_merge(tuple(gate.changes for gate in gates)), gates=tuple(gates))


def push_selection(repo: Path, push: PushRange) -> Selection:
    if push.local_oid == ZERO_OID:
        return Selection(changes=ChangeSet(paths=(), changed_lines=0), gates=())
    if push.remote_oid != ZERO_OID:
        available = _git(repo, ("cat-file", "-e", f"{push.remote_oid}^{{commit}}"), False)
        if available.returncode != 0:
            issue = SelectionIssue(
                category="push-missing-remote-object",
                message=(
                    f"remote object {push.remote_oid} for {push.remote_ref} is unavailable locally; "
                    f"run git fetch {push.remote_name} {push.remote_ref}."
                ),
            )
            return Selection(changes=ChangeSet(paths=(), changed_lines=0), gates=(), issues=(issue,))
        commits = _paths(
            _git(repo, ("rev-list", push.local_oid, f"^{push.remote_oid}"), True).stdout
        )
        return _commit_selection(repo, commits)
    commits = _paths(
        _git(
            repo,
            ("rev-list", push.local_oid, "--not", f"--remotes={push.remote_name}"),
            True,
        ).stdout
    )
    return _commit_selection(repo, commits)
