# Add Sector Fund Flow F164 Fallback

## Stage

Complete

## Status

All 19 OpenSpec tasks, including the final invalid-row Oracle remediation, are implemented and verified. The plan is complete and awaiting archive.

## Acceptance

- `get_sector_fund_flow_history` keeps push2his as the authoritative daily fund-flow history source.
- A single Eastmoney `getbkzj` request with `key=f164` and `code=m:90+s:4` is used only for a five-day request targeting local today when at least one valid daily series is missing.
- `SectorFundFlowHistoryResult` exposes `five_day_main_net_inflow_by_code` without changing `history_by_code`; numeric zero is preserved and missing or invalid values remain missing.
- THS market bars never create daily main-net-inflow values or five-day aggregates.
- Successful f164 bulk data is cached by exact target date without cross-date fallback, and warnings remain concise and source-specific.
- Python API, CLI, MCP, documentation, targeted tests, the full suite, the docs contract, and an environment-permitted live smoke agree with the public contract.

## Completion Evidence

- OpenSpec apply instructions reported 19 ordered tasks and repository-local edit scope.
- Client red phase: 6 tests failed because the getbkzj URL and f164 bulk function did not exist; green phase passed all 6.
- Model red phase: 2 tests failed because the aggregate field was absent; green client/model verification passed 8 tests.
- Service red phase: the allowed guard path failed while the three forbidden paths already held; aggregate/cache/warning coverage then produced 6 focused failures for the missing implementation.
- Service green evidence: guards passed 4 tests, aggregate separation 2, THS semantics 3, exact-date cache 4, and warnings 4.
- Python API, CLI, and MCP serialization passed 5 focused tests through the shared Pydantic model without handler changes.
- README structured-contract red phase failed the old fallback assertion; the updated facts passed all 4 agent/docs structure tests.
- Targeted regression: `python -m pytest` across the f164 client/service/cache/contracts plus existing Eastmoney, signals, public API, CLI, and MCP suites passed 163 tests in 5.64 seconds.
- Initial full regression: `python -m pytest -q` passed 509 tests with 7 skips in 126.73 seconds.
- Full docs contract: `python scripts/check_docs_contract.py --mode full` passed all required paths, active-plan fields, and links; the configured range selected 0 committed paths.
- Live CLI smoke returned five real push2his daily rows for `BK1036` and a true summed aggregate of 8,761,409,792 yuan without loading f164.
- Controlled opt-in live fallback smoke forced only daily/THS absence, then received the same 8,761,409,792 yuan through the real f164 endpoint with empty history and an f164-only warning; the previous-date call did not invoke f164 and returned no aggregate. A first attempt passed business assertions but hit a Windows temporary SQLite cleanup error; explicit garbage collection made the repeated smoke exit successfully.
- Cache-write warning red/green: the focused test first failed because SQLite write failure was silent, then passed after the service retained the result and emitted a concise warning.
- Final full regression after that cleanup passed 510 tests with 7 skips in 124.47 seconds.
- LSP diagnostics were requested for every changed Python file, but `basedpyright` is not installed and installation was previously declined; no clean-LSP claim is made.
- Programming no-excuse audit removed the one newly introduced silent-except finding. Its remaining 24 findings are inherited in `eastmoney.py`, `signals_b.py`, and `test_public_api.py`.
- Pure LOC: Eastmoney client 652, signals model 133, signals service 906, new client tests 77, new service tests 126, new cache/warning tests 237, new facade contract tests 72, public API tests 448, and docs-structure tests 86.
- Oracle remediation red phase: invalid dated rows left the f164 call count at zero, and a first-sector `DataSourceError` left the requested secids at only `90.bk9000`; the past-date fail-fast control passed.
- Oracle remediation focused green: the two regressions plus the past-date control passed 3 tests; the complete f164 service/cache warning group passed 14 tests in 1.20 seconds.
- Oracle remediation broader targeted suite passed 167 client, service, public API, CLI, and MCP tests in 6.29 seconds.
- Oracle remediation full regression passed 513 tests with 7 skips in 123.99 seconds.
- Oracle remediation docs contract passed in full mode with 0 committed paths selected while required docs, plan fields, and links were checked.
- Oracle remediation opt-in live smoke on 2026-07-30 returned a real f164 aggregate of 28,564,623,360 yuan with empty daily history; the 2026-07-29 historical guard did not invoke f164 and returned no aggregate.
- Strict OpenSpec validation reported `Change 'add-sector-fund-flow-f164-fallback' is valid`.
- Oracle test-file split preserved all 7 service/regression tests; pure LOC is 126 for `test_sector_f164_service.py` and 143 for `test_sector_f164_oracle_regressions.py`, with no no-excuse violations in either file.
- Final full regression after the mechanical test split passed 513 tests with 7 skips in 117.59 seconds.
- Final Oracle red phase: the revised invalid-row regression failed because `history_by_code["BK9000"]` contained three `None`/string/bool rows instead of `[]`.
- Final Oracle green phase: all 3 Oracle regressions passed; the complete f164 focused suite passed 24 tests in 2.11 seconds and the broader targeted suite passed 167 tests in 5.63 seconds.
- Final Oracle full regression passed 513 tests with 7 skips in 116.45 seconds.
- Final Oracle docs contract passed in full mode with 0 committed paths selected.
- Final Oracle live smoke on 2026-07-30 proved invalid-only push2his input yields empty history and a real f164 aggregate of 26,221,969,152 yuan; the 2026-07-29 historical guard returned no aggregate without invoking f164.

## Remaining Gaps

- `basedpyright` remains unavailable by prior user decision, so LSP diagnostics could not execute.
- The inherited no-excuse findings and oversized legacy modules predate this change; the new 237-line cache/warning test is in the warning band and should be split before future additions.
- No live-network gap remains for the observed 2026-07-29 payload; future upstream availability remains outside repository control.
- The pre-existing `astock_data.zip` remains untouched.

## Next Step

Archive `add-sector-fund-flow-f164-fallback` after final strict validation and OpenSpec apply status.
