# Repository Status

## Current State

- Runtime: Python `>=3.10`; package boundary remains a pure data layer.
- Public surface: 26 Python API functions, 26 CLI commands, and 26 MCP stdio tools.
- Consumer boundary: `daily-review` calls `python -m astock_data.cli` and consumes JSON.
- Enforcement: stdlib-only docs-contract core/checker, lifecycle contract tests, three thin hooks, and the idempotent installer are implemented.
- Hook connection: repository-local `core.hooksPath` is `.githooks`.
- CI: none configured.
- Sector fund flow: push2his remains the daily source; independently date-verified latest-session f164 aggregates, aggregate-only retrieval, exact-date cache, cache-before-THS ordering, and the THS semantic guard are implemented.
- Sector ETF coverage: ten representative software/computer/media/communication/robot/electronics/gold/gaming/chemical/agriculture ETFs are added to the allowlist; the 2026-07-31 downstream mapping covers 82 of 89 sector rows.
- ETF expansion verification: 91 focused API/CLI/MCP/docs tests passed; the final full suite passed 525 tests with 7 skips in 128.60 seconds; the full docs contract passed.
- Global news: dated requests paginate the Eastmoney 7x24 archive with the vendor cursor and reject out-of-window live rows and legacy polluted cache entries.
- Order book: Tencent five-level snapshots expose vendor time, visible bid/ask depth, spread and imbalance; bounded sampling emits only unattributed same-price depth changes and entered/left-view events.

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
- Historical review retrieval focused suite passed 67 news/client tests; full regression passed 518 tests with 7 skips after redirecting pytest's blocked system temp directory to a writable workspace-owned path.
- Historical news live smoke returned 15 correctly dated 2026-07-31 items through Eastmoney cursor pagination; downstream sector and money-flow smokes restored outflow rankings and five-day ratios.
- Latest-session sector recovery live evidence: Sina verified `2026-07-31`, f164 returned 128 industry aggregates, and the enhanced review completed in about 61 seconds. Top30 retained eight detailed histories from live/cache and recovered eight additional five-day aggregates without inventing positive-day counts.
- Market amount live evidence: the date-verified Sina market snapshot summed 2.5591 trillion yuan across 5,527 positive-amount stock rows for 2026-07-31; the index-K-line series remains separately labeled as a trend proxy.
- Final retrieval regression: 524 tests passed with 7 skips in 134.08 seconds; `python scripts/check_docs_contract.py --mode full` passed.
- Order-book focused verification after review remediation: 146 data-layer tests passed in 18.43 seconds; 7 buyer-exhaustion integration tests passed in 0.007 seconds.
- Order-book revision 2 verification: 149 data-layer tests passed in 19.81 seconds; 9 buyer-exhaustion integration tests passed in 0.007 seconds after `position`, timeout isolation, inverse-time filtering, and malformed-payload regressions.
- Order-book revision 3 verification: the corrected 26-command README contract test passed, followed by 149 data-layer tests and 9 buyer-exhaustion integration tests.
- Order-book independent review passed revision 3 with no blocking findings.
- Order-book final regression passed 551 tests with 7 skips in 133.26 seconds; full docs contract and both repository diff checks passed.
- Order-book live evidence for 600809 returned five bids and five asks in lots at vendor time `20260804161500`; duplicate closing timestamps produced no changes and `exact_cancellation_available` remained false.
- Buyer-exhaustion resilience developer verification passed 161 focused data/API/CLI/MCP tests and 12 downstream analysis tests. `wildman-daily-review` quick validation passed after enabling Python UTF-8 mode; the first invocation was blocked only by the validator process using the Windows GBK default for a UTF-8 Skill file.

## Remaining Gaps

- No CI exists; enforcement depends on installing and retaining the repository-local hooks.
- `basedpyright` is unavailable and installation permission was previously declined; all six final LSP calls reported this tool gap, so no clean-diagnostics claim is made.
- Changes remain uncommitted by request; the pre-existing untracked `astock_data.zip` was not modified.
- `basedpyright` remains unavailable by prior decision. The no-excuse audit found no newly introduced violation after cache-write warning cleanup; inherited findings and all changed-file LOC values are recorded in the active sector f164 plan.
- The f164 plan and active index now agree that implementation is complete and awaiting archive.
- Fine-grained industries absent from the official f164 industry universe still depend on push2his or a prior valid cache; no parent-industry value is substituted.
- Order-book exact cancellations, hidden liquidity, order identity, and historical intraday depth before collection remain unavailable by design.
- Buyer-exhaustion resilience revision 4 passes 602 package tests with 7 skips, 16 downstream analysis tests, Skill validation, the full docs contract, strict OpenSpec validation, and live 600809/002230 smokes. Current-revision Developer ownership and independent no-blocker review remain pending because the host collaboration dispatch interface is not accepting another Agent call.
