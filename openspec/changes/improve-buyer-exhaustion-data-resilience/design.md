# Design

## Current State

`get_stock_data` returns `OHLCVBar`, while `get_stock_amount` returns `KlineBar`. Eastmoney daily K-line rows currently stop at amount even though the upstream payload also exposes change percentage and turnover. The Tencent quote fallback already parses all required fields but the service retains only amount.

`get_fund_flow` performs minute and daily requests without independent error handling. A disconnect from either endpoint aborts the public function and CLI process.

`get_market_breadth` obtains current limit statistics through `SinaClient.market_all()`. Live timing on 2026-08-04 showed about 62.8 seconds for 5,535 rows, while indices, hot-stock enrichment, and board derivation each completed in roughly one second or less.

The buyer-exhaustion script consumes only K-line and dragon-tiger payloads, so amount, turnover, fund structure, and market environment remain manual additions.

## Proposed Design

### Additive K-line metrics

Add nullable `change_pct` and `turnover_pct` fields to `KlineBar`. Extend the Eastmoney K-line field list through `f61` and parse:

- `f59` as `change_pct`
- `f61` as `turnover_pct`

When Eastmoney fails, construct the current Tencent fallback bar with the quote date, open, high, low, close, volume, amount, change percentage, and turnover percentage. The result warning must identify the fallback source. Missing historical bars remain missing; the service must not copy the current quote onto a historical date.

### Independent fund-flow degradation

Wrap minute and daily requests independently. Each failed capability contributes a warning and an empty collection while the other successful capability remains available. `signal` is derived only from available minute rows. If both requests fail, the function still returns a valid result with `minute=[]`, `daily=[]` when history was requested, `signal=None`, and explicit warnings.

No other quote source is treated as a substitute for Eastmoney order-size classifications.

### Bounded market breadth

Add `fast: bool = False` to the Python API, CLI, and MCP market-breadth entrypoints.

In fast mode:

1. Fetch fixed index snapshots through the existing fallback chain.
2. Try the fast Eastmoney clist once.
3. If Eastmoney fails, fetch Sina pages sorted by `changepercent` descending and ascending.
4. Stop each direction after the last row is outside the smallest applicable limit threshold, so normal sessions require only one page per direction.
5. Compute limit counts, limit-down rows, and board ladders from the extreme rows.
6. Skip the full-market amount snapshot and record that omission in warnings and `raw` metadata.

Default mode keeps the existing full-market scan and verified market amount behavior.

### Buyer-exhaustion integration

The script invokes four structured CLI boundaries:

- `kline`
- `stock-amount`
- `fund-flow`
- `market-breadth --fast`
- optional `dragon-tiger`

Each supplemental command is best-effort. Failure becomes a source warning, not a total analysis failure. For the target bar, exact vendor values take precedence in this order:

1. Matching `stock-amount` bar value.
2. Base K-line value or derived change percentage.
3. `None` with an explicit limitation.

The JSON and Markdown output include amount, turnover, main fund-flow values, benchmark index changes, market limit counts, source metadata, and dynamic limitations.

## Failure Modes

- Eastmoney amount history blocked: use a same-day Tencent quote only when its quote date matches the requested date.
- Eastmoney fund-flow blocked: return structured empty/partial flow evidence with warnings.
- Sina extreme pages blocked: retain indices and return unavailable limit statistics with warnings.
- Target date is historical and no exact amount bar is available: leave amount and turnover unavailable; do not backfill the current quote.
- L2 and unpublished dragon-tiger data remain unavailable by design.

## Compatibility

All new model fields are optional. Existing serialized fields and command defaults remain unchanged. Fast market breadth is opt-in, and old consumers ignoring new buyer-exhaustion fields continue to work.

## Verification

- Offline client parsing tests for Eastmoney and Tencent metric fields.
- Service tests for independent fund-flow failure and partial success.
- Market-breadth fast-mode tests proving bounded pagination and metadata.
- Buyer-exhaustion tests for metric precedence, dynamic limitations, and supplemental-command failure.
- Full `stock-data-source` regression, docs contract, and a live 600809 smoke after implementation.
