# Design

## Current State

`TencentClient.quote()` parses the real-time Tencent payload but discards indices 9 through 28, which contain five bid prices and volumes followed by five ask prices and volumes. Index 30 contains the vendor timestamp. The public package has no order-book model, service, API, CLI, or MCP entrypoint, and the buyer-exhaustion script therefore always reports order-book depth as unavailable.

The MX MCP confirms that a current five-level snapshot exists for 600809, but targeted queries returned no historical order-event data. A current snapshot cannot reconstruct an earlier intraday sequence.

## Proposed Design

### Tencent parsing

Extend the Tencent client with a dedicated order-book parser that returns:

- vendor timestamp normalized from `YYYYMMDDHHMMSS`;
- last price;
- bid levels 1 through 5 from payload indices 9 through 18;
- ask levels 1 through 5 from payload indices 19 through 28.

Each level contains `position`, `price`, and `volume_lots`. Tencent quote volumes are lots, where one lot represents 100 shares. Missing or zero-price levels are omitted rather than fabricated.

### Public model

Add additive models for an order-book level, snapshot, visible-level change, and result. A snapshot includes visible bid/ask depth totals, spread, and normalized depth imbalance when calculable.

The result contains the resolved ticker, successful snapshots, visible-level changes, requested sampling metadata, source, warnings, and `exact_cancellation_available=false`.

### Bounded sampling

Expose `get_order_book(ticker, samples=1, interval_seconds=1.0)`.

- `samples` must be between 1 and 60.
- `interval_seconds` must be between 1 and 60 seconds.
- total planned wait `(samples - 1) * interval_seconds` must not exceed 300 seconds.
- the default remains one non-blocking snapshot.
- failed later samples preserve earlier successful snapshots and add warnings.
- total failure returns the package's typed data-source error; downstream analysis catches it as an independent limitation.

Consecutive snapshots with the same vendor timestamp do not generate changes. Visible changes are compared by side and price, not by level position:

- same price, larger volume: `depth-increase`;
- same price, smaller volume: `depth-decrease` with `attribution=unattributed`;
- new visible price: `entered-view`;
- no longer visible price: `left-view`.

`left-view` does not mean the order was removed; the price may have moved beyond the visible five levels.

### Public adapters

Add `order-book` to the CLI and `get_order_book` to MCP with the same arguments and serialized result. Update the public API export and the documented interface count from 25 to 26.

### Buyer-exhaustion integration

The analysis script adds order-book sampling options and invokes the structured CLI only when the target date equals the current local date. Historical dates never consume a current snapshot.

Dynamic evidence rules:

- one valid snapshot can describe only current visible depth and spread;
- at least two distinct matching-date vendor timestamps are required for depth-change evidence;
- depth decreases are reported as unattributed reductions, not cancellations;
- outside-session static snapshots remain objective closing snapshots but cannot establish intraday replenishment or withdrawal behavior.

## Failure Modes

- Tencent is unavailable: the new capability returns a typed failure and the buyer-exhaustion analysis retains other evidence with a warning.
- The payload is truncated: the client rejects unusable rows instead of shifting indices.
- A sample repeats the previous timestamp: retain the snapshot but do not create false changes.
- The vendor timestamp does not match the requested analysis date: exclude it from the target-date evidence.
- A price leaves the visible window: label it `left-view`, never as a cancellation.

## Compatibility

Existing public signatures and serialized fields remain unchanged. The new entrypoint is additive. Sampling defaults to one request, so existing callers do not incur new delays.

## Verification

- Offline Tencent parsing tests for five levels, timestamp, unit handling, and malformed payloads.
- Model and service tests for depth metrics, bounded validation, partial sampling, duplicate timestamps, and change semantics.
- Public API, CLI, MCP, and documentation contract tests for the 26th entrypoint.
- Buyer-exhaustion tests for current-date use, historical-date isolation, single-snapshot limitations, and unattributed reductions.
- Full regression, docs contract, independent review, and a live 600809 smoke.
