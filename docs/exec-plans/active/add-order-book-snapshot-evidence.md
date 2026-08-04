# Add Order Book Snapshot Evidence

## Stage

Completion

## Status

The additive five-level snapshot capability, downstream buyer-exhaustion integration, independent review, and integration verification are complete. The plan remains active only until archive is explicitly requested.

## Acceptance

- Tencent five-level bid/ask data is exposed through one-to-one Python API, CLI, and MCP contracts.
- Multi-sample collection is bounded and validates its total planned wait before network access.
- Visible depth reductions remain unattributed and prices leaving the five-level window are not described as cancellations.
- Buyer-exhaustion analysis consumes only matching current-date snapshots and never contaminates historical analysis.
- Focused tests, full regression, docs contract, independent review, and a live 600809 smoke pass.

## Completion Evidence

- The live Tencent payload for 600809 on 2026-08-04 contained five bid and five ask levels plus vendor timestamp `20260804161500`.
- MX MCP returned a current five-level snapshot but targeted historical order and cancellation queries returned no order events.
- The user selected the free snapshot-sampling option and accepted that reductions cannot be called exact cancellations.
- Workflow assessment classified the change as `spec-required` because it adds a public contract across client, model, service, API, CLI, MCP, and downstream analysis boundaries.
- The public signature is `get_order_book(ticker, samples=1, interval_seconds=1.0)` with matching `order-book` CLI and `get_order_book` MCP entries.
- Final focused data verification passed 149 tests in 19.62 seconds.
- Final buyer-exhaustion integration verification passed 9 tests in 0.010 seconds.
- Review remediation added explicit `exact_cancellation_available=false`, typed all-sample failure semantics, partial-success preservation, and strict vendor-date filtering for buyer-exhaustion evidence.
- Revision 2 standardized depth levels on `position`, rejected truncated Tencent rows, isolated non-increasing vendor timestamps, and gave order-book subprocesses a sampling-aware timeout that degrades locally.
- Revision 3 corrected the stale README CLI-count contract from 25 to 26; its targeted test passed in 0.03 seconds without functional-code changes.
- Independent review passed revision 3 with no blocking findings.
- `python -m pytest -q` passed 551 tests with 7 skips in 133.26 seconds.
- `python scripts/check_docs_contract.py --mode full` passed.
- The live 600809 smoke returned five bids and five asks in lots, vendor timestamp `20260804161500`, `exact_cancellation_available=false`, and no changes for duplicate closing timestamps.
- Direct byte-level verification decoded the Tencent GBK name as `山西汾酒`; mojibake in one shell capture was a console-decoding artifact rather than a data-model error.

## Remaining Gaps

- Historical intraday depth before collection is unavailable.
- Exact cancellations, hidden liquidity, and order identity remain outside the free data contract.
- Direct Eastmoney push2 requests are unstable in the current environment; this design uses the verified Tencent payload.

## Next Step

Keep the completed change unarchived until explicit archive approval; consumers can now use the Python API, CLI, MCP tool, and current-date buyer-exhaustion integration.
