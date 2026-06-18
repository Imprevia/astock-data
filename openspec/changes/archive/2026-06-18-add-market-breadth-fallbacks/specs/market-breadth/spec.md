## MODIFIED Requirements

### Requirement: Fixed index enumeration
The system SHALL provide index snapshots from a fixed internal enumeration of index identifiers. The implementation MUST NOT accept arbitrary user-supplied index codes and MUST NOT route index identifiers through `resolve_ticker`.

Default index keys SHALL include:

- `sh` for 上证指数
- `sz` for 深证成指
- `cyb` for 创业板指
- `kc50` for 科创50
- `hs300` for 沪深300
- `zz500` for 中证500

The system SHALL try index sources in this order: Eastmoney, Tencent, Sina. If Eastmoney rejects the connection or returns an unusable payload, the system MUST continue to the next source before failing the index capability.

#### Scenario: Default indices are returned
- **WHEN** `get_market_breadth()` succeeds and at least one index source is available
- **THEN** `indices` contains one `IndexSnapshot` for each default index key

#### Scenario: Index lookup does not use ticker resolver
- **WHEN** `get_market_breadth()` retrieves index snapshots
- **THEN** it uses internal vendor-specific index mappings and does not call `resolve_ticker` for index identifiers

#### Scenario: Eastmoney index source fails over to Tencent
- **WHEN** Eastmoney index snapshot calls fail with a transport or data-source error and Tencent returns valid index rows
- **THEN** `indices` is populated from Tencent and `raw.sources.indices` records `tencent`

#### Scenario: Index fallback warnings are recorded
- **WHEN** a higher-priority index source fails and a lower-priority source succeeds
- **THEN** `warnings` includes the failed source name and the fallback source used

### Requirement: Limit statistics from full-market classification
The system SHALL compute `LimitStats` from full-market quote rows. The result MUST include `limit_up_count` and `limit_down_count`, and MUST NOT include `broke_board_count` unless a future stable data source is specified.

The system SHALL try full-market quote sources in this order: Eastmoney clist, Tencent market board, Sina market pagination. If a source fails with transport, data-source, empty, or malformed payload errors, the system MUST continue to the next source before failing limit statistics.

The classification thresholds SHALL be:

- ST or `*ST` stock name: `±4.8%`
- 创业板 / 科创板 ticker prefixes `300`, `301`, `688`: `±19.5%`
- 北交所 ticker prefixes `8`, `92`, `43`: `±29.5%`
- Other A-share stocks: `±9.8%`

#### Scenario: Limit counts are computed from fallback quote rows
- **WHEN** Eastmoney clist fails and Tencent full-market rows contain normal, ST, 创业板/科创板, and 北交所 stocks
- **THEN** `limit_stats.limit_up_count` and `limit_stats.limit_down_count` reflect the threshold rules above and `raw.sources.limit_stats` records `tencent`

#### Scenario: Sina is used after Eastmoney and Tencent fail
- **WHEN** Eastmoney and Tencent full-market sources both fail and Sina returns valid rows
- **THEN** `limit_stats` is computed from Sina rows and `raw.sources.limit_stats` records `sina`

#### Scenario: Broke-board count is not promised
- **WHEN** `get_market_breadth()` returns `LimitStats`
- **THEN** the model does not require `broke_board_count` because available sources cannot reliably identify intraday failed limit-up attempts

### Requirement: Board ladders from stateless K-line derivation
The system SHALL compute `board_ladders` by deriving consecutive limit-up days from daily K-line data for the current limit-up stock set when a current limit-up stock set is available. The implementation MUST NOT persist cross-day board state and MUST NOT create a dedicated state database.

The default lookback window SHALL be 20 calendar days unless explicitly overridden by internal implementation constants.

If no source can provide a current limit-up stock set, the system SHALL return `board_ladders={}` and record a warning instead of failing the entire market breadth result, provided at least `indices` or `limit_stats` can still be returned.

#### Scenario: Consecutive limit-up days form board ladders
- **WHEN** a mocked limit-up stock has daily bars where the target date and the previous two trading days meet the limit-up threshold
- **THEN** the corresponding `BoardItem.boards` is `3` and the item appears under `board_ladders[3]`

#### Scenario: Non-limit-up day breaks the chain
- **WHEN** a mocked limit-up stock has a non-limit-up bar between two limit-up bars
- **THEN** the board count stops at the most recent consecutive limit-up run and does not include earlier limit-up days

#### Scenario: Board ladders degrade to empty when no limit-up set is available
- **WHEN** `indices` succeeds but all full-market quote sources fail
- **THEN** `board_ladders` is `{}` and `warnings` states that board ladder derivation was skipped because no current limit-up stock set was available

#### Scenario: No persistent board state is created
- **WHEN** `get_market_breadth()` calculates or skips board ladders
- **THEN** it does not write a board-state SQLite database or other cross-day state file

### Requirement: Result metadata and warnings
The system SHALL populate `MarketBreadthResult` with `source`, `retrieved_at`, `warnings`, and optionally `raw` according to existing `ResultBase` semantics. The `source` field SHALL remain a string and MAY summarize mixed origins using a value such as `market-breadth:fallback`.

The result warnings MUST include a warning when board ladders are derived from threshold-based K-line calculations rather than vendor-provided official board counts. The result warnings MUST also include source fallback or partial-result messages whenever a higher-priority source fails or a capability is omitted.

`raw.sources` SHALL record actual sources used per capability with keys including `indices`, `limit_stats`, and `board_ladders`.

#### Scenario: Mixed-source result preserves ResultBase shape
- **WHEN** `get_market_breadth()` returns successfully
- **THEN** `source` is a string, `retrieved_at` is populated, and `warnings` is a list

#### Scenario: Derived board warning is present
- **WHEN** `get_market_breadth()` includes `board_ladders`
- **THEN** `warnings` includes a message indicating the board ladder is derived and may differ from vendor terminal口径

#### Scenario: Actual sources are recorded
- **WHEN** indices come from Tencent and limit statistics come from Sina
- **THEN** `raw.sources.indices` is `tencent` and `raw.sources.limit_stats` is `sina`

#### Scenario: All sources fail with typed error
- **WHEN** all index sources and all full-market quote sources fail
- **THEN** `get_market_breadth()` raises a typed data-source error rather than returning an all-empty success result
