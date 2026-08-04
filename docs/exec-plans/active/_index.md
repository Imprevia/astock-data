# Active Execution Plans

## Stage

Verification

## Status

The completed retrieval plans remain awaiting archive. Buyer-exhaustion data resilience remains in specification; free order-book snapshot evidence is complete and awaiting archive.

## Acceptance

- Each listed plan has an explicit lifecycle state.
- Completed retrieval plans record evidence, remaining gaps, and the next repository-handling step.

## Completion Evidence

- In specification: [Improve Buyer Exhaustion Data Resilience](improve-buyer-exhaustion-data-resilience.md)
- Completed, awaiting archive: [Add Order Book Snapshot Evidence](add-order-book-snapshot-evidence.md)
- Completed: [Expand Sector ETF Coverage](expand-sector-etf-coverage.md)
- Completed: [Restore Latest-Trade-Day Sector Aggregate](restore-latest-trade-day-sector-aggregate.md)
- Completed: [Add Market Amount Snapshot Fallback](add-market-amount-snapshot-fallback.md)
- Completed: [Fix Historical Review Data Retrieval](fix-historical-review-data-retrieval.md)
- Existing active plan: [Harness Retrofit](harness-retrofit.md)
- Completed, awaiting archive: [Add Sector Fund Flow F164 Fallback](add-sector-fund-flow-f164-fallback.md)

## Remaining Gaps

- The buyer-exhaustion resilience change requires OpenSpec validation and explicit approval before implementation.
- The order-book snapshot change passed focused checks, independent review, full regression, docs contract, and a live 600809 smoke; exact cancellations and historical intraday backfill remain unavailable.
- Seven fine-grained sectors still lack a defensible representative ETF and remain explicitly degraded.
- The market amount snapshot fallback and latest-trading-day aggregate restoration are implemented; the shared full suite and docs contract pass.
- The historical retrieval repair is implemented and verified but not yet archived.
- The harness plan remains active because its delivered files have not been staged or committed.
- CI and LSP availability remain explicitly tracked in the primary plan.
- The f164 fallback implementation and all Oracle remediations are complete; the plan remains active only until archive.

## Next Step

Archive the completed order-book change when explicitly requested; approve the separate buyer-exhaustion resilience change before its broader implementation.
