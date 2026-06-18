## ADDED Requirements

### Requirement: Public market breadth entrypoint
The system SHALL expose `get_market_breadth(date: str = "")` as a public Python API function, CLI subcommand, and MCP tool. The entrypoint MUST return a structured Pydantic `MarketBreadthResult` model and MUST NOT require a stock symbol.

#### Scenario: Python API returns structured market breadth
- **WHEN** a caller imports and calls `get_market_breadth()` from `astock_data.api`
- **THEN** the system returns a `MarketBreadthResult` containing `indices`, `limit_stats`, and `board_ladders`

#### Scenario: CLI exposes market breadth command
- **WHEN** a caller runs `astock-data market-breadth --format json`
- **THEN** the CLI returns JSON serialized from `MarketBreadthResult`

#### Scenario: MCP exposes market breadth tool
- **WHEN** an MCP client invokes `get_market_breadth`
- **THEN** the MCP server returns the same structured fields as the Python API

### Requirement: Fixed index enumeration
The system SHALL provide index snapshots from a fixed internal enumeration of index secids. The implementation MUST NOT accept arbitrary user-supplied index codes and MUST NOT route index identifiers through `resolve_ticker`.

Default index keys SHALL include:

- `sh` for 上证指数 (`1.000001`)
- `sz` for 深证成指 (`0.399001`)
- `cyb` for 创业板指 (`0.399006`)
- `kc50` for 科创50 (`1.000688`)
- `hs300` for 沪深300 (`1.000300`)
- `zz500` for 中证500 (`1.000905`)

#### Scenario: Default indices are returned
- **WHEN** `get_market_breadth()` succeeds
- **THEN** `indices` contains one `IndexSnapshot` for each default index key

#### Scenario: Index lookup does not use ticker resolver
- **WHEN** `get_market_breadth()` retrieves index snapshots
- **THEN** it uses internal secid mappings and does not call `resolve_ticker` for index identifiers

### Requirement: Limit statistics from full-market classification
The system SHALL compute `LimitStats` from full-market Eastmoney `clist` quote rows. The result MUST include `limit_up_count` and `limit_down_count`, and MUST NOT include `broke_board_count` unless a future stable data source is specified.

The classification thresholds SHALL be:

- ST or `*ST` stock name: `±4.8%`
- 创业板 / 科创板 ticker prefixes `300`, `301`, `688`: `±19.5%`
- 北交所 ticker prefixes `8`, `92`, `43`: `±29.5%`
- Other A-share stocks: `±9.8%`

#### Scenario: Limit counts are computed from quote rows
- **WHEN** `get_market_breadth()` receives mocked clist rows spanning normal, ST, 创业板/科创板, and 北交所 stocks
- **THEN** `limit_stats.limit_up_count` and `limit_stats.limit_down_count` reflect the threshold rules above

#### Scenario: Broke-board count is not promised
- **WHEN** `get_market_breadth()` returns `LimitStats`
- **THEN** the model does not require `broke_board_count` because available sources cannot reliably identify intraday failed limit-up attempts

### Requirement: Board ladders from stateless K-line derivation
The system SHALL compute `board_ladders` by deriving consecutive limit-up days from daily K-line data for the current limit-up stock set. The implementation MUST NOT persist cross-day board state and MUST NOT create a dedicated state database.

The default lookback window SHALL be 20 calendar days unless explicitly overridden by internal implementation constants.

#### Scenario: Consecutive limit-up days form board ladders
- **WHEN** a mocked limit-up stock has daily bars where the target date and the previous two trading days meet the limit-up threshold
- **THEN** the corresponding `BoardItem.boards` is `3` and the item appears under `board_ladders[3]`

#### Scenario: Non-limit-up day breaks the chain
- **WHEN** a mocked limit-up stock has a non-limit-up bar between two limit-up bars
- **THEN** the board count stops at the most recent consecutive limit-up run and does not include earlier limit-up days

#### Scenario: No persistent board state is created
- **WHEN** `get_market_breadth()` calculates board ladders
- **THEN** it reads quote rows and K-line data only and does not write a board-state SQLite database or other cross-day state file

### Requirement: Result metadata and warnings
The system SHALL populate `MarketBreadthResult` with `source`, `retrieved_at`, `warnings`, and optionally `raw` according to existing `ResultBase` semantics. The `source` field SHALL remain a string and MAY summarize mixed origins using a value such as `eastmoney+derived`.

The result warnings MUST include a warning when board ladders are derived from threshold-based K-line calculations rather than vendor-provided official board counts.

#### Scenario: Mixed-source result preserves ResultBase shape
- **WHEN** `get_market_breadth()` returns successfully
- **THEN** `source` is a string, `retrieved_at` is populated, and `warnings` is a list

#### Scenario: Derived board warning is present
- **WHEN** `get_market_breadth()` includes `board_ladders`
- **THEN** `warnings` includes a message indicating the board ladder is derived and may differ from vendor terminal口径

### Requirement: Date handling
The system SHALL accept an optional ISO date string `YYYY-MM-DD`. If `date` is empty, the system SHALL use the current local date. Invalid date strings MUST raise the existing validation error style used by the market layer.

#### Scenario: Empty date defaults to current date
- **WHEN** `get_market_breadth(date="")` is called
- **THEN** the service resolves the request date to the current local date

#### Scenario: Explicit date is accepted
- **WHEN** `get_market_breadth(date="2026-06-17")` is called
- **THEN** the service uses `2026-06-17` as the target date for limit statistics and board ladder derivation

#### Scenario: Invalid date is rejected
- **WHEN** `get_market_breadth(date="2026/06/17")` is called
- **THEN** the service raises a market validation error rather than silently coercing the value
