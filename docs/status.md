# Repository Status

## Current State

- Runtime: Python `>=3.10`; package boundary remains a pure data layer.
- Public surface: 25 Python API functions, 25 CLI commands, and 25 MCP stdio tools.
- Consumer boundary: `daily-review` calls `python -m astock_data.cli` and consumes JSON.
- Enforcement: stdlib-only docs-contract core/checker, lifecycle contract tests, three thin hooks, and the idempotent installer are implemented.
- Hook connection: repository-local `core.hooksPath` is `.githooks`.
- CI: none configured.
- Sector fund flow: push2his remains the daily source; the current-date five-day f164 aggregate fallback, exact-date cache, separated result field, and THS semantic guard are implemented.

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
- Sector f164 TDD red phase: client tests failed 6 cases on the missing endpoint/function; service/model tests then failed on missing guard, aggregate field, exact-date cache, and warning behavior.
- Sector f164 focused green evidence: client/model tests passed 8 cases; service guards passed 4; aggregate separation passed 2; THS semantics passed 3; exact-date cache passed 4; warning behavior passed 4; API/CLI/MCP serialization passed 5.
- Sector f164 regression evidence: 163 targeted tests passed in 5.64 seconds; the final full suite passed 510 tests with 7 skips in 124.47 seconds.
- Sector f164 docs evidence: `python scripts/check_docs_contract.py --mode full` passed with 0 committed paths selected while required docs, plan fields, and links were checked.
- Sector f164 live evidence: the normal CLI returned five push2his rows and an 8,761,409,792 yuan sum; a controlled opt-in fallback call returned that value from real f164 with empty daily history, while the previous-date guard skipped f164 and returned no aggregate.
- Sector f164 Oracle remediation: two failing regressions proved invalid push2his rows suppressed f164 and an early `DataSourceError` skipped a later sector; both turned green while the historical fail-fast control remained green.
- Oracle remediation verification: 14 focused service/cache tests and 167 broader targeted tests passed; final full regression passed 513 tests with 7 skips in 117.59 seconds.
- Oracle remediation live/strict evidence: 2026-07-30 real f164 returned 28,564,623,360 yuan with empty history, 2026-07-29 skipped f164, and strict OpenSpec validation passed.
- Final invalid-row remediation: the regression first failed with three invalid rows in public history, then all 3 Oracle tests and 24 focused f164 tests passed after invalid-only rows continued to THS/cache instead of being returned.
- Final invalid-row verification: 167 broader targeted tests passed, the full suite passed 513 tests with 7 skips in 116.45 seconds, and docs-contract full mode passed.
- Final invalid-row live evidence: invalid-only input produced empty history plus a real 26,221,969,152 yuan f164 aggregate; the prior-date guard produced no aggregate.

## Remaining Gaps

- No CI exists; enforcement depends on installing and retaining the repository-local hooks.
- `basedpyright` is unavailable and installation permission was previously declined; all six final LSP calls reported this tool gap, so no clean-diagnostics claim is made.
- Changes remain uncommitted by request; the pre-existing untracked `astock_data.zip` was not modified.
- `basedpyright` remains unavailable by prior decision. The no-excuse audit found no newly introduced violation after cache-write warning cleanup; inherited findings and all changed-file LOC values are recorded in the active sector f164 plan.
- The f164 plan and active index now agree that implementation is complete and awaiting archive.
