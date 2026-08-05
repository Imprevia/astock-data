# Improve Buyer Exhaustion Data Resilience

## Why

The `analyze-buyer-exhaustion` workflow currently loses important evidence when Eastmoney endpoints disconnect. `fund-flow` exits instead of returning a partial structured result, `stock-amount` discards real-time quote fields other than amount, and the full-market Sina pagination path takes about 63 seconds in the current environment. The current stock-concept implementation also queries a board constituent endpoint that returns empty membership for ordinary stocks, while the downstream report conflates a successful dragon-tiger query with no listing and a future session that has not happened with missing confirmation data. These gaps force manual reconstruction and can produce misleading empty-state conclusions.

## What Changes

- Extend the additive `KlineBar` contract with optional `change_pct` and `turnover_pct` fields.
- Preserve OHLCV, amount, vendor change percentage, and turnover percentage when `get_stock_amount` falls back to Tencent; parse the corresponding Eastmoney daily K-line fields when available.
- Make minute and daily fund-flow retrieval degrade independently into a structured `FundFlowResult` with warnings instead of failing the whole CLI command.
- Add a bounded market-breadth mode that uses index snapshots plus sorted market-extreme pages and does not require a full-market amount scan.
- Add explicit market-breadth availability states, nullable per-direction limit counts, exact snapshot-date verification, trustworthy clist completeness checks, and equivalent JSON/Markdown/Text status rendering so stale, malformed, partial, or non-trading-day data cannot appear as factual zero counts.
- Restore stock industry, region, and concept membership through the Eastmoney individual-stock core-conception endpoint while retaining the existing structured result.
- Update `analyze-buyer-exhaustion` to merge stock amount, fund flow, fast market breadth, concept, and dragon-tiger evidence while keeping every unavailable capability explicit.
- Distinguish published dragon-tiger data, a successful query with no target-date listing, an unavailable source, pending next-session confirmation, observed next-session confirmation, and historical confirmation data gaps; seat endpoint failures do not erase a confirmed event or no-listing result.
- Update `wildman-daily-review` so core-stock analysis explicitly consumes the restored concept and evidence-status outputs.

## Impact

- `KlineBar` changes are additive and optional. Market-breadth results add status fields, while limit counts become nullable when a direction is unavailable; downstream consumers must branch on status instead of assuming every count is an integer.
- Python API, CLI, and MCP signatures for market breadth gain a backward-compatible fast-mode option.
- Existing default market-breadth behavior remains available for callers that require a verified full-market amount snapshot.
- Requests whose snapshot date cannot be verified return a structured unavailable result rather than relabeling the latest live snapshot.
- The stock-concept source changes internally without adding a new public entrypoint.
- The downstream buyer-exhaustion script gains additive structured evidence and explicit status fields.

## Non-Goals

- Do not synthesize L2 order-book, cancellation, or account-level evidence.
- Do not infer dragon-tiger seats for stocks that did not publish a list.
- Do not label price or turnover estimates as exact vendor facts.
- Do not add a new vendor dependency or restore the retired Baidu PAE fund-flow source.

## Open Questions

None. External-source outages remain an explicit partial-data state rather than a reason to invent substitute facts.
