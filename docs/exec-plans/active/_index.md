# Active Execution Plans

## Stage

Complete

## Status

ETF coverage expansion and the related retrieval plans are complete awaiting archive or repository handling.

## Acceptance

- Each listed plan has an explicit lifecycle state.
- Completed retrieval plans record evidence, remaining gaps, and the next repository-handling step.

## Completion Evidence

- Completed: [Expand Sector ETF Coverage](expand-sector-etf-coverage.md)
- Completed: [Restore Latest-Trade-Day Sector Aggregate](restore-latest-trade-day-sector-aggregate.md)
- Completed: [Add Market Amount Snapshot Fallback](add-market-amount-snapshot-fallback.md)
- Completed: [Fix Historical Review Data Retrieval](fix-historical-review-data-retrieval.md)
- Existing active plan: [Harness Retrofit](harness-retrofit.md)
- Completed, awaiting archive: [Add Sector Fund Flow F164 Fallback](add-sector-fund-flow-f164-fallback.md)

## Remaining Gaps

- Seven fine-grained sectors still lack a defensible representative ETF and remain explicitly degraded.
- The market amount snapshot fallback and latest-trading-day aggregate restoration are implemented; the shared full suite and docs contract pass.
- The historical retrieval repair is implemented and verified but not yet archived.
- The harness plan remains active because its delivered files have not been staged or committed.
- CI and LSP availability remain explicitly tracked in the primary plan.
- The f164 fallback implementation and all Oracle remediations are complete; the plan remains active only until archive.

## Next Step

Archive completed plans when repository history handling is requested.
