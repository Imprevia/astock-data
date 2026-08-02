# Add Market Amount Snapshot Fallback

## Stage

Complete

## Status

The date-verified full-market amount snapshot is implemented. Sina market rows retain amount fields, market breadth validates the snapshot date, and daily-review separates the exact snapshot from index-proxy history.

## Acceptance

- Sina market rows preserve numeric `volume`, `amount`, and `ticktime` fields while retaining existing limit-stat fields.
- `get_market_breadth(target_date)` sums positive per-stock amounts only when a Sina index K-line independently verifies that the live market snapshot belongs to `target_date`.
- The structured result exposes the amount, exact snapshot date, row count, and source under `raw.market_amount`; a date mismatch or unverifiable date emits a warning and omits the value.
- `daily-review` uses the verified snapshot for the current full-market amount while keeping the existing index-proxy history explicitly separate for 5/10-day trend comparisons.
- Offline tests, full regression, docs contract, and a 2026-07-31 live smoke pass.

## Completion Evidence

- Live Sina raw market-center data contains `amount`, `volume`, and `ticktime`; the existing normalizer retained only code, name, close, and change percentage.
- The mootdx server discovery path leaves `BESTIP.HQ` empty in this environment and repeated TCP 7709 probes did not return usable rows, so it remains an optional source rather than a required fallback.
- Focused Sina and market-breadth tests pass, and the live 2026-07-31 snapshot returned 2.5591 trillion yuan across 5,527 stocks.

## Remaining Gaps

- Full-market amount history is not available from the live market pagination endpoint; only a date-verified latest trading-day snapshot can be exposed.
- External market-center pagination and index-date verification may fail independently and must degrade with warnings.
- Exact historical per-stock amounts still depend on Eastmoney or another source; the downstream OHLC estimate remains explicit when exact values are unavailable.

## Next Step

Run the shared full regression and docs contract after the remaining sector aggregate restoration is complete.
