# Improve Buyer Exhaustion Data Resilience

## Stage

Implementation

## Status

Revision 4 implementation and main-owned engineering checks are complete. The third independent review found four remaining gaps in real Sina row normalization, Eastmoney clist completeness, dragon-tiger seat degradation, and human-readable market-breadth status output; those fixes and regression tests are present. Current-revision Developer ownership and independent review remain pending because the host collaboration dispatch interface is not accepting another Agent call.

## Acceptance

- Fund-flow endpoint failures return structured partial results with warnings.
- Stock amount preserves matching-date amount, vendor change percentage, and turnover percentage.
- Fast market breadth completes without a full Sina market scan while retaining objective limit and index evidence.
- Historical market breadth is used only after exact target-session verification; fast limit-count failures preserve partial or unavailable semantics instead of fabricated zeroes.
- Buyer-exhaustion output consumes the new evidence and keeps unavailable L2 or unpublished dragon-tiger data explicit.
- Historical buyer-exhaustion analysis ignores current minute fund flow and uses only exact-date daily evidence; dual-empty endpoints are unavailable.
- Stock concepts return industries, region, and concept tags for 600809 and 002230 through the individual-stock endpoint.
- Dragon-tiger output distinguishes not listed from source unavailable; forward confirmation distinguishes pending from historical data unavailable.
- Focused tests, full regression, docs contract, independent review, and a live 600809 smoke pass.

## Completion Evidence

- 2026-08-04 live `fund-flow` failed because Eastmoney disconnected and caused a nonzero CLI exit.
- 2026-08-04 live `market-breadth` timing isolated 62.79 seconds in `SinaClient.market_all()` for 5,535 rows; indices took 0.06 seconds and board derivation took 0.06 seconds.
- Sina sorted gainers and losers pages returned 100 rows per direction and can bound limit classification without full pagination.
- `stock-amount` returned exact amount through Tencent fallback but discarded already-parsed OHLCV, change percentage, and turnover percentage fields.
- Eastmoney core-conception live probes returned 19 board memberships for 600809 and 50 for 002230, while the existing stock-`secid` `slist` call returned empty arrays.
- Dragon-tiger live probes for both target stocks succeeded with empty event arrays, proving the correct state is not listed rather than source unavailable.
- Revision 2 focused data checks passed 173 tests in 10.18 seconds.
- Revision 2 buyer-exhaustion script checks passed 15 tests.
- Revision 2 wildman skill validation reported `Skill is valid!`.
- Revision 3 focused data checks passed 180 tests; buyer-exhaustion checks passed 16 tests; wildman skill validation passed.
- Full regression passed 581 tests with 7 skips; the full docs contract, both diff checks, and OpenSpec strict validation passed.
- Live 600809 and 002230 smoke returned available concepts and market context, dragon-tiger `not-listed`, and forward confirmation `pending`. Public Eastmoney amount and fund-flow disconnections degraded to matching-date Tencent metrics or structured unavailable evidence.
- Revision 4 narrow branch checks passed for Sina parsing, clist completeness, dragon-tiger seat degradation, formatter status rendering, and the real Sina normalization path.
- Revision 4 package regression passed 602 tests with 7 skips; 16 buyer-exhaustion tests and `wildman-daily-review` validation passed. The full docs contract and strict OpenSpec validation passed.
- Revision 4 live smoke returned 3 industries, 1 region, and 15 concepts for 600809; 3 industries, 1 region, and 46 concepts for 002230. Both returned market/limit status `available`, dragon-tiger `not-listed`, forward confirmation `pending`, matching-date Tencent amount fallback, and structured unavailable fund flow during Eastmoney disconnections.

## Remaining Gaps

- L2 order-book and account-level identity remain unavailable without an authorized provider.
- External vendors may still return no data; the intended fix is truthful partial results, not fabricated replacement values.
- The 2026-08-06 session cannot be confirmed before it occurs; the output will remain pending until later data exists.
- Revision 4 still requires real Developer verification and an independent no-blocker review. Build, lint, typecheck, and product checks are not configured as gates for this change.

## Next Step

Restore Agent dispatch, complete revision 4 Developer verification and independent read-only review, then archive the OpenSpec change.
