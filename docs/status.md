# Repository Status

## Current State

- Runtime: Python `>=3.10`; package boundary remains a pure data layer.
- Public surface: 25 Python API functions, 25 CLI commands, and 25 MCP stdio tools.
- Consumer boundary: `daily-review` calls `python -m astock_data.cli` and consumes JSON.
- Enforcement: stdlib-only docs-contract core/checker, lifecycle contract tests, three thin hooks, and the idempotent installer are implemented.
- Hook connection: repository-local `core.hooksPath` is `.githooks`.
- CI: none configured.

## Evidence

- Existing repository survey: README, CHANGELOG, AGENTS, pyproject, and contract tests reviewed on 2026-07-29.
- Red phase: `python -m pytest tests/test_docs_contract.py tests/test_hooks_contract.py -q` failed 10 tests because required docs, scripts, and hooks were absent.
- Green phase: the same dedicated command passed 10 tests in 5.32 seconds.
- Regression suite: `python -m pytest -q` passed 477 tests with 7 skips in 117.74 seconds.
- Local gate: full mode passed required-path, plan-field, relative-link, and selected-change checks.
- Installation: the installer succeeded and Git reported `.githooks`.
- Size gate: every new Python file is below 250 pure LOC.
- Oracle remediation red phase: 9 dedicated tests failed on staged message timing, empty plan fields, streaming counts, explicit push ranges, and hook lifecycle.
- Oracle remediation focused green phase: 19 dedicated tests passed in 11.65 seconds before final regression verification.
- Final focused suite: 19 tests passed in 10.04 seconds.
- Final regression suite: 486 tests passed with 7 skips in 115.38 seconds.
- Hook smoke: fast pre-commit, staged commit-msg, and deletion-only pre-push invocations exited successfully; focused tests also exercised multi-ref, non-current ref, and new-branch ranges.
- Final local gate: full mode passed with 0 committed paths in the configured upstream range while structural contracts were still checked.
- Final installation: installer succeeded and Git returned `.githooks`.
- Final size gate: changed Python pure LOC values are 190, 116, 40, 146, 78, and 91.
- Oracle follow-up red phase: focused tests exposed unsupported explicit remote-ref input, missing remote-object recovery, and range-shared marker behavior; full selection lacked commit gate units.
- Oracle follow-up implementation: typed `GateUnit` and `SelectionIssue` preserve per-commit gates while range-level structural checks remain shared.
- Oracle follow-up red evidence: 4 focused failures exposed unsupported remote-ref input and missing push semantics; a dedicated full-selection test failed because commit gates were absent.
- Oracle follow-up final focused suite: 22 tests passed in 15.46 seconds.
- Oracle follow-up final regression suite: 489 tests passed with 7 skips in 118.71 seconds.
- Final local commands: fast and full contracts passed, hook installation succeeded, and Git returned `.githooks`.
- Final size values: 204, 142, 40, 146, 126, and 91 pure LOC.
- Forbidden-pattern scan returned no matches; the dedicated scanner replaced unavailable `rg`.

## Remaining Gaps

- No CI exists; enforcement depends on installing and retaining the repository-local hooks.
- `basedpyright` is unavailable and installation permission was previously declined; all six final LSP calls reported this tool gap, so no clean-diagnostics claim is made.
- Changes remain uncommitted by request; the pre-existing untracked `astock_data.zip` was not modified.
