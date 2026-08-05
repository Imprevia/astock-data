## ADDED Requirements

### Requirement: Additive K-line evidence metrics

The system SHALL expose optional vendor change percentage and turnover percentage fields on `KlineBar` without removing or renaming existing fields.

#### Scenario: Eastmoney daily K-line provides all evidence metrics

- **WHEN** Eastmoney returns daily K-line fields through `f61`
- **THEN** the corresponding `KlineBar` contains OHLCV, amount, `change_pct`, and `turnover_pct`

#### Scenario: Tencent current quote is used as amount fallback

- **WHEN** Eastmoney amount history fails and Tencent returns a current quote whose date matches the requested current session
- **THEN** the fallback bar preserves OHLCV, amount, `change_pct`, and `turnover_pct` and records a source warning

#### Scenario: Historical request does not reuse current quote

- **WHEN** the requested target date is earlier than the Tencent quote date
- **THEN** the system MUST NOT assign the current quote metrics to the historical date

### Requirement: Partial fund-flow results

The system SHALL isolate minute and daily fund-flow failures and return a structured `FundFlowResult` whenever ticker resolution succeeds.

#### Scenario: Minute flow fails but daily flow succeeds

- **WHEN** the minute endpoint fails and the daily endpoint returns valid rows
- **THEN** the result contains `minute=[]`, preserves daily rows, derives no minute signal, and records the minute failure warning

#### Scenario: Daily flow fails but minute flow succeeds

- **WHEN** the daily endpoint fails and the minute endpoint returns valid rows
- **THEN** the result preserves minute rows and signal, contains an empty daily collection, and records the daily failure warning

#### Scenario: Both flow endpoints fail

- **WHEN** both Eastmoney fund-flow endpoints fail
- **THEN** the public API and CLI return an empty structured result with warnings rather than an unhandled command failure

### Requirement: Bounded market-breadth mode

The system SHALL provide an opt-in fast market-breadth mode that avoids full-market pagination while preserving structured source metadata.

#### Scenario: Eastmoney clist succeeds in fast mode

- **WHEN** fast mode is requested and Eastmoney returns usable full-market rows within the fail-fast request
- **THEN** the service computes limit statistics from those rows without calling Sina market pagination

#### Scenario: Eastmoney clist fails in fast mode

- **WHEN** fast mode is requested and Eastmoney clist fails
- **THEN** the service fetches sorted Sina gainers and losers pages, stops after rows leave the applicable limit threshold, and computes limit statistics from the bounded result

#### Scenario: Fast mode omits full-market amount

- **WHEN** fast mode returns a market-breadth result
- **THEN** `raw.market_amount` is unavailable and warnings explicitly state that the verified full-market amount scan was skipped

#### Scenario: Default mode remains compatible

- **WHEN** callers omit the fast-mode option
- **THEN** the existing full-market scan and date-verified market amount behavior remain available

### Requirement: Truthful market-breadth availability

The system SHALL expose `MarketBreadthResult.status` and `LimitStats.status` as `available`, `partial`, or `unavailable`. `limit_up_count` and `limit_down_count` SHALL be nullable so unavailable source directions are never serialized as factual zero counts.

#### Scenario: Requested session cannot be verified

- **WHEN** the requested date cannot be matched exactly to the vendor snapshot date, including a future date, non-trading current date, or stale current snapshot
- **THEN** market breadth is `unavailable`, indices and ladders are empty, both limit counts are `null`, and source warnings explain the date mismatch

#### Scenario: One limit direction is unavailable

- **WHEN** only the gainers or losers extreme path returns complete and parseable rows
- **THEN** `LimitStats.status` is `partial`, the available direction has an integer count, and the unavailable direction is `null`

#### Scenario: Both limit directions are unavailable

- **WHEN** neither limit direction returns complete and parseable rows
- **THEN** `LimitStats.status` is `unavailable` and both counts are `null`

#### Scenario: Limit source payload is malformed or truncated

- **WHEN** required code or change-percentage fields are missing, unparseable, or the bounded page cannot prove completion
- **THEN** that source is rejected or the affected direction is marked unavailable rather than counted as zero

#### Scenario: Full-market clist cannot prove completeness

- **WHEN** the Eastmoney clist total is missing, invalid, non-positive, smaller than returned rows, or does not exactly match the single fast-mode page
- **THEN** the clist response is rejected and the service falls back or marks limit evidence unavailable

#### Scenario: Human-readable output preserves availability

- **WHEN** market breadth is formatted as Markdown or text
- **THEN** the output explicitly includes the top-level status, `LimitStats.status`, and both directions, rendering unavailable counts as unavailable rather than omitting them

#### Scenario: No board ladder was derived

- **WHEN** no complete limit-up set is available or derivation returns no ladders
- **THEN** the top-level source and warnings MUST NOT claim a `derived` ladder source

### Requirement: Buyer-exhaustion evidence integration

The buyer-exhaustion analysis SHALL merge supplemental structured evidence independently and SHALL NOT fail the complete analysis when one supplemental capability is unavailable.

#### Scenario: Supplemental metrics are available

- **WHEN** matching-date amount, turnover, fund-flow, and fast market-breadth payloads are returned
- **THEN** JSON and Markdown output include those objective facts and their sources

#### Scenario: Supplemental command fails

- **WHEN** one supplemental CLI command fails or returns empty data
- **THEN** the base K-line analysis remains available and the missing capability appears in source warnings and dynamic limitations

#### Scenario: Vendor percentage prevents ex-dividend distortion

- **WHEN** a matching target bar contains vendor `change_pct`
- **THEN** the analysis uses that value instead of deriving percentage change from an unadjusted previous close

#### Scenario: Restricted evidence remains explicit

- **WHEN** L2 data or unpublished dragon-tiger seats are unavailable
- **THEN** the output identifies the capability as unavailable and does not synthesize substitute facts

### Requirement: Stock concept membership recovery

The system SHALL return structured industry, region, and concept membership for a resolved A-share through an individual-stock membership endpoint rather than treating a block constituent endpoint as stock membership.

#### Scenario: Individual stock has board memberships

- **WHEN** Eastmoney returns ordered `ssbk` rows for a resolved stock
- **THEN** the existing concept result contains its industry classifications, regional board, concept memberships, and non-empty concept tags

#### Scenario: Membership source returns an empty result

- **WHEN** the individual-stock endpoint succeeds with no membership rows
- **THEN** the system returns an explicit empty structured result without inventing concepts

#### Scenario: Membership payload is malformed

- **WHEN** `ssbk` is missing or not a list, or a membership row lacks a valid rank, board code, or non-empty board name
- **THEN** the client raises a typed data-source error rather than returning a successful empty result

#### Scenario: Membership ranks determine categories

- **WHEN** valid ordered membership rows are normalized
- **THEN** ranks 1-3 are industries, rank 4 is region, and ranks 5 onward are concepts or styles without name-based reclassification

### Requirement: Truthful restricted-evidence states

The buyer-exhaustion report SHALL distinguish absent published evidence, unavailable sources, and evidence that cannot exist yet.

#### Scenario: Stock did not publish a dragon-tiger list

- **WHEN** the dragon-tiger query succeeds and no event matches the target date
- **THEN** the service skips seat endpoints and the report marks the stock as `not-listed` without describing the query as missing data

#### Scenario: Published event seat endpoint fails

- **WHEN** an event matches the target date but either buy-seat or sell-seat retrieval fails
- **THEN** the event remains published, the failed seat collection is empty, and a source warning identifies only the failed seat capability

#### Scenario: Dragon-tiger source fails

- **WHEN** the dragon-tiger command fails
- **THEN** the report marks the capability as `unavailable` and preserves the source warning

#### Scenario: Next trading session has not occurred

- **WHEN** the target date is the local current date or later and no future bar exists
- **THEN** forward confirmation is `pending` rather than a negative confirmation

#### Scenario: Historical target lacks a future bar

- **WHEN** the target date is before the local current date and no future bar is returned
- **THEN** forward confirmation is `unavailable` with an explicit data-gap limitation

#### Scenario: Future session is available

- **WHEN** at least one later trading-session bar is returned
- **THEN** forward confirmation is `observed` and the report may state whether the configured retreat condition was confirmed
