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
