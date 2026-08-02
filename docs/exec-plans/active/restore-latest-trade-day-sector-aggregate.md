# Restore Latest-Trade-Day Sector Aggregate

## Stage

Complete

## Status

The latest completed trading-day aggregate recovery is implemented. Eastmoney f164 is accepted only after independent Sina index-date verification, aggregate-only mode bounds review latency, and cached daily fund-flow history precedes THS market bars.

## Acceptance

- Five-day f164 data is eligible only when the requested period is five days and the Sina Shanghai index latest date exactly matches the target date.
- A mismatched or unverifiable latest date keeps f164 disabled and never assigns current aggregates to an older historical date.
- Daily history and positive-day counts remain unavailable when only the aggregate is present.
- `daily-review` displays the verified aggregate with an aggregate-only label instead of claiming continuous inflow.
- Sector history requests preserve the documented eight-worker concurrency so endpoint failures do not serialize into multi-minute review timeouts.
- The public service supports aggregate-only retrieval so downstream review code can obtain one verified bulk snapshot without launching per-sector history requests.
- Cached daily fund-flow history is preferred over THS market-price bars, preserving semantically correct data across same-day reruns.
- Focused tests, full regression, docs contract, and a 2026-07-31 live smoke pass.

## Completion Evidence

- Existing service tests prove that unverified historical targets do not use f164.
- The 2026-07-31 review is running on 2026-08-02, so a latest-trading-day check can distinguish the completed Friday session from arbitrary history.
- Inspection found that a request lock enclosed the full network call and unintentionally serialized the documented thread pool.
- Focused retrieval regression passed 144 tests; the final full suite passed 524 tests with 7 skips; the full docs contract passed.
- Live verification confirmed Sina date `2026-07-31`, 128 f164 industry aggregates, and a complete enhanced review in about 61 seconds.

## Remaining Gaps

- f164 supplies only one five-day aggregate and cannot recover daily positive-flow counts.
- If Sina index K-line verification is unavailable, the aggregate must remain unavailable.

## Next Step

Archive the completed execution plans when repository history handling is requested.
