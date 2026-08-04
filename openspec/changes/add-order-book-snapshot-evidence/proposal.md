# Add Order Book Snapshot Evidence

## Why

The buyer-exhaustion workflow currently has no structured order-book evidence. The configured MX MCP can return a current five-level snapshot, but it does not provide historical snapshot sequences, tick-by-tick orders, or cancellation events. The existing Tencent quote response already exposes five bid and five ask levels and is reachable from the local data package.

## What Changes

- Add a structured five-level order-book result sourced from Tencent real-time quotes.
- Add one-to-one Python API, CLI, and MCP entrypoints with bounded multi-sample collection.
- Compare consecutive snapshots by visible price level and label depth increases, depth decreases, entries, and exits from the visible five-level window.
- Mark every depth decrease as unattributed; never describe it as a verified cancellation.
- Let `analyze-buyer-exhaustion` collect current-day order-book evidence while keeping historical dates isolated from current snapshots.
- Add offline contract tests, documentation, and a live 600809 smoke test.

## Impact

- The public surface grows from 25 to 26 Python APIs, CLI commands, and MCP tools.
- A new market-data model and service are added without changing existing signatures.
- Bounded sampling may block for a caller-selected interval, capped by validation rules.
- The buyer-exhaustion report gains optional order-book evidence and dynamic limitations.

## Non-Goals

- Do not call the free five-level snapshot true L2 data.
- Do not infer exact cancellations, order identities, hidden liquidity, or account behavior.
- Do not backfill historical intraday depth before collection was running.
- Do not persist a full trading-session order book or introduce a daemon.
- Do not make the data package depend on an Agent or natural-language MCP response.

## Open Questions

None. The user selected the free snapshot-sampling scope and accepted that reductions remain unattributed.
