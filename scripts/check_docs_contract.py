from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Sequence

if __package__:
    from . import docs_contract_core as core
else:
    import docs_contract_core as core

Mode = Literal["fast", "staged", "full", "push"]

REQUIRED_PATHS: Final = (
    "AGENTS.md",
    "README.md",
    "docs/repository-guide.md",
    "docs/architecture.md",
    "docs/runbooks.md",
    "docs/lessons-learned.md",
    "docs/status.md",
    "docs/exec-plans/active/_index.md",
    "docs/exec-plans/completed/.gitkeep",
)
PLAN_FIELDS: Final = (
    "Stage",
    "Status",
    "Acceptance",
    "Completion Evidence",
    "Remaining Gaps",
    "Next Step",
)
CODE_SUFFIXES: Final = frozenset({".py", ".pyi", ".toml"})
LINK_PATTERN: Final = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
DOCS_MARKER_PATTERN: Final = re.compile(
    r"\[(?:docs-only|no-docs)\]\s+\S+",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Invocation:
    mode: Mode
    message_file: Path | None = None
    local_oid: str | None = None
    remote_oid: str | None = None
    remote_name: str | None = None
    remote_ref: str | None = None


class CliUsageError(Exception):
    """Raised when command-line arguments do not match the contract."""


def _required_path_errors(repo: Path) -> list[str]:
    return [
        f"[required-docs] missing path: {relative}; create or restore it."
        for relative in REQUIRED_PATHS
        if not (repo / relative).is_file()
    ]


def _plan_errors(repo: Path) -> list[str]:
    active = repo / "docs" / "exec-plans" / "active"
    plans = tuple(sorted(active.glob("*.md"))) if active.is_dir() else ()
    errors: list[str] = []
    if not plans:
        return ["[plan-fields] no active Markdown plan; create docs/exec-plans/active/<name>.md."]
    for plan in plans:
        lines = plan.read_text(encoding="utf-8").splitlines()
        indices = {
            line.removeprefix("## ").strip(): index
            for index, line in enumerate(lines)
            if line.startswith("## ")
        }
        relative = plan.relative_to(repo).as_posix()
        for field in PLAN_FIELDS:
            start = indices.get(field)
            if start is None:
                errors.append(f"[plan-fields] {relative} missing heading: ## {field}.")
                continue
            end = next(
                (index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")),
                len(lines),
            )
            if not any(line.strip() for line in lines[start + 1 : end]):
                errors.append(f"[plan-fields] {relative} has empty field: ## {field}.")
    return errors


def _link_errors(repo: Path) -> list[str]:
    docs = repo / "docs"
    errors: list[str] = []
    if not docs.is_dir():
        return errors
    for markdown in docs.rglob("*.md"):
        content = markdown.read_text(encoding="utf-8")
        for raw_target in LINK_PATTERN.findall(content):
            target = raw_target.strip().strip("<>").split("#", maxsplit=1)[0]
            external = not target or "://" in target or target.startswith("mailto:")
            if not external and not (markdown.parent / target).resolve().exists():
                relative = markdown.relative_to(repo).as_posix()
                errors.append(f"[doc-links] {relative} has missing relative target: {target}.")
    return errors


def _gate_errors(changes: core.ChangeSet, message: str) -> list[str]:
    paths = changes.paths
    docs_changed = any(
        path.startswith("docs/") or path == "README.md" or Path(path).name == "AGENTS.md"
        for path in paths
    )
    code_changed = any(Path(path).suffix in CODE_SUFFIXES for path in paths)
    errors: list[str] = []
    if code_changed and not docs_changed and DOCS_MARKER_PATTERN.search(message) is None:
        errors.append(
            "[gate-1] code changed without docs/README/AGENTS; update the matching fact source "
            "or use [no-docs] <reason>."
        )

    small_change = len(paths) <= 1 and changes.changed_lines < core.NON_SMALL_LINES
    plan_changed = any(
        path.startswith("docs/exec-plans/active/") and path.endswith(".md") for path in paths
    )
    plan_escape = os.environ.get("SKIP_PLAN_GATE") == "1" or "[skip-plan]" in message.lower()
    if paths and not small_change and not plan_changed and not plan_escape:
        errors.append(
            "[gate-2/3] non-small change lacks an active plan update; update "
            "docs/exec-plans/active/*.md or set SKIP_PLAN_GATE=1 with a recorded reason."
        )
    return errors


def _parse_invocation(arguments: Sequence[str]) -> Invocation:
    values = tuple(arguments)
    if values == ("--mode", "fast"):
        return Invocation(mode="fast")
    if values == ("--mode", "full"):
        return Invocation(mode="full")
    if len(values) == 4 and values[:3] == ("--mode", "staged", "--message-file"):
        return Invocation(mode="staged", message_file=Path(values[3]))
    push_keys = (
        "--mode",
        "push",
        "--local-oid",
        "--remote-oid",
        "--remote-name",
        "--remote-ref",
    )
    if len(values) == 10 and values[0:2] == push_keys[0:2] and values[2::2] == push_keys[2:]:
        return Invocation(
            mode="push",
            local_oid=values[3],
            remote_oid=values[5],
            remote_name=values[7],
            remote_ref=values[9],
        )
    raise CliUsageError


def _selection(repo: Path, invocation: Invocation) -> core.Selection | None:
    if invocation.mode == "fast":
        return None
    if invocation.mode == "staged" and invocation.message_file is not None:
        message_path = invocation.message_file
        if not message_path.is_absolute():
            message_path = repo / message_path
        if not message_path.is_file():
            raise CliUsageError
        return core.staged_selection(repo, message_path.read_text(encoding="utf-8"))
    if invocation.mode == "full":
        return core.full_selection(repo)
    if (
        invocation.mode == "push"
        and invocation.local_oid is not None
        and invocation.remote_oid is not None
        and invocation.remote_name is not None
        and invocation.remote_ref is not None
    ):
        return core.push_selection(
            repo,
            core.PushRange(
                local_oid=invocation.local_oid,
                remote_oid=invocation.remote_oid,
                remote_name=invocation.remote_name,
                remote_ref=invocation.remote_ref,
            ),
        )
    raise CliUsageError


def main() -> int:
    if os.environ.get("SKIP_DOCS_CONTRACT") == "1":
        print("docs-contract: skipped by SKIP_DOCS_CONTRACT=1")
        return 0
    try:
        invocation = _parse_invocation(sys.argv[1:])
        repo = Path.cwd()
        selection = _selection(repo, invocation)
    except CliUsageError:
        print(
            "usage: check_docs_contract.py --mode {fast|full} | "
            "--mode staged --message-file PATH | --mode push --local-oid OID "
            "--remote-oid OID --remote-name NAME --remote-ref REF",
            file=sys.stderr,
        )
        return 2

    errors = _required_path_errors(repo) + _plan_errors(repo) + _link_errors(repo)
    if selection is not None:
        errors.extend(f"[{issue.category}] {issue.message}" for issue in selection.issues)
        for gate in selection.gates:
            gate_errors = _gate_errors(gate.changes, gate.message)
            commit_suffix = "" if gate.commit_oid is None else f" commit={gate.commit_oid}"
            errors.extend(f"{error}{commit_suffix}" for error in gate_errors)
    if errors:
        print("docs-contract: failed", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    changed_paths = 0 if selection is None else len(selection.changes.paths)
    print(f"docs-contract: passed ({invocation.mode}, {changed_paths} changed paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
