# Design

## Current State

`get_stock_data` returns `OHLCVBar`, while `get_stock_amount` returns `KlineBar`. Eastmoney daily K-line rows currently stop at amount even though the upstream payload also exposes change percentage and turnover. The Tencent quote fallback already parses all required fields but the service retains only amount.

`get_fund_flow` performs minute and daily requests without independent error handling. A disconnect from either endpoint aborts the public function and CLI process.

`get_market_breadth` obtains current limit statistics through `SinaClient.market_all()`. Live timing on 2026-08-04 showed about 62.8 seconds for 5,535 rows, while indices, hot-stock enrichment, and board derivation each completed in roughly one second or less.

The buyer-exhaustion script consumes only K-line and dragon-tiger payloads, so amount, turnover, fund structure, and market environment remain manual additions. `EastmoneyClient.concept_blocks()` currently calls the push2 `slist` constituent endpoint with a stock `secid`; live calls for 600809 and 002230 return an empty list even though the individual-stock core-conception endpoint returns their industries, region, and concepts. The report also renders both a successful no-listing dragon-tiger query and an upstream failure as generic missing data, and it renders a target date equal to the local current date as if a next-session confirmation had already been checked.

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
2. Try the fast Eastmoney clist once, accepting it only when a positive valid supplier total exactly matches the returned single-page row count.
3. If Eastmoney fails, fetch Sina pages sorted by `changepercent` descending and ascending.
4. Stop each direction after the last row is outside the smallest applicable limit threshold, so normal sessions require only one page per direction.
5. Compute limit counts, limit-down rows, and board ladders from the extreme rows.
6. Skip the full-market amount snapshot and record that omission in warnings and `raw` metadata.

Every current or historical request first verifies that the vendor snapshot belongs to the exact requested trading session. A future date, non-trading current date, stale snapshot, or unverifiable date returns a structured unavailable result instead of relabeling current data.

`MarketBreadthResult.status` and `LimitStats.status` expose `available`, `partial`, or `unavailable`. Per-direction limit counts are nullable: a complete parseable direction may report an integer including zero, while an incomplete, malformed, truncated, or failed direction reports `null`. Sina market rows with missing/invalid stock codes or change percentages are rejected before counting. Markdown and text formatters render both status levels and show unavailable directions explicitly instead of omitting null values. Board-ladder source metadata and warnings are emitted only when ladders were actually derived.

Default mode keeps the existing full-market scan and verified market amount behavior.

Preferred Tencent and Sina sources are a valid composite result rather than a fallback failure. Source metadata identifies the actual composite components; warnings are reserved for omitted capabilities, derived ladders, or genuine source failures.

### Stock concept membership

Replace the stock-`secid` `slist` call with the Eastmoney individual-stock core-conception endpoint. The client sends the resolved market-prefixed stock code and normalizes the returned `ssbk` rows. The upstream ordering is preserved: ranks 1-3 are industry classifications, rank 4 is the regional board, and remaining rows are concept or style memberships. The service continues to return the existing `ConceptBlocksResult` fields and records the normalized raw rows for audit.

An explicit `ssbk=[]` remains an empty successful membership result. Missing or malformed `ssbk`, invalid rank, missing board code, or empty board name is a typed data-source failure. Classification uses normalized rank only: ranks 1-3 are industries, rank 4 is region, and later ranks are concepts or styles; names do not override that mapping.

### Dragon-tiger and forward-confirmation states

The downstream analysis exposes explicit status values:

- dragon-tiger: `published`, `not-listed`, or `unavailable`;
- forward confirmation: `pending`, `observed`, or `unavailable`.

`not-listed` means the public endpoint was queried successfully and no event exists on the target date; in that state the service does not request seat endpoints. When a target-date event exists, buy-seat and sell-seat requests degrade independently so a seat outage adds a warning without erasing the published event. `pending` means the target session is today or later and no later trading session has occurred. Historical targets with no returned later bar are `unavailable`, not negative confirmation. Existing event and session arrays remain available for compatibility.

### Buyer-exhaustion integration

The script invokes four structured CLI boundaries:

- `kline`
- `stock-amount`
- `fund-flow`
- `market-breadth --fast`
- optional `dragon-tiger`
- `concepts`

Each supplemental command is best-effort. Failure becomes a source warning, not a total analysis failure. For the target bar, exact vendor values take precedence in this order:

1. Matching `stock-amount` bar value.
2. Base K-line value or derived change percentage.
3. `None` with an explicit limitation.

The JSON and Markdown output include amount, turnover, main fund-flow values, benchmark index changes, market limit counts, concepts, dragon-tiger query status, forward-confirmation status, source metadata, and dynamic limitations.

## Failure Modes

- Eastmoney amount history blocked: use a same-day Tencent quote only when its quote date matches the requested date.
- Eastmoney fund-flow blocked: return structured empty/partial flow evidence with warnings.
- Eastmoney clist lacks a valid exact total, or Sina extreme pages are blocked, malformed, or truncated: reject the incomplete source, retain any verified independent evidence, set the affected limit direction to `null`, and return partial or unavailable limit statistics with warnings.
- Dragon-tiger target event is absent: skip seat retrieval and preserve `not-listed`; a seat endpoint failure for a published event preserves the event and adds a capability-specific warning.
- Requested market session cannot be matched exactly to the vendor snapshot date: return structured unavailable market breadth without live indices or ladders.
- Target date is historical and no exact amount bar is available: leave amount and turnover unavailable; do not backfill the current quote.
- L2 and unpublished dragon-tiger data remain unavailable by design.
- A future trading session remains pending until it occurs; the system does not synthesize confirmation data.

## Compatibility

`KlineBar` fields are optional and command defaults remain unchanged. Fast market breadth is opt-in. Market-breadth status fields are additive, but unavailable limit directions now serialize as `null`; consumers that previously assumed integers must use the status contract. Old consumers ignoring new buyer-exhaustion fields continue to work for available results.

## Verification

- Offline client parsing tests for Eastmoney and Tencent metric fields.
- Service tests for independent fund-flow failure and partial success.
- Market-breadth fast-mode tests proving bounded pagination, clist completeness, real Sina normalization failures, and JSON/Markdown/Text availability metadata.
- Buyer-exhaustion tests for metric precedence, dynamic limitations, and supplemental-command failure.
- Concept client/service tests for 600809-like and 002230-like normalized membership.
- Buyer-exhaustion tests for published/not-listed/unavailable dragon-tiger states and pending/observed/unavailable forward states.
- Skill validation proving `wildman-daily-review` references the restored concept evidence.
- Full `stock-data-source` regression, docs contract, and a live 600809 smoke after implementation.
