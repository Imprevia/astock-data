# Improve Buyer Exhaustion Data Resilience

## Stage

Specification

## Status

The failure modes are reproduced and the OpenSpec change is drafted. Source implementation is blocked on explicit approval of the public-contract and cross-module scope.

## Acceptance

- Fund-flow endpoint failures return structured partial results with warnings.
- Stock amount preserves matching-date amount, vendor change percentage, and turnover percentage.
- Fast market breadth completes without a full Sina market scan while retaining objective limit and index evidence.
- Buyer-exhaustion output consumes the new evidence and keeps unavailable L2 or unpublished dragon-tiger data explicit.
- Focused tests, full regression, docs contract, independent review, and a live 600809 smoke pass.

## Completion Evidence

- 2026-08-04 live `fund-flow` failed because Eastmoney disconnected and caused a nonzero CLI exit.
- 2026-08-04 live `market-breadth` timing isolated 62.79 seconds in `SinaClient.market_all()` for 5,535 rows; indices took 0.06 seconds and board derivation took 0.06 seconds.
- Sina sorted gainers and losers pages returned 100 rows per direction and can bound limit classification without full pagination.
- `stock-amount` returned exact amount through Tencent fallback but discarded already-parsed OHLCV, change percentage, and turnover percentage fields.

## Remaining Gaps

- The OpenSpec change requires explicit approval before implementation.
- L2 order-book and account-level identity remain unavailable without an authorized provider.
- External vendors may still return no data; the intended fix is truthful partial results, not fabricated replacement values.

## Next Step

Validate the OpenSpec change, obtain approval, then dispatch the governed Developer and independent Reviewer roles.
