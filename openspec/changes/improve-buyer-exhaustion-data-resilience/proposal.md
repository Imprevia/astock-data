# Improve Buyer Exhaustion Data Resilience

## Why

The `analyze-buyer-exhaustion` workflow currently loses important evidence when Eastmoney endpoints disconnect. `fund-flow` exits instead of returning a partial structured result, `stock-amount` discards real-time quote fields other than amount, and the full-market Sina pagination path takes about 63 seconds in the current environment. These gaps force manual reconstruction and can produce an incorrect price-change interpretation around ex-dividend dates.

## What Changes

- Extend the additive `KlineBar` contract with optional `change_pct` and `turnover_pct` fields.
- Preserve OHLCV, amount, vendor change percentage, and turnover percentage when `get_stock_amount` falls back to Tencent; parse the corresponding Eastmoney daily K-line fields when available.
- Make minute and daily fund-flow retrieval degrade independently into a structured `FundFlowResult` with warnings instead of failing the whole CLI command.
- Add a bounded market-breadth mode that uses index snapshots plus sorted market-extreme pages and does not require a full-market amount scan.
- Update `analyze-buyer-exhaustion` to merge stock amount, fund flow, fast market breadth, and dragon-tiger evidence while keeping every unavailable capability explicit.

## Impact

- Public model change is additive and optional.
- Python API, CLI, and MCP signatures for market breadth gain a backward-compatible fast-mode option.
- Existing default market-breadth behavior remains available for callers that require a verified full-market amount snapshot.
- The downstream buyer-exhaustion script gains additional structured output fields and dynamic limitations.

## Non-Goals

- Do not synthesize L2 order-book, cancellation, or account-level evidence.
- Do not infer dragon-tiger seats for stocks that did not publish a list.
- Do not label price or turnover estimates as exact vendor facts.
- Do not add a new vendor dependency or restore the retired Baidu PAE fund-flow source.

## Open Questions

None. External-source outages remain an explicit partial-data state rather than a reason to invent substitute facts.
